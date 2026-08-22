from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.ai_audit_providers as legacy_primary
import app.issue_primary_audit_provider as issue_primary
import app.issue_secondary_review_provider as issue_secondary
import app.provider_settings as provider_settings
import app.secondary_review_providers as legacy_secondary
from app.main import app
from app.provider_runtime_settings import (
    DEEPSEEK_DEFAULT_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
    KIMI_DEFAULT_BASE_URL,
    KIMI_DEFAULT_MODEL,
    ProviderRuntimeOptions,
    ProviderRuntimeSettingsError,
    ProviderRuntimeSource,
    ProviderRuntimeUpdateRequest,
    normalize_provider_base_url,
    provider_runtime_overview,
    reset_provider_runtime_settings,
    resolve_provider_runtime,
    save_provider_runtime_settings,
)
from app.secret_store import ResolvedSecret

client = TestClient(app)


def _clean_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    for name in (
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "MOONSHOT_MODEL",
        "MOONSHOT_BASE_URL",
        "LAW_RAG_DEEPSEEK_SUPPORTED_MODELS",
        "LAW_RAG_KIMI_SUPPORTED_MODELS",
        "DEEPSEEK_API_KEY",
        "MOONSHOT_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _options(
    provider: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    request_timeout: float | None = None,
    connect_timeout: float = 15.0,
    attempts: int = 2,
    backoff: float = 1.0,
) -> ProviderRuntimeOptions:
    if provider == "deepseek":
        return ProviderRuntimeOptions(
            model=model or DEEPSEEK_DEFAULT_MODEL,
            base_url=base_url or DEEPSEEK_DEFAULT_BASE_URL,
            request_timeout_seconds=request_timeout or 90.0,
            connect_timeout_seconds=connect_timeout,
            max_attempts=attempts,
            retry_backoff_seconds=backoff,
        )
    return ProviderRuntimeOptions(
        model=model or KIMI_DEFAULT_MODEL,
        base_url=base_url or KIMI_DEFAULT_BASE_URL,
        request_timeout_seconds=request_timeout or 120.0,
        connect_timeout_seconds=connect_timeout,
        max_attempts=attempts,
        retry_backoff_seconds=backoff,
    )


def _request(**overrides) -> ProviderRuntimeUpdateRequest:
    return ProviderRuntimeUpdateRequest(
        deepseek=overrides.get("deepseek", _options("deepseek")),
        kimi=overrides.get("kimi", _options("kimi")),
        confirm_custom_endpoints=overrides.get("confirm_custom_endpoints", False),
    )


def test_default_overview_is_non_mutating_and_explicit(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)

    overview = provider_runtime_overview()

    assert [item.source for item in overview.providers] == [
        ProviderRuntimeSource.DEFAULT,
        ProviderRuntimeSource.DEFAULT,
    ]
    assert overview.providers[0].model == DEEPSEEK_DEFAULT_MODEL
    assert overview.providers[1].model == KIMI_DEFAULT_MODEL
    assert not (tmp_path / "config" / "provider-runtime.json").exists()


def test_legacy_environment_remains_visible_without_saved_override(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPSEEK_MODEL", "deployment-deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://gateway.example.test/deepseek")

    resolved = resolve_provider_runtime("deepseek")

    assert resolved.source == ProviderRuntimeSource.ENVIRONMENT
    assert resolved.model == "deployment-deepseek"
    assert "deployment-deepseek" in resolved.supported_models
    assert resolved.base_url == "https://gateway.example.test/deepseek"
    assert resolved.custom_endpoint is True


def test_saved_settings_precede_legacy_environment(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPSEEK_MODEL", "environment-model")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://environment.example.test/v1")
    monkeypatch.setenv("LAW_RAG_DEEPSEEK_SUPPORTED_MODELS", "saved-model")

    save_provider_runtime_settings(
        _request(
            deepseek=_options(
                "deepseek",
                model="saved-model",
                base_url=DEEPSEEK_DEFAULT_BASE_URL,
                request_timeout=77,
                connect_timeout=9,
                attempts=3,
                backoff=2.5,
            )
        )
    )

    resolved = resolve_provider_runtime("deepseek")
    assert resolved.source == ProviderRuntimeSource.SAVED
    assert resolved.model == "saved-model"
    assert resolved.base_url == DEEPSEEK_DEFAULT_BASE_URL
    assert resolved.request_timeout_seconds == 77
    assert resolved.connect_timeout_seconds == 9
    assert resolved.max_attempts == 3
    assert resolved.retry_backoff_seconds == 2.5


def test_persisted_runtime_file_contains_no_secret_fields(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    save_provider_runtime_settings(_request())

    path = tmp_path / "config" / "provider-runtime.json"
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "api_key" not in lowered
    assert "authorization" not in lowered
    assert "credential" not in lowered
    assert "secret" not in lowered
    assert "deepseek-v4-pro" in text
    assert "kimi-k3" in text

    # A second read validates the persisted fingerprint and full two-provider shape.
    assert provider_runtime_overview().providers[0].source == ProviderRuntimeSource.SAVED


def test_unsupported_model_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)

    with pytest.raises(ProviderRuntimeSettingsError, match="not an allowed"):
        save_provider_runtime_settings(
            _request(deepseek=_options("deepseek", model="arbitrary-unknown-model"))
        )


def test_allowlisted_model_can_be_selected(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("LAW_RAG_DEEPSEEK_SUPPORTED_MODELS", "deepseek-approved-alt")

    overview = save_provider_runtime_settings(
        _request(deepseek=_options("deepseek", model="deepseek-approved-alt"))
    )

    deepseek = next(item for item in overview.providers if item.provider == "deepseek")
    assert deepseek.model == "deepseek-approved-alt"
    assert deepseek.source == ProviderRuntimeSource.SAVED


def test_custom_https_endpoint_requires_explicit_confirmation(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    request = _request(
        deepseek=_options("deepseek", base_url="https://proxy.example.test/v1")
    )

    with pytest.raises(ProviderRuntimeSettingsError, match="confirmation is required"):
        save_provider_runtime_settings(request)

    saved = save_provider_runtime_settings(
        request.model_copy(update={"confirm_custom_endpoints": True})
    )
    deepseek = next(item for item in saved.providers if item.provider == "deepseek")
    assert deepseek.custom_endpoint is True
    assert deepseek.base_url == "https://proxy.example.test/v1"


def test_loopback_http_is_allowed_only_with_custom_endpoint_confirmation(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    request = _request(
        kimi=_options("kimi", base_url="http://127.0.0.1:9000/v1")
    )
    with pytest.raises(ProviderRuntimeSettingsError, match="confirmation is required"):
        save_provider_runtime_settings(request)

    overview = save_provider_runtime_settings(
        request.model_copy(update={"confirm_custom_endpoints": True})
    )
    kimi = next(item for item in overview.providers if item.provider == "kimi")
    assert kimi.base_url == "http://127.0.0.1:9000/v1"


@pytest.mark.parametrize(
    "value",
    [
        "http://provider.example.test/v1",
        "ftp://provider.example.test/v1",
        "https://user:password@provider.example.test/v1",
        "https://provider.example.test/v1?token=secret",
        "https://provider.example.test/v1#fragment",
        "https://provider.example.test/v1/chat/completions",
    ],
)
def test_unsafe_or_ambiguous_base_urls_are_rejected(value: str) -> None:
    with pytest.raises(ProviderRuntimeSettingsError):
        normalize_provider_base_url(value)


def test_runtime_api_rejects_unknown_or_secret_fields(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    payload = {
        "deepseek": _options("deepseek").model_dump(mode="json"),
        "kimi": _options("kimi").model_dump(mode="json"),
        "confirm_custom_endpoints": False,
        "deepseek_api_key": "must-not-be-accepted-here",
    }

    response = client.put("/api/config/providers/runtime", json=payload)

    assert response.status_code == 422
    assert not (tmp_path / "config" / "provider-runtime.json").exists()


def test_runtime_api_save_and_reset_never_touch_network(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)

    class ExplodingClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("saving runtime settings must not instantiate an HTTP client")

    monkeypatch.setattr(provider_settings.httpx, "Client", ExplodingClient)
    payload = {
        "deepseek": _options("deepseek").model_dump(mode="json"),
        "kimi": _options("kimi").model_dump(mode="json"),
        "confirm_custom_endpoints": False,
    }

    saved = client.put("/api/config/providers/runtime", json=payload)
    assert saved.status_code == 200
    assert all(item["source"] == "SAVED" for item in saved.json()["providers"])

    reset = client.delete("/api/config/providers/runtime")
    assert reset.status_code == 200
    assert reset.json()["reset"] is True
    assert all(item["source"] == "DEFAULT" for item in reset.json()["overview"]["providers"])


def test_runtime_api_validates_bounds(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    bad = _options("deepseek").model_dump(mode="json")
    bad["max_attempts"] = 4
    response = client.put(
        "/api/config/providers/runtime",
        json={
            "deepseek": bad,
            "kimi": _options("kimi").model_dump(mode="json"),
            "confirm_custom_endpoints": False,
        },
    )
    assert response.status_code == 422


def test_reset_returns_to_environment_resolution(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPSEEK_MODEL", "env-after-reset")
    save_provider_runtime_settings(_request())

    response = reset_provider_runtime_settings()

    assert response.reset is True
    deepseek = next(item for item in response.overview.providers if item.provider == "deepseek")
    assert deepseek.source == ProviderRuntimeSource.ENVIRONMENT
    assert deepseek.model == "env-after-reset"


def test_symlinked_runtime_settings_file_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    config = tmp_path / "config"
    config.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    settings_path = config / "provider-runtime.json"
    try:
        settings_path.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")

    with pytest.raises(ProviderRuntimeSettingsError, match="symlink"):
        provider_runtime_overview()
    assert outside.read_text(encoding="utf-8") == "{}"


def test_provider_overview_reports_saved_runtime_without_secrets(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-deepseek")
    monkeypatch.setenv("MOONSHOT_API_KEY", "secret-kimi")
    save_provider_runtime_settings(
        _request(deepseek=_options("deepseek", request_timeout=75))
    )

    response = client.get("/api/config/providers")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert "secret-deepseek" not in serialized
    assert "secret-kimi" not in serialized
    assert {item["runtime_source"] for item in response.json()["providers"]} == {"SAVED"}


def test_connectivity_probe_uses_saved_runtime_but_only_fixed_probe_message(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("LAW_RAG_DEEPSEEK_SUPPORTED_MODELS", "deepseek-probe-model")
    save_provider_runtime_settings(
        _request(
            deepseek=_options(
                "deepseek",
                model="deepseek-probe-model",
                base_url="https://probe.example.test/v1",
                request_timeout=55,
                connect_timeout=7,
            ),
            confirm_custom_endpoints=True,
        )
    )

    captured: dict = {}

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(provider_settings.httpx, "Client", FakeClient)
    result = provider_settings.test_provider_connection(
        provider_settings.ProviderTestRequest(
            provider=provider_settings.ProviderName.DEEPSEEK,
            api_key="probe-only-secret",
        )
    )

    assert result.success is True
    assert captured["url"] == "https://probe.example.test/v1/chat/completions"
    assert captured["json"]["model"] == "deepseek-probe-model"
    serialized_payload = json.dumps(captured["json"], ensure_ascii=False)
    assert "No contract data is included" in serialized_payload
    assert "audit_context" not in serialized_payload
    assert "probe-only-secret" not in result.model_dump_json()


def test_all_real_adapters_resolve_the_same_saved_runtime_settings(tmp_path: Path, monkeypatch) -> None:
    _clean_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("LAW_RAG_DEEPSEEK_SUPPORTED_MODELS", "deepseek-runtime-alt")
    monkeypatch.setenv("LAW_RAG_KIMI_SUPPORTED_MODELS", "kimi-runtime-alt")
    save_provider_runtime_settings(
        _request(
            deepseek=_options(
                "deepseek",
                model="deepseek-runtime-alt",
                request_timeout=66,
                connect_timeout=8,
                attempts=3,
                backoff=2,
            ),
            kimi=_options(
                "kimi",
                model="kimi-runtime-alt",
                request_timeout=88,
                connect_timeout=9,
                attempts=1,
                backoff=0,
            ),
        )
    )

    def resolved(provider: str) -> ResolvedSecret:
        return ResolvedSecret(value=f"{provider}-secret", source="test")

    monkeypatch.setattr(issue_primary, "resolve_provider_secret", resolved)
    monkeypatch.setattr(issue_secondary, "resolve_provider_secret", resolved)
    monkeypatch.setattr(legacy_primary, "resolve_provider_secret", resolved)
    monkeypatch.setattr(legacy_secondary, "resolve_provider_secret", resolved)

    issue_deepseek = issue_primary.DeepSeekIssuePrimaryProvider()
    legacy_deepseek = legacy_primary.DeepSeekProvider()
    issue_kimi = issue_secondary.KimiIssueSecondaryReviewProvider()
    legacy_kimi = legacy_secondary.KimiSecondaryReviewProvider()

    for provider in (issue_deepseek, legacy_deepseek):
        assert provider.model_name == "deepseek-runtime-alt"
        assert provider.base_url == DEEPSEEK_DEFAULT_BASE_URL
        assert provider.request_timeout_seconds == 66
        assert provider.connect_timeout_seconds == 8
        assert provider.max_attempts == 3
        assert provider.retry_backoff_seconds == 2

    for provider in (issue_kimi, legacy_kimi):
        assert provider.model_name == "kimi-runtime-alt"
        assert provider.base_url == KIMI_DEFAULT_BASE_URL
        assert provider.request_timeout_seconds == 88
        assert provider.connect_timeout_seconds == 9
        assert provider.max_attempts == 1
        assert provider.retry_backoff_seconds == 0

    # Evidence-output safety ceilings remain application-owned, not user-configurable.
    assert issue_primary.ISSUE_PRIMARY_MAX_TOKENS == 3500
    assert issue_secondary.DEFAULT_KIMI_MAX_COMPLETION_TOKENS == 8000
    assert legacy_primary.DEFAULT_MAX_TOKENS == 6000
    assert legacy_secondary.DEFAULT_KIMI_MAX_COMPLETION_TOKENS == 12000
