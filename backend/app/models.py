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
    OCR = "ocr"


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


class OcrPageState(str, Enum):
    NATIVE_RETAINED = "NATIVE_RETAINED"
    OCR_COMPLETE = "OCR_COMPLETE"
    OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
    OCR_NO_TEXT = "OCR_NO_TEXT"
    OCR_FAILED = "OCR_FAILED"


class OcrBlockEvidence(BaseModel):
    evidence_id: str
    page_number: int = Field(ge=1)
    block_index: int = Field(ge=1)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bbox: list[int] | None = None
    polygon: list[list[int]] | None = None
    provider: str
    model: str
    provider_version: str
    source_method: SourceMethod = SourceMethod.OCR
    low_confidence: bool = False
    low_confidence_reason: str | None = None
    source_locator: str


class OcrPageEvidence(BaseModel):
    page_number: int = Field(ge=1)
    state: OcrPageState
    source_method: SourceMethod
    text: str
    native_evidence_id: str | None = None
    source_image_locator: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    blocks: list[OcrBlockEvidence] = Field(default_factory=list)
    mean_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    low_confidence_blocks: int = Field(default=0, ge=0)
    error: str | None = None


class OcrRunResult(BaseModel):
    job_id: UUID
    provider: str
    model: str
    provider_version: str
    status: str
    page_count: int = Field(ge=1)
    native_pages: int = Field(ge=0)
    ocr_pages_attempted: int = Field(ge=0)
    ocr_pages_complete: int = Field(ge=0)
    low_confidence_pages: int = Field(ge=0)
    failed_pages: int = Field(ge=0)
    no_text_pages: int = Field(ge=0)
    pages: list[OcrPageEvidence]
