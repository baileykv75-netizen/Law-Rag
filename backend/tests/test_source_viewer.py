from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.main import app
from app.models import OcrBlockEvidence, OcrPageEvidence, OcrPageState, OcrRunResult, SourceMethod


client = TestClient(app)


def _pdf_bytes() -> bytes:
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
        b"(Fictional clause requires payment within thirty days after acceptance.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _upload_pdf(tmp_path: Path, monkeypatch) -> dict:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    response = client.post(
        "/api/documents",
        files={"file": ("viewer-fixture.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_pdf_source_page_is_rendered_as_bounded_png(tmp_path: Path, monkeypatch) -> None:
    body = _upload_pdf(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{body['job_id']}/source/pages/1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert (tmp_path / "viewer" / body["job_id"] / "page-0001.png").exists()


def test_source_page_rejects_out_of_range_page(tmp_path: Path, monkeypatch) -> None:
    body = _upload_pdf(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{body['job_id']}/source/pages/2")

    assert response.status_code == 404
    assert "does not exist" in response.json()["detail"]


def test_native_evidence_resolves_to_canonical_span_and_object(tmp_path: Path, monkeypatch) -> None:
    body = _upload_pdf(tmp_path, monkeypatch)
    job_id = body["job_id"]
    evidence_id = body["pages"][0]["evidence_id"]
    quote = "payment within thirty days"
    span = SourceSpan(
        page_number=1,
        evidence_ids=[evidence_id],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=28,
        char_end=55,
    )
    contract = CanonicalContract(
        job_id=job_id,
        filename="viewer-fixture.pdf",
        source_fingerprint="viewer-source",
        evidence_unit_count=1,
        clauses=[
            Clause(
                clause_id="clause-viewer-001",
                heading_token="1",
                heading_text="Payment",
                body_text=quote,
                level=1,
                page_start=1,
                page_end=1,
                source_spans=[span],
                provenance=ExtractionProvenance(
                    extractor_id="fixture",
                    confidence=ExtractionConfidence.HIGH,
                ),
            )
        ],
    )
    (tmp_path / "jobs" / job_id / "contract.json").write_text(
        contract.model_dump_json(indent=2),
        encoding="utf-8",
    )

    response = client.get(f"/api/documents/{job_id}/evidence/{evidence_id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["page_number"] == 1
    assert detail["source_method"] == "native_pdf_text"
    assert detail["text"] == quote
    assert detail["char_start"] == 28
    assert detail["char_end"] == 55
    assert detail["bbox"] is None
    assert detail["canonical_references"] == [
        {"object_type": "clause", "object_id": "clause-viewer-001"}
    ]


def test_ocr_evidence_preserves_bbox_polygon_confidence_and_coordinate_space(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = b"\x89PNG\r\n\x1a\nfictional-viewer-image"
    upload = client.post(
        "/api/documents",
        files={"file": ("viewer-scan.png", payload, "image/png")},
    )
    assert upload.status_code == 201
    job_id = upload.json()["job_id"]

    ocr = OcrRunResult(
        job_id=job_id,
        provider="fake-ocr",
        model="fake-ocr-v1",
        provider_version="1.0",
        status="complete",
        page_count=1,
        native_pages=0,
        ocr_pages_attempted=1,
        ocr_pages_complete=1,
        low_confidence_pages=0,
        failed_pages=0,
        no_text_pages=0,
        pages=[
            OcrPageEvidence(
                page_number=1,
                state=OcrPageState.OCR_COMPLETE,
                source_method=SourceMethod.OCR,
                text="虚构付款条款",
                source_image_locator="source.png",
                width_px=200,
                height_px=100,
                blocks=[
                    OcrBlockEvidence(
                        evidence_id="ocr-viewer-p0001-b0001",
                        page_number=1,
                        block_index=1,
                        text="虚构付款条款",
                        confidence=0.96,
                        bbox=[10, 20, 110, 60],
                        polygon=[[10, 20], [110, 20], [110, 60], [10, 60]],
                        provider="fake-ocr",
                        model="fake-ocr-v1",
                        provider_version="1.0",
                        source_locator="page:1:block:1",
                    )
                ],
                mean_confidence=0.96,
                low_confidence_blocks=0,
            )
        ],
    )
    (tmp_path / "jobs" / job_id / "ocr.json").write_text(ocr.model_dump_json(indent=2), encoding="utf-8")

    response = client.get(f"/api/documents/{job_id}/evidence/ocr-viewer-p0001-b0001")

    assert response.status_code == 200
    detail = response.json()
    assert detail["page_number"] == 1
    assert detail["source_method"] == "ocr"
    assert detail["confidence"] == 0.96
    assert detail["bbox"] == [10, 20, 110, 60]
    assert detail["polygon"] == [[10, 20], [110, 20], [110, 60], [10, 60]]
    assert detail["coordinate_space_width_px"] == 200
    assert detail["coordinate_space_height_px"] == 100


def test_unknown_evidence_id_fails_explicitly(tmp_path: Path, monkeypatch) -> None:
    body = _upload_pdf(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{body['job_id']}/evidence/not-real")

    assert response.status_code == 404
    assert "cannot be resolved" in response.json()["detail"]
