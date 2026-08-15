from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.main import app
from app.models import OcrPageState
from app.ocr import (
    OcrProviderError,
    PaddleOcrProvider,
    ProviderOcrBlock,
    run_ocr_for_job,
)

client = TestClient(app)


def _png_bytes(width: int = 320, height: int = 120) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


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


def _upload_image(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    response = client.post(
        "/api/documents",
        files={"file": ("fictional-scan.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 201
    return response.json()["job_id"]


class FakeProvider:
    provider_name = "fake-ocr"
    model_name = "fake-model"
    provider_version = "1.0"

    def __init__(self, *, confidence: float = 0.97, empty: bool = False) -> None:
        self.confidence = confidence
        self.empty = empty
        self.calls: list[tuple[Path, int]] = []

    def recognize(self, image_path: Path, page_number: int) -> list[ProviderOcrBlock]:
        self.calls.append((image_path, page_number))
        if self.empty:
            return []
        return [
            ProviderOcrBlock(
                text=f"Fictional OCR text page {page_number}",
                confidence=self.confidence,
                bbox=[10, 20, 210, 52],
                polygon=[[10, 20], [210, 20], [210, 52], [10, 52]],
            )
        ]


class FailingProvider(FakeProvider):
    def recognize(self, image_path: Path, page_number: int) -> list[ProviderOcrBlock]:
        self.calls.append((image_path, page_number))
        raise OcrProviderError("Synthetic provider failure.")


def test_image_ocr_preserves_text_coordinates_confidence_and_persistence(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_image(tmp_path, monkeypatch)
    provider = FakeProvider(confidence=0.97)

    result = run_ocr_for_job(UUID(job_id), provider=provider)

    assert result.status == "complete"
    assert result.ocr_pages_attempted == 1
    assert result.ocr_pages_complete == 1
    assert result.failed_pages == 0
    assert result.pages[0].state == OcrPageState.OCR_COMPLETE
    assert result.pages[0].page_number == 1
    assert result.pages[0].width_px == 320
    assert result.pages[0].height_px == 120
    block = result.pages[0].blocks[0]
    assert block.evidence_id == f"ocr-{job_id}-p0001-b0001"
    assert block.text == "Fictional OCR text page 1"
    assert block.confidence == 0.97
    assert block.bbox == [10, 20, 210, 52]
    assert block.polygon == [[10, 20], [210, 20], [210, 52], [10, 52]]
    assert block.source_locator == "page:1;pixel_bbox:10,20,210,52"
    assert not block.low_confidence

    persisted = json.loads((tmp_path / "jobs" / job_id / "ocr.json").read_text(encoding="utf-8"))
    assert persisted["pages"][0]["blocks"][0]["bbox"] == [10, 20, 210, 52]
    assert persisted["pages"][0]["blocks"][0]["confidence"] == 0.97


def test_low_confidence_block_is_explicit(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_image(tmp_path, monkeypatch)
    result = run_ocr_for_job(UUID(job_id), provider=FakeProvider(confidence=0.42))

    assert result.low_confidence_pages == 1
    assert result.pages[0].state == OcrPageState.OCR_LOW_CONFIDENCE
    assert result.pages[0].low_confidence_blocks == 1
    assert result.pages[0].blocks[0].low_confidence
    assert "below the Stage 3 review threshold" in (result.pages[0].blocks[0].low_confidence_reason or "")


def test_no_text_ocr_result_is_explicit(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_image(tmp_path, monkeypatch)
    result = run_ocr_for_job(UUID(job_id), provider=FakeProvider(empty=True))

    assert result.status == "partial"
    assert result.no_text_pages == 1
    assert result.pages[0].state == OcrPageState.OCR_NO_TEXT
    assert result.pages[0].text == ""
    assert result.pages[0].error is not None


def test_ocr_failure_is_persisted_as_page_failure(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_image(tmp_path, monkeypatch)
    result = run_ocr_for_job(UUID(job_id), provider=FailingProvider())

    assert result.status == "failed"
    assert result.failed_pages == 1
    assert result.pages[0].state == OcrPageState.OCR_FAILED
    assert result.pages[0].error == "Synthetic provider failure."


def test_mixed_pdf_keeps_native_page_and_renders_only_ocr_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = _pdf_bytes([_native_text(), None])
    response = client.post(
        "/api/documents",
        files={"file": ("fictional-mixed.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["route"] == "MIXED"

    provider = FakeProvider()
    result = run_ocr_for_job(UUID(body["job_id"]), provider=provider)

    assert [page.page_number for page in result.pages] == [1, 2]
    assert result.pages[0].state == OcrPageState.NATIVE_RETAINED
    assert result.pages[0].native_evidence_id == f"ev-{body['job_id']}-p0001"
    assert "Fictional contract" in result.pages[0].text
    assert result.pages[1].state == OcrPageState.OCR_COMPLETE
    assert [page_number for _, page_number in provider.calls] == [2]

    rendered_dir = tmp_path / "rendered" / body["job_id"]
    assert not (rendered_dir / "page-0001.png").exists()
    rendered_page = rendered_dir / "page-0002.png"
    assert rendered_page.exists()
    with Image.open(rendered_page) as image:
        assert image.width > 0
        assert image.height > 0


def test_paddle_adapter_normalizes_official_result_fields_without_real_model() -> None:
    class FakePipeline:
        def predict(self, image_path: str):
            return [
                {
                    "rec_texts": ["合同金额100元"],
                    "rec_scores": [0.934],
                    "rec_boxes": [[8, 12, 188, 44]],
                    "rec_polys": [[[8, 12], [188, 12], [188, 44], [8, 44]]],
                }
            ]

    provider = PaddleOcrProvider(
        pipeline_factory=lambda: FakePipeline(),
        provider_version="3.7.0-test",
    )
    blocks = provider.recognize(Path("synthetic.png"), 1)

    assert len(blocks) == 1
    assert blocks[0].text == "合同金额100元"
    assert blocks[0].confidence == 0.934
    assert blocks[0].bbox == [8, 12, 188, 44]
    assert blocks[0].polygon == [[8, 12], [188, 12], [188, 44], [8, 44]]
