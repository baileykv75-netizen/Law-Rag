from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .models import DocumentKind, OcrRunResult, PageEvidence, PageRoute, SourceMethod


SOURCE_EVIDENCE_SCHEMA_VERSION = "2.0.0"


class SourceDocumentIdentity(BaseModel):
    """Stable identity for the local source file behind evidence."""

    job_id: UUID
    filename: str
    media_type: str
    document_kind: DocumentKind
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class PageTextAnchor(BaseModel):
    kind: Literal["PAGE_TEXT"] = "PAGE_TEXT"
    page_number: int = Field(ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "PageTextAnchor":
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class PageRegionAnchor(BaseModel):
    kind: Literal["PAGE_REGION"] = "PAGE_REGION"
    page_number: int = Field(ge=1)
    bbox: list[int] | None = None
    polygon: list[list[int]] | None = None


class DocxParagraphAnchor(BaseModel):
    kind: Literal["DOCX_PARAGRAPH"] = "DOCX_PARAGRAPH"
    part: str = Field(default="document", min_length=1)
    paragraph_index: int = Field(ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "DocxParagraphAnchor":
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class DocxTableCellAnchor(BaseModel):
    kind: Literal["DOCX_TABLE_CELL"] = "DOCX_TABLE_CELL"
    part: str = Field(default="document", min_length=1)
    table_index: int = Field(ge=1)
    row_index: int = Field(ge=1)
    cell_index: int = Field(ge=1)
    paragraph_index: int = Field(ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "DocxTableCellAnchor":
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class DocxEmbeddedImageAnchor(BaseModel):
    kind: Literal["DOCX_EMBEDDED_IMAGE"] = "DOCX_EMBEDDED_IMAGE"
    part: str = Field(default="document", min_length=1)
    image_index: int = Field(ge=1)
    relationship_id: str | None = None
    parent_locator: str | None = None


SourceAnchor = Annotated[
    PageTextAnchor
    | PageRegionAnchor
    | DocxParagraphAnchor
    | DocxTableCellAnchor
    | DocxEmbeddedImageAnchor,
    Field(discriminator="kind"),
]


def source_anchor_locator(anchor: SourceAnchor) -> str:
    if isinstance(anchor, PageTextAnchor):
        return f"page:{anchor.page_number:04d}:text"
    if isinstance(anchor, PageRegionAnchor):
        return f"page:{anchor.page_number:04d}:region"
    if isinstance(anchor, DocxParagraphAnchor):
        return f"docx:{anchor.part}:paragraph:{anchor.paragraph_index:06d}"
    if isinstance(anchor, DocxTableCellAnchor):
        return (
            f"docx:{anchor.part}:table:{anchor.table_index:04d}"
            f":row:{anchor.row_index:04d}:cell:{anchor.cell_index:04d}"
            f":paragraph:{anchor.paragraph_index:04d}"
        )
    if isinstance(anchor, DocxEmbeddedImageAnchor):
        return f"docx:{anchor.part}:image:{anchor.image_index:04d}"
    raise TypeError(f"Unsupported source anchor type: {type(anchor).__name__}")


def source_anchor_page_number(anchor: SourceAnchor | None) -> int | None:
    if isinstance(anchor, (PageTextAnchor, PageRegionAnchor)):
        return anchor.page_number
    return None


class SourceEvidence(BaseModel):
    """Cross-format evidence identity plus an explicit typed source anchor.

    Evidence IDs are opaque identities. Callers must use ``source_anchor`` to
    locate source material instead of parsing location semantics out of the ID.
    """

    schema_version: str = SOURCE_EVIDENCE_SCHEMA_VERSION
    evidence_id: str = Field(min_length=1)
    order_index: int = Field(ge=1)
    text: str
    source_method: SourceMethod
    source_anchor: SourceAnchor
    source_locator: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    block_kind: Literal["TEXT", "TABLE_CELL", "IMAGE"] = "TEXT"
    parent_group_id: str | None = None

    @model_validator(mode="after")
    def normalize_locator(self) -> "SourceEvidence":
        canonical = source_anchor_locator(self.source_anchor)
        if self.source_locator is None:
            self.source_locator = canonical
        elif self.source_locator != canonical:
            raise ValueError("source_locator must match the canonical typed source_anchor locator")
        return self


class SourceEvidenceArtifact(BaseModel):
    schema_version: str = SOURCE_EVIDENCE_SCHEMA_VERSION
    job_id: UUID
    source_document: SourceDocumentIdentity
    evidence: list[SourceEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_job_identity(self) -> "SourceEvidenceArtifact":
        if self.job_id != self.source_document.job_id:
            raise ValueError("source document job_id does not match evidence artifact job_id")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique within one source evidence artifact")
        return self


def adapt_legacy_paginated_evidence(
    *,
    source_document: SourceDocumentIdentity,
    page_evidence: list[PageEvidence],
    ocr_result: OcrRunResult | None = None,
) -> SourceEvidenceArtifact:
    """Adapt persisted Stage 2/3 PDF/image evidence without rewriting it.

    Native PDF pages retain their existing Evidence IDs. OCR-required pages
    contribute the OCR block Evidence IDs when a completed OCR artifact is
    available; page placeholders are not promoted into usable text evidence.
    """

    ocr_pages = {page.page_number: page for page in (ocr_result.pages if ocr_result else [])}
    evidence: list[SourceEvidence] = []
    order_index = 1

    for page in sorted(page_evidence, key=lambda item: item.page_number):
        if page.route == PageRoute.NATIVE_TEXT_USABLE:
            evidence.append(
                SourceEvidence(
                    evidence_id=page.evidence_id,
                    order_index=order_index,
                    text=page.text,
                    source_method=page.source_method,
                    source_anchor=PageTextAnchor(page_number=page.page_number),
                )
            )
            order_index += 1
            continue

        ocr_page = ocr_pages.get(page.page_number)
        if ocr_page is None:
            continue
        for block in sorted(ocr_page.blocks, key=lambda item: item.block_index):
            evidence.append(
                SourceEvidence(
                    evidence_id=block.evidence_id,
                    order_index=order_index,
                    text=block.text,
                    source_method=block.source_method,
                    source_anchor=PageRegionAnchor(
                        page_number=block.page_number,
                        bbox=block.bbox,
                        polygon=block.polygon,
                    ),
                    confidence=block.confidence,
                )
            )
            order_index += 1

    return SourceEvidenceArtifact(
        job_id=source_document.job_id,
        source_document=source_document,
        evidence=evidence,
    )
