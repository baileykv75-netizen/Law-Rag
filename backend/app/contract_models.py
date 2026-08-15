from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .models import SourceMethod

CONTRACT_SCHEMA_VERSION = "1.0.0"
EXTRACTOR_VERSION = "stage4-1.0.0"


class ExtractionConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNRESOLVED = "UNRESOLVED"


class ResolutionState(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


class SourceSpan(BaseModel):
    page_number: int = Field(ge=1)
    evidence_ids: list[str] = Field(min_length=1)
    source_method: SourceMethod
    quote: str
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: list[int] | None = None
    polygon: list[list[int]] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ExtractionProvenance(BaseModel):
    extractor_id: str
    extractor_version: str = EXTRACTOR_VERSION
    confidence: ExtractionConfidence


class EvidenceUnit(BaseModel):
    unit_id: str
    page_number: int = Field(ge=1)
    order_index: int = Field(ge=1)
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    source_method: SourceMethod
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: list[int] | None = None
    polygon: list[list[int]] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TitleCandidate(BaseModel):
    candidate_id: str
    text: str
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class Clause(BaseModel):
    clause_id: str
    heading_token: str
    heading_text: str
    body_text: str
    level: int = Field(ge=1)
    parent_clause_id: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class UnnumberedBlock(BaseModel):
    block_id: str
    text: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class PartyMention(BaseModel):
    mention_id: str
    role_label: str
    raw_name: str | None = None
    normalized_name: str | None = None
    resolution_state: ResolutionState
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class DateMention(BaseModel):
    mention_id: str
    raw_text: str
    iso_date: str | None = None
    field_label: str | None = None
    resolution_state: ResolutionState
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class MoneyMention(BaseModel):
    mention_id: str
    raw_text: str
    numeric_value: str | None = None
    currency: str | None = None
    unit: str | None = None
    resolution_state: ResolutionState
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class PercentageMention(BaseModel):
    mention_id: str
    raw_text: str
    numeric_value: str | None = None
    resolution_state: ResolutionState
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class IdentifierMention(BaseModel):
    mention_id: str
    label: str
    raw_value: str
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class ReferenceType(str, Enum):
    ATTACHMENT = "ATTACHMENT"
    CLAUSE = "CLAUSE"


class ReferenceMention(BaseModel):
    reference_id: str
    raw_text: str
    reference_type: ReferenceType
    target_label: str | None = None
    resolved_target_id: str | None = None
    resolution_state: ResolutionState
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class StructuredBlockKind(str, Enum):
    TABLE_CANDIDATE = "TABLE_CANDIDATE"


class StructuredBlockCandidate(BaseModel):
    block_id: str
    kind: StructuredBlockKind
    raw_text: str
    source_spans: list[SourceSpan] = Field(min_length=1)
    provenance: ExtractionProvenance


class ExtractionWarning(BaseModel):
    warning_id: str
    code: str
    message: str
    page_number: int | None = Field(default=None, ge=1)
    evidence_ids: list[str] = Field(default_factory=list)


class CanonicalContract(BaseModel):
    schema_version: str = CONTRACT_SCHEMA_VERSION
    extractor_version: str = EXTRACTOR_VERSION
    job_id: UUID
    filename: str
    status: str = "complete"
    source_fingerprint: str
    evidence_unit_count: int = Field(ge=0)
    title_candidates: list[TitleCandidate] = Field(default_factory=list)
    clauses: list[Clause] = Field(default_factory=list)
    unnumbered_blocks: list[UnnumberedBlock] = Field(default_factory=list)
    parties: list[PartyMention] = Field(default_factory=list)
    dates: list[DateMention] = Field(default_factory=list)
    money_mentions: list[MoneyMention] = Field(default_factory=list)
    percentages: list[PercentageMention] = Field(default_factory=list)
    identifiers: list[IdentifierMention] = Field(default_factory=list)
    references: list[ReferenceMention] = Field(default_factory=list)
    structured_blocks: list[StructuredBlockCandidate] = Field(default_factory=list)
    warnings: list[ExtractionWarning] = Field(default_factory=list)


class StructureSummary(BaseModel):
    job_id: UUID
    schema_version: str
    status: str
    title: str | None = None
    clause_count: int = Field(ge=0)
    party_count: int = Field(ge=0)
    date_count: int = Field(ge=0)
    money_count: int = Field(ge=0)
    percentage_count: int = Field(ge=0)
    identifier_count: int = Field(ge=0)
    unresolved_reference_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    clauses: list[Clause] = Field(default_factory=list)
    parties: list[PartyMention] = Field(default_factory=list)
    dates: list[DateMention] = Field(default_factory=list)
    money_mentions: list[MoneyMention] = Field(default_factory=list)
    percentages: list[PercentageMention] = Field(default_factory=list)
    identifiers: list[IdentifierMention] = Field(default_factory=list)
