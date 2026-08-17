from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass


class SecretStoreError(RuntimeError):
    pass


class SecretStoreUnavailable(SecretStoreError):
    pass


_PROVIDER_ENV = {
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
}
_PROVIDER_TARGET = {
    "deepseek": "Law-Rag:DeepSeek-API-Key",
    "kimi": "Law-Rag:Kimi-API-Key",
}

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_GENERIC_SECRET_BYTES = 5 * 512


@dataclass(frozen=True)
class ResolvedSecret:
    value: str | None
    source: str | None


def _provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in _PROVIDER_ENV:
        raise SecretStoreError(f"Unsupported provider secret: {provider}")
    return normalized


def secure_store_available() -> bool:
    return sys.platform == "win32"


def _credential_api():
    if not secure_store_available():
        raise SecretStoreUnavailable("Windows Credential Manager is only available on Windows.")

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    advapi.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi.CredDeleteW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    advapi.CredFree.restype = None
    return advapi, CREDENTIALW


def _target(provider: str) -> str:
    return _PROVIDER_TARGET[_provider_name(provider)]


def read_secure_secret(provider: str) -> str | None:
    target = _target(provider)
    advapi, credential_type = _credential_api()
    pointer = ctypes.POINTER(credential_type)()
    if not advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise SecretStoreError(f"Windows Credential Manager read failed with error {error}.")
    try:
        credential = pointer.contents
        if not credential.CredentialBlob or credential.CredentialBlobSize == 0:
            return None
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretStoreError("Stored Law-Rag provider credential is not valid UTF-8.") from exc
    finally:
        advapi.CredFree(pointer)


def write_secure_secret(provider: str, secret: str) -> None:
    normalized = _provider_name(provider)
    value = secret.strip()
    if not value:
        raise SecretStoreError("API key must not be empty.")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_GENERIC_SECRET_BYTES:
        raise SecretStoreError("API key is too large for Windows Credential Manager.")

    target = _PROVIDER_TARGET[normalized]
    advapi, credential_type = _credential_api()
    blob = ctypes.create_string_buffer(encoded)
    credential = credential_type()
    credential.Flags = 0
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.Comment = "Law-Rag protected local API credential"
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = "Law-Rag"
    if not advapi.CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise SecretStoreError(f"Windows Credential Manager write failed with error {error}.")


def delete_secure_secret(provider: str) -> None:
    target = _target(provider)
    advapi, _ = _credential_api()
    if not advapi.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return
        raise SecretStoreError(f"Windows Credential Manager delete failed with error {error}.")


def resolve_provider_secret(provider: str) -> ResolvedSecret:
    normalized = _provider_name(provider)
    env_name = _PROVIDER_ENV[normalized]
    environment_value = os.getenv(env_name, "").strip()
    if environment_value:
        return ResolvedSecret(value=environment_value, source="environment")
    if not secure_store_available():
        return ResolvedSecret(value=None, source=None)
    value = read_secure_secret(normalized)
    return ResolvedSecret(
        value=value.strip() if value and value.strip() else None,
        source="windows_credential_manager" if value and value.strip() else None,
    )
