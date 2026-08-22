from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from .provider_runtime_settings import (
    DEEPSEEK_DEFAULT_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    KIMI_DEFAULT_BASE_URL,
    KIMI_DEFAULT_MODEL,
    ProviderRuntimeSettingsError,
    resolve_provider_runtime,
)
from .safe_persistence import atomic_write_text
from .secret_store import (
    SecretStoreError,
    SecretStoreUnavailable,
    delete_secure_secret,
    resolve_provider_secret,
    secure_store_available,
    write_secure_secret,
)
from .storage import runtime_dir

SETUP_STATE_SCHEMA_VERSION = "1.0.0"
DEFAULT_DEEPSEEK_BASE_URL = DEEPSEEK_DEFAULT_BASE_URL
DEFAULT_DEEPSEEK_MODEL = DEEPSEEK_DEFAULT_MODEL
DEFAULT_KIMI_BASE_URL = KIMI_DEFAULT_BASE_URL
DEFAULT_KIMI_MODEL = KIMI_DEFAULT_MODEL


class ProviderName(str, Enum):
    DEEPSEEK = "deepseek"
    KIMI = "kimi"


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderConfigurationItem(BaseModel):
    provider: ProviderName
    configured: bool
    source: str | None = None
    model: str
    base_url: str
    runtime_source: str


class ProviderConfigurationOverview(BaseModel):
    setup_completed: bool
    requires_setup: bool
    secure_storage_available: bool
    providers: list[ProviderConfigurationItem]


class ProviderSaveRequest(BaseModel):
    deepseek_api_key: str | None = Field(default=None, max_length=2400)
    kimi_api_key: str | None = Field(default=None, max_length=2400)
    complete_setup: bool = True


class ProviderTestRequest(BaseModel):
    provider: ProviderName
    api_key: str | None = Field(default=None, max_length=2400)


class ProviderTestResult(BaseModel):
    provider: ProviderName
    success: bool
    detail: str


def _state_path() -> Path:
    return runtime_dir() / "config" / "provider-setup.json"


def _load_setup_completed() -> bool:
    path = _state_path()
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("schema_version") == SETUP_STATE_SCHEMA_VERSION
        and payload.get("setup_completed") is True
    )


def mark_setup_complete() -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SETUP_STATE_SCHEMA_VERSION,
        "setup_completed": True,
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _runtime(provider: ProviderName):
    try:
        return resolve_provider_runtime(provider.value)
    except ProviderRuntimeSettingsError as exc:
        raise ProviderConfigurationError(str(exc)) from exc


def _resolve(provider: ProviderName):
    try:
        return resolve_provider_secret(provider.value)
    except (SecretStoreError, SecretStoreUnavailable) as exc:
        raise ProviderConfigurationError(str(exc)) from exc


def provider_overview() -> ProviderConfigurationOverview:
    items: list[ProviderConfigurationItem] = []
    for provider in (ProviderName.DEEPSEEK, ProviderName.KIMI):
        resolved = _resolve(provider)
        runtime = _runtime(provider)
        items.append(
            ProviderConfigurationItem(
                provider=provider,
                configured=bool(resolved.value),
                source=resolved.source,
                model=runtime.model,
                base_url=runtime.base_url,
                runtime_source=runtime.source.value,
            )
        )
    completed = _load_setup_completed()
    all_configured = all(item.configured for item in items)
    return ProviderConfigurationOverview(
        setup_completed=completed,
        requires_setup=not completed and not all_configured,
        secure_storage_available=secure_store_available(),
        providers=items,
    )


def save_provider_configuration(request: ProviderSaveRequest) -> ProviderConfigurationOverview:
    secrets = {
        ProviderName.DEEPSEEK: request.deepseek_api_key,
        ProviderName.KIMI: request.kimi_api_key,
    }
    if any(value is not None and value.strip() for value in secrets.values()) and not secure_store_available():
        raise ProviderConfigurationError(
            "Protected API-key saving is only supported through Windows Credential Manager in the desktop release. "
            "Development environments may continue using DEEPSEEK_API_KEY/MOONSHOT_API_KEY."
        )
    try:
        for provider, value in secrets.items():
            if value is not None and value.strip():
                write_secure_secret(provider.value, value)
    except (SecretStoreError, SecretStoreUnavailable) as exc:
        raise ProviderConfigurationError(str(exc)) from exc
    if request.complete_setup:
        mark_setup_complete()
    return provider_overview()


def delete_provider_configuration(provider: ProviderName) -> ProviderConfigurationOverview:
    if not secure_store_available():
        raise ProviderConfigurationError("Windows Credential Manager is not available on this platform.")
    try:
        delete_secure_secret(provider.value)
    except (SecretStoreError, SecretStoreUnavailable) as exc:
        raise ProviderConfigurationError(str(exc)) from exc
    return provider_overview()


def _probe_payload(provider: ProviderName, model: str) -> dict:
    messages = [
        {
            "role": "user",
            "content": "Reply with OK only. This is a Law-Rag API connectivity test. No contract data is included.",
        }
    ]
    if provider == ProviderName.DEEPSEEK:
        return {
            "model": model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "max_tokens": 8,
            "stream": False,
        }
    return {
        "model": model,
        "messages": messages,
        "max_completion_tokens": 16,
        "stream": False,
    }


def test_provider_connection(request: ProviderTestRequest) -> ProviderTestResult:
    supplied = (request.api_key or "").strip()
    if supplied:
        api_key = supplied
    else:
        api_key = _resolve(request.provider).value or ""
    if not api_key:
        return ProviderTestResult(
            provider=request.provider,
            success=False,
            detail="未提供或保存 API Key。",
        )

    runtime = _runtime(request.provider)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(
            timeout=httpx.Timeout(runtime.request_timeout_seconds, connect=runtime.connect_timeout_seconds)
        ) as client:
            response = client.post(
                f"{runtime.base_url}/chat/completions",
                headers=headers,
                json=_probe_payload(request.provider, runtime.model),
            )
    except httpx.HTTPError:
        return ProviderTestResult(
            provider=request.provider,
            success=False,
            detail="无法连接提供商 API；请检查网络、代理或服务地址。",
        )

    if 200 <= response.status_code < 300:
        return ProviderTestResult(
            provider=request.provider,
            success=True,
            detail="连接成功。测试请求不包含任何合同内容。",
        )
    if response.status_code in {401, 403}:
        detail = "认证失败，请检查 API Key 是否正确且仍有效。"
    elif response.status_code == 429:
        detail = "已连接到提供商，但当前请求被限流或账户额度受限。"
    else:
        detail = f"提供商返回 HTTP {response.status_code}；未读取或回显响应正文。"
    return ProviderTestResult(provider=request.provider, success=False, detail=detail)
