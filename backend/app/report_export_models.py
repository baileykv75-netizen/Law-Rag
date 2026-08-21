from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

REPORT_EXPORT_SCHEMA_VERSION = "1.0.0"
REPORT_EXPORT_ENGINE_VERSION = "stage18.2-1.0.0"


class ReportExportFormat(str, Enum):
    DOCX = "docx"
    PDF = "pdf"


class ReportContractEvidence(BaseModel):
    evidence_id: str
    quote: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    source_method: str | None = None


class ReportLegalEvidence(BaseModel):
    legal_evidence_id: str
    authority_id: str
    authority_title: str
    version_id: str
    article_token: str
    article_text: str
    effective_date: str
    end_date_exclusive: str | None = None
    coverage_type: str


class ReportHumanDecision(BaseModel):
    state: str
    revision: int = Field(ge=1)
    decided_at: datetime
    reviewer_note: str = ""
    is_stale: bool = False


class ReportIssue(BaseModel):
    issue_id: str
    topic: str
    priority: str
    why_review: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    primary_state: str
    primary_severity: str
    primary_title: str
    primary_reasoning: str
    primary_suggestion: str
    primary_evidence_sufficiency: str
    secondary_assessment: str
    secondary_coverage_assessment: str
    secondary_severity: str
    secondary_reasoning: str
    secondary_suggestion: str
    comparison_state: str
    requires_human_review: bool
    comparison_reasons: list[str] = Field(default_factory=list)
    omission_title: str | None = None
    omission_reasoning: str | None = None
    contract_evidence: list[ReportContractEvidence] = Field(default_factory=list)
    legal_evidence: list[ReportLegalEvidence] = Field(default_factory=list)
    human_decision: ReportHumanDecision | None = None


class AuditReportDocument(BaseModel):
    schema_version: str = REPORT_EXPORT_SCHEMA_VERSION
    engine_version: str = REPORT_EXPORT_ENGINE_VERSION
    job_id: UUID
    filename: str
    document_kind: str
    as_of: str
    overall_state: str
    contract_type: str
    planning_mode: str
    planning_coverage_complete: bool
    canonical_object_count: int = Field(ge=0)
    reviewed_with_issue_count: int = Field(ge=0)
    reviewed_no_specific_issue_count: int = Field(ge=0)
    primary_provider: str
    primary_model: str
    secondary_provider: str
    secondary_model: str
    final_review_state: str
    human_review_required_count: int = Field(ge=0)
    human_review_resolved_required_count: int = Field(ge=0)
    human_review_outstanding_required_count: int = Field(ge=0)
    issues: list[ReportIssue] = Field(default_factory=list)
    source_uncertainty: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_fingerprints: dict[str, str] = Field(default_factory=dict)
    report_content_fingerprint: str


class ReportExportResult(BaseModel):
    schema_version: str = REPORT_EXPORT_SCHEMA_VERSION
    job_id: UUID
    format: ReportExportFormat
    filename: str
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
