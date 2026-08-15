from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_runtime_health_endpoint_is_local_non_mutating_and_secret_safe(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))
    monkeypatch.delenv("LAW_RAG_LEGAL_DB", raising=False)
    monkeypatch.delenv("LAW_RAG_RETRIEVAL_DB", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "endpoint-deepseek-secret")
    monkeypatch.setenv("MOONSHOT_API_KEY", "endpoint-kimi-secret")

    response = client.get("/api/runtime/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["base_app_ready"] is True
    assert {item["check_id"] for item in payload["checks"]} >= {
        "python-runtime",
        "runtime-directory",
        "legal-database",
        "retrieval-database",
        "ocr-runtime",
        "semantic-runtime",
        "deepseek-provider",
        "kimi-provider",
    }
    rendered = response.text
    assert "endpoint-deepseek-secret" not in rendered
    assert "endpoint-kimi-secret" not in rendered
    assert not runtime.exists(), "GET diagnostics must not create runtime state"
