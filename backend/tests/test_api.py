from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_supported_pdf_upload_is_stored_locally(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = b"%PDF-1.4\n% fictional stage-1 test\n"

    response = client.post(
        "/api/documents",
        files={"file": ("fictional-contract.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "fictional-contract.pdf"
    assert body["media_type"] == "application/pdf"
    assert body["size_bytes"] == len(payload)
    assert body["status"] == "stored"
    assert body["storage_scope"] == "local-runtime-only"

    stored = tmp_path / "uploads" / body["job_id"] / "source.pdf"
    assert stored.exists()
    assert stored.read_bytes() == payload


def test_unsupported_extension_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))

    response = client.post(
        "/api/documents",
        files={"file": ("notes.txt", b"not a contract", "text/plain")},
    )

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]
    assert not (tmp_path / "uploads").exists()


def test_fake_pdf_signature_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))

    response = client.post(
        "/api/documents",
        files={"file": ("fake.pdf", b"this is not a pdf", "application/pdf")},
    )

    assert response.status_code == 415
    assert "contents do not match" in response.json()["detail"]
