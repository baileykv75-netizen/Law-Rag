from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentKind(str, Enum):
    PDF = "pdf"
    IMAGE = "image"


class PageRoute(str, Enum):
    NATIVE_TEXT_USABLE = "NATIVE_TEXT_USABLE"
    OCR_REQUIRED = "OCR_REQUIRED"
    EMPTY_OR_UNSUPPORTED = "EMPTY_OR_UNSUPPORTED"


class DocumentRoute(str, Enum):
    NATIVE_TEXT = "NATIVE_TEXT"
    OCR_REQUIRED = "OCR_REQUIRED"
    MIXED = "MIXED"


class SourceMethod(str, Enum):
    NATIVE_PDF_TEXT = "native_pdf_text"
    IMAGE_SOURCE = "image_source"


class PageEvidence(BaseModel):
    evidence_id: str
    page_number: int = Field(ge=1)
    source_method: SourceMethod
    text: str
    character_count: int = Field(ge=0)
    non_whitespace_count: int = Field(ge=0)
    meaningful_ratio: float = Field(ge=0.0, le=1.0)
    suspicious_character_count: int = Field(ge=0)
    route: PageRoute
    route_reason: str
    source_locator: str


class PageEvidenceSummary(BaseModel):
    evidence_id: str
    page_number: int
    route: PageRoute
    character_count: int
    route_reason: str


class DocumentInspection(BaseModel):
    job_id: UUID
    filename: str
    media_type: str
    document_kind: DocumentKind
    page_count: int = Field(ge=1)
    route: DocumentRoute
    native_text_pages: int = Field(ge=0)
    ocr_required_pages: int = Field(ge=0)
    pages: list[PageEvidence]
    status: str = "inspected"


class IngestResponse(BaseModel):
    job_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    status: str
    storage_scope: str
    document_kind: DocumentKind
    page_count: int
    route: DocumentRoute
    native_text_pages: int
    ocr_required_pages: int
    pages: list[PageEvidenceSummary]
