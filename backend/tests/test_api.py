from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.main import app

client = TestClient(app)


def _pdf_bytes(page_texts: list[str | None]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)

    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue

        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
        )
        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = StreamObject()
        stream._data = f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET".encode("latin-1")
        page[NameObject("/Contents")] = writer._add_object(stream)

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _native_text() -> str:
    return (
        "Fictional contract payment obligation requires Party A to pay Party B "
        "100000 units within thirty days after acceptance. "
    )


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_native_text_pdf_is_classified_and_persisted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = _pdf_bytes([_native_text()])

    response = client.post(
        "/api/documents",
        files={"file": ("fictional-contract.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "fictional-contract.pdf"
    assert body["status"] == "inspected"
    assert body["document_kind"] == "pdf"
    assert body["page_count"] == 1
    assert body["route"] == "NATIVE_TEXT"
    assert body["native_text_pages"] == 1
    assert body["ocr_required_pages"] == 0
    assert body["pages"][0]["route"] == "NATIVE_TEXT_USABLE"

    job_id = body["job_id"]
    stored = tmp_path / "uploads" / job_id / "source.pdf"
    document_path = tmp_path / "jobs" / job_id / "document.json"
    evidence_path = tmp_path / "jobs" / job_id / "evidence.json"
    assert stored.read_bytes() == payload
    assert document_path.exists()
    assert evidence_path.exists()

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence[0]["page_number"] == 1
    assert evidence[0]["evidence_id"] == f"ev-{job_id}-p0001"
    assert evidence[0]["route"] == "NATIVE_TEXT_USABLE"
    assert "Fictional contract" in evidence[0]["text"]


def test_image_is_routed_to_future_ocr(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = b"\x89PNG\r\n\x1a\nfictional-stage-2-image"

    response = client.post(
        "/api/documents",
        files={"file": ("fictional-scan.png", payload, "image/png")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document_kind"] == "image"
    assert body["page_count"] == 1
    assert body["route"] == "OCR_REQUIRED"
    assert body["native_text_pages"] == 0
    assert body["ocr_required_pages"] == 1
    assert body["pages"][0]["route"] == "OCR_REQUIRED"


def test_pdf_without_usable_text_is_routed_to_ocr(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = _pdf_bytes([None])

    response = client.post(
        "/api/documents",
        files={"file": ("fictional-scan.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["route"] == "OCR_REQUIRED"
    assert body["page_count"] == 1
    assert body["ocr_required_pages"] == 1
    assert "No native text" in body["pages"][0]["route_reason"]


def test_mixed_pdf_preserves_page_routes_and_stable_evidence_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = _pdf_bytes([_native_text(), None])

    response = client.post(
        "/api/documents",
        files={"file": ("fictional-mixed.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["route"] == "MIXED"
    assert body["page_count"] == 2
    assert body["native_text_pages"] == 1
    assert body["ocr_required_pages"] == 1
    assert [page["page_number"] for page in body["pages"]] == [1, 2]
    assert [page["route"] for page in body["pages"]] == [
        "NATIVE_TEXT_USABLE",
        "OCR_REQUIRED",
    ]
    assert body["pages"][0]["evidence_id"].endswith("-p0001")
    assert body["pages"][1]["evidence_id"].endswith("-p0002")


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


def test_corrupt_pdf_returns_explicit_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))

    response = client.post(
        "/api/documents",
        files={"file": ("corrupt.pdf", b"%PDF-1.7\nthis is corrupt", "application/pdf")},
    )

    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]
