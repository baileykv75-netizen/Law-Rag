from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .evidence_models import (
    DocxEmbeddedImageAnchor,
    DocxParagraphAnchor,
    DocxTableCellAnchor,
    SourceAnchor,
    SourceEvidenceWarning,
)
from .models import SourceMethod


SOURCE_VIEWER_SCHEMA_VERSION = "1.2.0"


class CanonicalEvidenceReference(BaseModel):
    object_type: str
    object_id: str


class SourceEvidenceDetail(BaseModel):
    schema_version: str = SOURCE_VIEWER_SCHEMA_VERSION
    evidence_id: str
    page_number: int | None = Field(default=None, ge=1)
    source_method: SourceMethod
    text: str
    source_anchor: SourceAnchor | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bbox: list[int] | None = None
    polygon: list[list[int]] | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    source_locator: str | None = None
    coordinate_space_width_px: int | None = Field(default=None, ge=1)
    coordinate_space_height_px: int | None = Field(default=None, ge=1)
    canonical_references: list[CanonicalEvidenceReference] = Field(default_factory=list)


class DocxLogicalParagraph(BaseModel):
    kind: Literal["PARAGRAPH"] = "PARAGRAPH"
    order_index: int = Field(ge=1)
    evidence_id: str
    text: str
    source_locator: str
    source_anchor: DocxParagraphAnchor


class DocxLogicalCellParagraph(BaseModel):
    order_index: int = Field(ge=1)
    evidence_id: str
    text: str
    source_locator: str
    source_anchor: DocxTableCellAnchor


class DocxLogicalTableCell(BaseModel):
    row_index: int = Field(ge=1)
    cell_index: int = Field(ge=1)
    paragraphs: list[DocxLogicalCellParagraph] = Field(default_factory=list)


class DocxLogicalTableRow(BaseModel):
    row_index: int = Field(ge=1)
    cells: list[DocxLogicalTableCell] = Field(default_factory=list)


class DocxLogicalTable(BaseModel):
    kind: Literal["TABLE"] = "TABLE"
    order_index: int = Field(ge=1)
    table_index: int = Field(ge=1)
    group_id: str
    rows: list[DocxLogicalTableRow] = Field(default_factory=list)


class DocxLogicalImage(BaseModel):
    kind: Literal["IMAGE"] = "IMAGE"
    order_index: int = Field(ge=1)
    evidence_id: str
    source_locator: str
    source_anchor: DocxEmbeddedImageAnchor


DocxLogicalBlock = DocxLogicalParagraph | DocxLogicalTable | DocxLogicalImage


class DocxSourceView(BaseModel):
    schema_version: str = SOURCE_VIEWER_SCHEMA_VERSION
    job_id: UUID
    document_kind: Literal["docx"] = "docx"
    filename: str
    pagination: Literal["LOGICAL_NO_STABLE_PAGES"] = "LOGICAL_NO_STABLE_PAGES"
    evidence_count: int = Field(ge=0)
    coverage_complete: bool
    warnings: list[SourceEvidenceWarning] = Field(default_factory=list)
    blocks: list[DocxLogicalBlock] = Field(default_factory=list)
