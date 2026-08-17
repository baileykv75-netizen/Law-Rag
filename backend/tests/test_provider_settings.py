from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.provider_settings import ProviderName, ProviderTestRequest, test_provider_connection

client = TestClient(app)


def test_provider_status_never_returns_secret_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-super-secret-value")
    monkeypatch.setenv("MOONSHOT_API_KEY", "kimi-super-secret-value")

    response = client.get("/api/config/providers")
    assert response.status_code == 200
    body = response.json()
    serialized = json.dumps(body)
    assert "ds-super-secret-value" not in serialized
    assert "kimi-super-secret-value" not in serialized
    assert body["requires_setup"] is False
    assert all(item["configured"] for item in body["providers"])
    assert {item["source"] for item in body["providers"]} == {"environment"}


def test_skip_setup_persists_only_non_secret_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    response = client.post("/api/config/providers/skip")
    assert response.status_code == 200
    assert response.json()["setup_completed"] is True
    state_path = tmp_path / "config" / "provider-setup.json"
    payload = state_path.read_text(encoding="utf-8")
    assert "setup_completed" in payload
    assert "api_key" not in payload.lower()
    assert "secret" not in payload.lower()


def test_save_api_uses_protected_store_and_does_not_write_keys_to_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    import app.provider_settings as settings

    stored: dict[str, str] = {}
    monkeypatch.setattr(settings, "secure_store_available", lambda: True)
    monkeypatch.setattr(settings, "write_secure_secret", lambda provider, value: stored.__setitem__(provider, value))

    def resolved(provider: str):
        from app.secret_store import ResolvedSecret

        value = stored.get(provider)
        return ResolvedSecret(value=value, source="windows_credential_manager" if value else None)

    monkeypatch.setattr(settings, "resolve_provider_secret", resolved)

    response = client.put(
        "/api/config/providers",
        json={
            "deepseek_api_key": "ds-secret-123",
            "kimi_api_key": "kimi-secret-456",
            "complete_setup": True,
        },
    )
    assert response.status_code == 200
    assert stored == {"deepseek": "ds-secret-123", "kimi": "kimi-secret-456"}
    serialized = json.dumps(response.json())
    assert "ds-secret-123" not in serialized
    assert "kimi-secret-456" not in serialized
    for path in tmp_path.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "ds-secret-123" not in text
            assert "kimi-secret-456" not in text


def test_connectivity_probe_uses_only_fixed_non_contract_message(monkeypatch) -> None:
    import app.provider_settings as settings

    captured: dict = {}

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(settings.httpx, "Client", FakeClient)
    result = test_provider_connection(
        ProviderTestRequest(provider=ProviderName.DEEPSEEK, api_key="probe-secret")
    )
    assert result.success is True
    serialized_payload = json.dumps(captured["json"], ensure_ascii=False)
    assert "No contract data is included" in serialized_payload
    assert "contract_evidence" not in serialized_payload
    assert "audit_context" not in serialized_payload
    assert captured["headers"]["Authorization"] == "Bearer probe-secret"
    assert "probe-secret" not in result.model_dump_json()
