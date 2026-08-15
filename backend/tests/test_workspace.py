from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.main import app


client = TestClient(app)


def _native_pdf_bytes() -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = StreamObject()
    stream._data = (
        b"BT /F1 12 Tf 72 720 Td "
        b"(Fictional contract payment terms require performance within thirty days after acceptance.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _upload_native_job(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    response = client.post(
        "/api/documents",
        files={"file": ("workspace-fixture.pdf", _native_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["job_id"]


def test_workspace_load_is_read_only_and_explicitly_partial(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_native_job(tmp_path, monkeypatch)

    # Workspace navigation must not depend on or invoke either external provider.
    def forbidden_provider_call(*args, **kwargs):
        raise AssertionError("workspace GET must not resolve or call an external model provider")

    monkeypatch.setattr("app.ai_audit_providers.provider_from_name", forbidden_provider_call)
    monkeypatch.setattr("app.secondary_review_providers.secondary_provider_from_name", forbidden_provider_call)

    response = client.get(f"/api/documents/{job_id}/workspace")
    assert response.status_code == 200
    body = response.json()

    assert body["job_id"] == job_id
    assert body["overall_state"] == "INCOMPLETE"
    assert body["source_available"] is True
    assert body["document"]["filename"] == "workspace-fixture.pdf"
    assert body["document"]["page_count"] == 1
    assert body["document"]["ocr_used"] is False
    assert body["review"]["primary_available"] is False
    assert body["review"]["secondary_available"] is False
    assert body["review"]["comparison_available"] is False

    stages = {item["stage"]: item for item in body["stages"]}
    assert stages["2"]["state"] == "READY"
    assert stages["3"]["state"] == "NOT_REQUIRED"
    assert stages["4"]["state"] == "MISSING"
    assert stages["5"]["state"] == "MISSING"
    assert stages["8"]["state"] == "MISSING"
    assert stages["9A/B"]["state"] == "MISSING"
    assert stages["9C/D"]["state"] == "MISSING"


def test_unknown_workspace_job_returns_404_without_creating_runtime_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()

    response = client.get(f"/api/documents/{job_id}/workspace")

    assert response.status_code == 404
    assert not (tmp_path / "jobs" / str(job_id)).exists()
    assert not (tmp_path / "uploads" / str(job_id)).exists()


def test_workspace_surfaces_invalid_artifact_instead_of_hiding_it(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_native_job(tmp_path, monkeypatch)
    job_dir = tmp_path / "jobs" / job_id
    (job_dir / "contract.json").write_text("{}", encoding="utf-8")

    response = client.get(f"/api/documents/{job_id}/workspace")

    assert response.status_code == 200
    body = response.json()
    stages = {item["stage"]: item for item in body["stages"]}
    assert stages["4"]["state"] == "INVALID"
    assert body["overall_state"] == "INVALID"


def test_stage9_routes_remain_mounted_on_main_application(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    # A missing report should be a domain 404, not a FastAPI route 404 with "Not Found".
    job_id = uuid4()
    response = client.get(f"/api/documents/{job_id}/review-report")

    assert response.status_code == 404
    assert "review-report.json" in response.json()["detail"]
