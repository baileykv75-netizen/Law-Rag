from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path

from .runtime_encryption_models import (
    RUNTIME_ENCRYPTION_SCHEMA_VERSION,
    RuntimeEncryptionMode,
    RuntimeEncryptionOverview,
    RuntimeEncryptionState,
)
from .safe_persistence import atomic_write_text
from .storage import runtime_dir

# These roots contain contract/user-derived data. The public legal corpus is
# intentionally excluded so its frozen hashes/reproducibility remain stable.
_MANAGED_ROOT_NAMES = ("jobs", "uploads", "rendered", "batches", "cleanup", "exports")
_CONFIG_FILE = "runtime-security.json"

FILE_ENCRYPTABLE = 0
FILE_IS_ENCRYPTED = 1
FILE_SYSTEM_NOT_SUPPORT = 6
_EFS_UNSUPPORTED_ERRORS = {1, 50, 87, 120}


class RuntimeEncryptionError(RuntimeError):
    pass


class RuntimeEncryptionRequiredError(RuntimeEncryptionError):
    pass


def _config_path() -> Path:
    return runtime_dir() / "config" / _CONFIG_FILE


def _configured_mode() -> RuntimeEncryptionMode:
    override = os.getenv("LAW_RAG_RUNTIME_ENCRYPTION_MODE", "").strip().upper()
    if override:
        try:
            return RuntimeEncryptionMode(override)
        except ValueError as exc:
            raise RuntimeEncryptionError(
                "LAW_RAG_RUNTIME_ENCRYPTION_MODE must be OFF, AUTO, or REQUIRED."
            ) from exc

    path = _config_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != RUNTIME_ENCRYPTION_SCHEMA_VERSION:
                raise ValueError("unsupported schema")
            return RuntimeEncryptionMode(str(payload["mode"]))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RuntimeEncryptionError("Persisted runtime encryption settings are invalid.") from exc

    # Local-first privacy default: transparently protect Job-private roots on
    # Windows editions/filesystems that support EFS. Unsupported editions stay
    # usable but are reported explicitly as UNSUPPORTED rather than protected.
    return RuntimeEncryptionMode.AUTO


def _persist_mode(mode: RuntimeEncryptionMode) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {"schema_version": RUNTIME_ENCRYPTION_SCHEMA_VERSION, "mode": mode.value},
            ensure_ascii=False,
            indent=2,
        ),
    )


def _windows_api():
    if sys.platform != "win32":
        raise RuntimeEncryptionError("Windows EFS is only available on Windows.")
    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi.EncryptFileW.argtypes = [wintypes.LPCWSTR]
    advapi.EncryptFileW.restype = wintypes.BOOL
    advapi.FileEncryptionStatusW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    advapi.FileEncryptionStatusW.restype = wintypes.BOOL
    return advapi


def _status(path: Path) -> tuple[int | None, int | None]:
    if sys.platform != "win32":
        return None, None
    advapi = _windows_api()
    value = wintypes.DWORD()
    if not advapi.FileEncryptionStatusW(str(path), ctypes.byref(value)):
        return None, ctypes.get_last_error()
    return int(value.value), None


def _encrypt(path: Path) -> None:
    advapi = _windows_api()
    if not advapi.EncryptFileW(str(path)):
        error = ctypes.get_last_error()
        raise RuntimeEncryptionError(f"Windows EFS EncryptFileW failed for {path.name} with error {error}.")


def _assert_safe_tree(root: Path) -> list[Path]:
    """Return a stable pre-order list and fail closed on any symlink.

    EFS follows filesystem objects by path. Law-Rag never intentionally stores
    symlinks in Job-private runtime roots; refusing them prevents an attacker or
    corrupted runtime from making encryption traverse outside the managed root.
    """

    if root.is_symlink():
        raise RuntimeEncryptionError(f"Managed runtime root is a symlink: {root.name}")
    paths = [root]
    if not root.exists():
        return paths
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            child = current_path / name
            if child.is_symlink():
                raise RuntimeEncryptionError(f"Symlink is not allowed inside protected runtime data: {child}")
            paths.append(child)
        for name in filenames:
            child = current_path / name
            if child.is_symlink():
                raise RuntimeEncryptionError(f"Symlink is not allowed inside protected runtime data: {child}")
            paths.append(child)
    return paths


def _protect_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    # Encrypt directories before their descendants so new files created during
    # or after this pass inherit EFS automatically. Existing descendants are
    # still visited explicitly because marking a directory alone does not make
    # an unverifiable blanket claim about old content.
    paths = _assert_safe_tree(root)
    directories = [item for item in paths if item.is_dir()]
    files = [item for item in paths if item.is_file()]
    for path in [*directories, *files]:
        status, error = _status(path)
        if error is not None:
            raise RuntimeEncryptionError(f"Could not inspect EFS status for {path.name}; Windows error {error}.")
        if status != FILE_IS_ENCRYPTED:
            _encrypt(path)
        verified, verify_error = _status(path)
        if verify_error is not None or verified != FILE_IS_ENCRYPTED:
            raise RuntimeEncryptionError(f"EFS protection could not be verified for {path.name}.")


def _inspect_roots(mode: RuntimeEncryptionMode) -> RuntimeEncryptionOverview:
    root = runtime_dir()
    protected: list[str] = []
    unprotected: list[str] = []
    warnings: list[str] = []

    if mode == RuntimeEncryptionMode.OFF:
        return RuntimeEncryptionOverview(
            mode=mode,
            state=RuntimeEncryptionState.DISABLED,
            platform=sys.platform,
            managed_root_names=list(_MANAGED_ROOT_NAMES),
            detail="Law-Rag managed runtime encryption is disabled. Existing OS-level encryption is not removed automatically.",
        )

    if sys.platform != "win32":
        return RuntimeEncryptionOverview(
            mode=mode,
            state=RuntimeEncryptionState.UNSUPPORTED,
            platform=sys.platform,
            managed_root_names=list(_MANAGED_ROOT_NAMES),
            unprotected_root_names=list(_MANAGED_ROOT_NAMES),
            detail="Windows EFS runtime encryption is unavailable on this platform.",
            warnings=["No Job-private runtime root is claimed as encrypted by Law-Rag on this platform."],
        )

    for name in _MANAGED_ROOT_NAMES:
        path = root / name
        if not path.exists():
            unprotected.append(name)
            continue
        if path.is_symlink():
            unprotected.append(name)
            warnings.append(f"{name} is a symlink and cannot be trusted as a managed encrypted root.")
            continue
        status, error = _status(path)
        if error is None and status == FILE_IS_ENCRYPTED:
            protected.append(name)
        else:
            unprotected.append(name)
            if error is not None:
                warnings.append(f"Could not inspect {name} EFS state; Windows error {error}.")
            elif status == FILE_SYSTEM_NOT_SUPPORT:
                warnings.append(f"The filesystem hosting {name} does not support EFS.")

    if protected and not unprotected:
        state = RuntimeEncryptionState.ENCRYPTED
        detail = "All Law-Rag managed Job-private runtime roots are protected by Windows EFS."
    elif protected:
        state = RuntimeEncryptionState.DEGRADED
        detail = "Only part of the Law-Rag managed Job-private runtime is protected by Windows EFS."
    else:
        state = RuntimeEncryptionState.UNSUPPORTED if warnings else RuntimeEncryptionState.DEGRADED
        detail = "Law-Rag cannot currently verify EFS protection for its managed Job-private runtime roots."

    return RuntimeEncryptionOverview(
        mode=mode,
        state=state,
        platform=sys.platform,
        managed_root_names=list(_MANAGED_ROOT_NAMES),
        protected_root_names=protected,
        unprotected_root_names=unprotected,
        detail=detail,
        warnings=warnings,
    )


def runtime_encryption_overview() -> RuntimeEncryptionOverview:
    return _inspect_roots(_configured_mode())


def apply_runtime_encryption(mode: RuntimeEncryptionMode | None = None) -> RuntimeEncryptionOverview:
    selected = mode or _configured_mode()
    if selected == RuntimeEncryptionMode.OFF:
        return _inspect_roots(selected)

    if sys.platform != "win32":
        overview = _inspect_roots(selected)
        if selected == RuntimeEncryptionMode.REQUIRED:
            raise RuntimeEncryptionRequiredError(overview.detail)
        return overview

    protected: list[str] = []
    failed_names: list[str] = []
    failures: list[str] = []
    unsupported = False
    for name in _MANAGED_ROOT_NAMES:
        path = runtime_dir() / name
        try:
            _protect_root(path)
            protected.append(name)
        except RuntimeEncryptionError as exc:
            failed_names.append(name)
            failures.append(str(exc))
            message = str(exc)
            if any(f"error {code}" in message for code in _EFS_UNSUPPORTED_ERRORS):
                unsupported = True
            if selected == RuntimeEncryptionMode.REQUIRED:
                raise RuntimeEncryptionRequiredError(
                    f"Required runtime encryption could not protect {name}: {exc}"
                ) from exc

    overview = _inspect_roots(selected)
    warnings = [*overview.warnings, *failures]
    if failures:
        verified_protected = [name for name in overview.protected_root_names if name not in failed_names]
        verified_unprotected = sorted(set([*overview.unprotected_root_names, *failed_names]))
        state = RuntimeEncryptionState.DEGRADED if verified_protected else (
            RuntimeEncryptionState.UNSUPPORTED if unsupported else RuntimeEncryptionState.DEGRADED
        )
        overview = overview.model_copy(
            update={
                "state": state,
                "protected_root_names": verified_protected,
                "unprotected_root_names": verified_unprotected,
                "detail": (
                    "Runtime encryption is only partially active; see warnings."
                    if verified_protected
                    else "Windows EFS could not be enabled for the managed Job-private runtime."
                ),
                "warnings": sorted(set(warnings)),
            }
        )
    return overview


def set_runtime_encryption_mode(mode: RuntimeEncryptionMode) -> RuntimeEncryptionOverview:
    # Validate/apply before persisting REQUIRED so an unsupported machine is not
    # deliberately converted into a startup-blocking configuration by a failed
    # settings request.
    overview = apply_runtime_encryption(mode)
    _persist_mode(mode)
    return overview


def ensure_runtime_encryption_on_startup() -> RuntimeEncryptionOverview:
    mode = _configured_mode()
    return apply_runtime_encryption(mode)
