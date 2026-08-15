from __future__ import annotations

from pydantic import BaseModel, Field

from .models import SourceMethod


SOURCE_VIEWER_SCHEMA_VERSION = "1.0.0"


class CanonicalEvidenceReference(BaseModel):
    object_type: str
    object_id: str


class SourceEvidenceDetail(BaseModel):
    schema_version: str = SOURCE_VIEWER_SCHEMA_VERSION
    evidence_id: str
    page_number: int = Field(ge=1)
    source_method: SourceMethod
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bbox: list[int] | None = None
    polygon: list[list[int]] | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    source_locator: str | None = None
    coordinate_space_width_px: int | None = Field(default=None, ge=1)
    coordinate_space_height_px: int | None = Field(default=None, ge=1)
    canonical_references: list[CanonicalEvidenceReference] = Field(default_factory=list)
