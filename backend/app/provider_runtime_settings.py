from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .safe_persistence import atomic_write_text
from .storage import runtime_dir

PROVIDER_RUNTIME_SCHEMA_VERSION = "1.0.0"
PROVIDER_RUNTIME_ENGINE_VERSION = "stage18.4-1.0.0"

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-v4-flash"
KIMI_DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_DEFAULT_MODEL = "kimi-k3"

DEEPSEEK_DEFAULT_REQUEST_TIMEOUT_SECONDS = 90.0
KIMI_DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0

_PROVIDER_NAMES = ("deepseek", "kimi")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ProviderRuntimeSettingsError(RuntimeError):
    pass


class ProviderRuntimeSource(str, Enum):
    SAVED = "SAVED"
    ENVIRONMENT = "ENVIRONMENT"
    DEFAULT = "DEFAULT"


class ProviderRuntimeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    base_url: str = Field(min_length=1, max_length=512)
    request_timeout_seconds: float = Field(ge=15.0, le=300.0)
    connect_timeout_seconds: float = Field(ge=2.0, le=60.0)
    max_attempts: int = Field(ge=1, le=3)
    retry_backoff_seconds: float = Field(ge=0.0, le=10.0)


class ProviderRuntimeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PROVIDER_RUNTIME_SCHEMA_VERSION
    engine_version: str = PROVIDER_RUNTIME_ENGINE_VERSION
    providers: dict[str, ProviderRuntimeOptions]
    updated_at: datetime
    artifact_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_provider_keys(self) -> "ProviderRuntimeArtifact":
        actual = set(self.providers)
        expected = set(_PROVIDER_NAMES)
        if actual != expected:
            raise ValueError(
                f"Provider runtime artifact must contain exactly {sorted(expected)}; found {sorted(actual)}."
            )
        return self


class ProviderRuntimeResolved(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    source: ProviderRuntimeSource
    model: str
    base_url: str
    request_timeout_seconds: float
    connect_timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float
    supported_models: list[str]
    custom_endpoint: bool


class ProviderRuntimeOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PROVIDER_RUNTIME_SCHEMA_VERSION
    providers: list[ProviderRuntimeResolved]
    custom_endpoint_warning: str = (
        "A custom provider endpoint can receive the same bounded contract/legal evidence that would otherwise be sent to the official provider endpoint."
    )


class ProviderRuntimeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deepseek: ProviderRuntimeOptions
    kimi: ProviderRuntimeOptions
    confirm_custom_endpoints: bool = False


class ProviderRuntimeResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reset: bool
    overview: ProviderRuntimeOverview


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings_path() -> Path:
    return runtime_dir() / "config" / "provider-runtime.json"


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in _PROVIDER_NAMES:
        raise ProviderRuntimeSettingsError(f"Unsupported provider runtime settings: {provider}")
    return normalized


def _defaults(provider: str) -> ProviderRuntimeOptions:
    normalized = _provider_name(provider)
    if normalized == "deepseek":
        return ProviderRuntimeOptions(
            model=DEEPSEEK_DEFAULT_MODEL,
            base_url=DEEPSEEK_DEFAULT_BASE_URL,
            request_timeout_seconds=DEEPSEEK_DEFAULT_REQUEST_TIMEOUT_SECONDS,
            connect_timeout_seconds=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            retry_backoff_seconds=DEFAULT_RETRY_BACKOFF_SECONDS,
        )
    return ProviderRuntimeOptions(
        model=KIMI_DEFAULT_MODEL,
        base_url=KIMI_DEFAULT_BASE_URL,
        request_timeout_seconds=KIMI_DEFAULT_REQUEST_TIMEOUT_SECONDS,
        connect_timeout_seconds=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        retry_backoff_seconds=DEFAULT_RETRY_BACKOFF_SECONDS,
    )


def _env_names(provider: str) -> tuple[str, str, str]:
    normalized = _provider_name(provider)
    if normalized == "deepseek":
        return "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "LAW_RAG_DEEPSEEK_SUPPORTED_MODELS"
    return "MOONSHOT_MODEL", "MOONSHOT_BASE_URL", "LAW_RAG_KIMI_SUPPORTED_MODELS"


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if item and item not in seen:
            output.append(item)
            seen.add(item)
    return output


def supported_models(provider: str) -> list[str]:
    normalized = _provider_name(provider)
    defaults = _defaults(normalized)
    model_env, _, allowlist_env = _env_names(normalized)
    configured_model = os.getenv(model_env, "").strip()
    configured_allowlist = [item.strip() for item in os.getenv(allowlist_env, "").split(",")]
    return _unique([defaults.model, configured_model, *configured_allowlist])


def normalize_provider_base_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ProviderRuntimeSettingsError("Provider base URL must not be empty.")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise ProviderRuntimeSettingsError("Provider base URL is invalid.") from exc
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ProviderRuntimeSettingsError("Provider base URL must contain a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ProviderRuntimeSettingsError("Provider base URL must not contain embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ProviderRuntimeSettingsError("Provider base URL must not contain a query string or fragment.")
    if scheme != "https" and not (scheme == "http" and hostname in _LOOPBACK_HOSTS):
        raise ProviderRuntimeSettingsError(
            "Provider base URL must use HTTPS. Plain HTTP is allowed only for localhost/127.0.0.1/::1 development endpoints."
        )
    path = parsed.path.rstrip("/")
    if path.lower().endswith("/chat/completions"):
        raise ProviderRuntimeSettingsError("Provider base URL must be the API root, not the /chat/completions endpoint.")
    normalized = urlunsplit((scheme, parsed.netloc, path, "", ""))
    if len(normalized) > 512:
        raise ProviderRuntimeSettingsError("Provider base URL is too long.")
    return normalized


def _is_custom_endpoint(provider: str, base_url: str) -> bool:
    return normalize_provider_base_url(base_url) != normalize_provider_base_url(_defaults(provider).base_url)


def _config_dir_guard() -> Path:
    directory = runtime_dir() / "config"
    if directory.exists() and directory.is_symlink():
        raise ProviderRuntimeSettingsError("Runtime config directory must not be a symlink.")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _read_saved() -> ProviderRuntimeArtifact | None:
    path = _settings_path()
    if path.is_symlink():
        raise ProviderRuntimeSettingsError("provider-runtime.json must not be a symlink.")
    if not path.exists():
        return None
    try:
        artifact = ProviderRuntimeArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ProviderRuntimeSettingsError("Persisted provider-runtime.json is invalid.") from exc
    payload = artifact.model_dump(mode="json", exclude={"artifact_fingerprint"})
    if artifact.artifact_fingerprint != _fingerprint(payload):
        raise ProviderRuntimeSettingsError("Persisted provider-runtime.json fingerprint is invalid.")
    return artifact


def _persist(providers: dict[str, ProviderRuntimeOptions]) -> ProviderRuntimeArtifact:
    _config_dir_guard()
    path = _settings_path()
    if path.is_symlink():
        raise ProviderRuntimeSettingsError("provider-runtime.json must not be a symlink.")
    payload = {
        "schema_version": PROVIDER_RUNTIME_SCHEMA_VERSION,
        "engine_version": PROVIDER_RUNTIME_ENGINE_VERSION,
        "providers": {name: options.model_dump(mode="json") for name, options in providers.items()},
        "updated_at": _now(),
    }
    artifact = ProviderRuntimeArtifact(**payload, artifact_fingerprint="0" * 64)
    canonical_payload = artifact.model_dump(mode="json", exclude={"artifact_fingerprint"})
    artifact.artifact_fingerprint = _fingerprint(canonical_payload)
    atomic_write_text(path, artifact.model_dump_json(indent=2))
    return artifact


def _environment_options(provider: str) -> tuple[ProviderRuntimeOptions, bool]:
    defaults = _defaults(provider)
    model_env, base_env, _ = _env_names(provider)
    model_value = os.getenv(model_env, "").strip()
    base_value = os.getenv(base_env, "").strip()
    model = model_value or defaults.model
    if model not in supported_models(provider):
        raise ProviderRuntimeSettingsError(f"Configured model {model!r} is not in the supported model list for {provider}.")
    base_url = normalize_provider_base_url(base_value or defaults.base_url)
    return (
        ProviderRuntimeOptions(
            model=model,
            base_url=base_url,
            request_timeout_seconds=defaults.request_timeout_seconds,
            connect_timeout_seconds=defaults.connect_timeout_seconds,
            max_attempts=defaults.max_attempts,
            retry_backoff_seconds=defaults.retry_backoff_seconds,
        ),
        bool(model_value or base_value),
    )


def resolve_provider_runtime(provider: str) -> ProviderRuntimeResolved:
    normalized = _provider_name(provider)
    saved = _read_saved()
    if saved is not None:
        options = saved.providers[normalized]
        source = ProviderRuntimeSource.SAVED
    else:
        options, used_environment = _environment_options(normalized)
        source = ProviderRuntimeSource.ENVIRONMENT if used_environment else ProviderRuntimeSource.DEFAULT
    base_url = normalize_provider_base_url(options.base_url)
    models = supported_models(normalized)
    if options.model not in models:
        # A previously saved model remains explicit and visible rather than being
        # silently replaced when a deployment allowlist later changes.
        models = _unique([*models, options.model])
    return ProviderRuntimeResolved(
        provider=normalized,
        source=source,
        model=options.model,
        base_url=base_url,
        request_timeout_seconds=options.request_timeout_seconds,
        connect_timeout_seconds=options.connect_timeout_seconds,
        max_attempts=options.max_attempts,
        retry_backoff_seconds=options.retry_backoff_seconds,
        supported_models=models,
        custom_endpoint=_is_custom_endpoint(normalized, base_url),
    )


def provider_runtime_overview() -> ProviderRuntimeOverview:
    return ProviderRuntimeOverview(providers=[resolve_provider_runtime(name) for name in _PROVIDER_NAMES])


def _validate_for_save(provider: str, options: ProviderRuntimeOptions) -> ProviderRuntimeOptions:
    normalized = _provider_name(provider)
    models = supported_models(normalized)
    if options.model not in models:
        raise ProviderRuntimeSettingsError(
            f"Model {options.model!r} is not an allowed {normalized} model. Select one of the server-reported supported models."
        )
    return ProviderRuntimeOptions(
        model=options.model,
        base_url=normalize_provider_base_url(options.base_url),
        request_timeout_seconds=options.request_timeout_seconds,
        connect_timeout_seconds=options.connect_timeout_seconds,
        max_attempts=options.max_attempts,
        retry_backoff_seconds=options.retry_backoff_seconds,
    )


def save_provider_runtime_settings(request: ProviderRuntimeUpdateRequest) -> ProviderRuntimeOverview:
    deepseek = _validate_for_save("deepseek", request.deepseek)
    kimi = _validate_for_save("kimi", request.kimi)
    custom = [
        name
        for name, options in (("deepseek", deepseek), ("kimi", kimi))
        if _is_custom_endpoint(name, options.base_url)
    ]
    if custom and not request.confirm_custom_endpoints:
        raise ProviderRuntimeSettingsError(
            "Custom provider endpoint confirmation is required because bounded contract/legal evidence may be transmitted to: "
            + ", ".join(custom)
            + "."
        )
    _persist({"deepseek": deepseek, "kimi": kimi})
    return provider_runtime_overview()


def reset_provider_runtime_settings() -> ProviderRuntimeResetResponse:
    path = _settings_path()
    if path.is_symlink():
        raise ProviderRuntimeSettingsError("provider-runtime.json must not be a symlink.")
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            raise ProviderRuntimeSettingsError("Could not reset provider runtime settings.") from exc
    return ProviderRuntimeResetResponse(reset=True, overview=provider_runtime_overview())
