from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contract_models import SourceSpan
from app.evidence_models import (
    DocxParagraphAnchor,
    DocxTableCellAnchor,
    PageRegionAnchor,
    PageTextAnchor,
    SourceDocumentIdentity,
    SourceEvidence,
    adapt_legacy_paginated_evidence,
    source_anchor_locator,
)
from app.models import (
    DocumentKind,
    OcrBlockEvidence,
    OcrPageEvidence,
    OcrPageState,
    OcrRunResult,
    PageEvidence,
    PageRoute,
    SourceMethod,
)


def _source_document(kind: DocumentKind = DocumentKind.PDF) -> SourceDocumentIdentity:
    return SourceDocumentIdentity(
        job_id=uuid4(),
        filename="fictional-contract.pdf" if kind == DocumentKind.PDF else "fictional-contract.docx",
        media_type=(
            "application/pdf"
            if kind == DocumentKind.PDF
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        document_kind=kind,
        source_sha256="a" * 64,
        size_bytes=1234,
    )


def test_docx_paragraph_evidence_has_typed_anchor_without_fake_page() -> None:
    anchor = DocxParagraphAnchor(
        paragraph_index=37,
        char_start=4,
        char_end=12,
    )
    evidence = SourceEvidence(
        evidence_id="ev-docx-paragraph-37",
        order_index=1,
        text="乙方应于七日内完成验收",
        source_method=SourceMethod.NATIVE_DOCX_TEXT,
        source_anchor=anchor,
    )
    span = SourceSpan(
        evidence_ids=[evidence.evidence_id],
        source_method=SourceMethod.NATIVE_DOCX_TEXT,
        quote="七日内",
        source_anchor=anchor,
        char_start=4,
        char_end=7,
    )

    assert evidence.source_locator == "docx:document:paragraph:000037"
    assert span.page_number is None
    assert span.source_anchor.kind == "DOCX_PARAGRAPH"


def test_docx_table_cell_locator_preserves_table_structure() -> None:
    anchor = DocxTableCellAnchor(
        table_index=2,
        row_index=3,
        cell_index=2,
        paragraph_index=1,
    )

    assert source_anchor_locator(anchor) == (
        "docx:document:table:0002:row:0003:cell:0002:paragraph:0001"
    )


def test_source_evidence_rejects_locator_that_disagrees_with_anchor() -> None:
    with pytest.raises(ValidationError):
        SourceEvidence(
            evidence_id="ev-mismatch",
            order_index=1,
            text="fictional",
            source_method=SourceMethod.NATIVE_DOCX_TEXT,
            source_anchor=DocxParagraphAnchor(paragraph_index=2),
            source_locator="docx:document:paragraph:999999",
        )


def test_source_span_rejects_page_number_that_disagrees_with_page_anchor() -> None:
    with pytest.raises(ValidationError):
        SourceSpan(
            page_number=2,
            evidence_ids=["ev-page-1"],
            source_method=SourceMethod.NATIVE_PDF_TEXT,
            quote="fictional",
            source_anchor=PageTextAnchor(page_number=1),
        )


def test_legacy_native_page_adapts_without_changing_evidence_identity() -> None:
    source = _source_document()
    page = PageEvidence(
        evidence_id="ev-legacy-native-p0001",
        page_number=1,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text="第一条 虚构付款条款",
        character_count=10,
        non_whitespace_count=9,
        meaningful_ratio=1.0,
        suspicious_character_count=0,
        route=PageRoute.NATIVE_TEXT_USABLE,
        route_reason="fixture",
        source_locator="page:1",
    )

    artifact = adapt_legacy_paginated_evidence(
        source_document=source,
        page_evidence=[page],
    )

    assert artifact.job_id == source.job_id
    assert len(artifact.evidence) == 1
    adapted = artifact.evidence[0]
    assert adapted.evidence_id == page.evidence_id
    assert isinstance(adapted.source_anchor, PageTextAnchor)
    assert adapted.source_anchor.page_number == 1
    assert adapted.source_locator == "page:0001:text"


def test_legacy_ocr_block_adapts_to_page_region_anchor() -> None:
    source = _source_document()
    page = PageEvidence(
        evidence_id="ev-legacy-p0001",
        page_number=1,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text="",
        character_count=0,
        non_whitespace_count=0,
        meaningful_ratio=0.0,
        suspicious_character_count=0,
        route=PageRoute.OCR_REQUIRED,
        route_reason="fixture",
        source_locator="page:1",
    )
    block = OcrBlockEvidence(
        evidence_id="ocr-legacy-p0001-b0001",
        page_number=1,
        block_index=1,
        text="虚构扫描条款",
        confidence=0.97,
        bbox=[10, 20, 100, 60],
        polygon=[[10, 20], [100, 20], [100, 60], [10, 60]],
        provider="fake",
        model="fake-v1",
        provider_version="1.0",
        source_locator="page:1;pixel_bbox:10,20,100,60",
    )
    ocr = OcrRunResult(
        job_id=source.job_id,
        provider="fake",
        model="fake-v1",
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
                text=block.text,
                blocks=[block],
                width_px=120,
                height_px=80,
            )
        ],
    )

    artifact = adapt_legacy_paginated_evidence(
        source_document=source,
        page_evidence=[page],
        ocr_result=ocr,
    )

    assert len(artifact.evidence) == 1
    adapted = artifact.evidence[0]
    assert adapted.evidence_id == block.evidence_id
    assert isinstance(adapted.source_anchor, PageRegionAnchor)
    assert adapted.source_anchor.bbox == [10, 20, 100, 60]
    assert adapted.confidence == 0.97
