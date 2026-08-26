from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .ai_audit_models import FindingSeverity, ProviderUsage

ISSUE_SECONDARY_REVIEW_SCHEMA_VERSION = "1.0.0"
ISSUE_SECONDARY_REVIEW_ENGINE_VERSION = "stage13f-1.0.0"


class SecondaryIssueAssessment(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    DISAGREED = "DISAGREED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SecondaryCoverageAssessment(str, Enum):
    COVERED = "COVERED"
    COVERED_BUT_QUESTIONABLE = "COVERED_BUT_QUESTIONABLE"
    POSSIBLE_OMISSION = "POSSIBLE_OMISSION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class IssueSecondaryReviewStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    INTERRUPTED = "INTERRUPTED"


class SecondaryReviewDecisionStatus(str, Enum):
    REVIEWED = "REVIEWED"
    SKIPPED_CLEAR = "SKIPPED_CLEAR"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"


class ModelIssueSecondaryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    assessment: SecondaryIssueAssessment
    coverage_assessment: SecondaryCoverageAssessment
    severity: FindingSeverity
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    suggestion: str = Field(min_length=1, max_length=2000)
    contract_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    legal_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    review_reasons: list[str] = Field(default_factory=list, max_length=30)
    omission_title: str | None = Field(default=None, max_length=240)
    omission_reasoning: str | None = Field(default=None, max_length=2400)


class IssueSecondaryProviderCall(BaseModel):
    issue_id: str
    provider: str
    model: str
    request_id: str | None = None
    finish_reason: str | None = None
    raw_response_hash: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class IssueSecondaryReviewResult(BaseModel):
    issue_id: str
    topic: str
    primary_state: str
    review_status: SecondaryReviewDecisionStatus = SecondaryReviewDecisionStatus.REVIEWED
    assessment: SecondaryIssueAssessment
    coverage_assessment: SecondaryCoverageAssessment
    severity: FindingSeverity
    reasoning_summary: str
    suggestion: str
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    omission_title: str | None = None
    omission_reasoning: str | None = None
    context_fingerprint: str


class IssueSecondaryReviewArtifact(BaseModel):
    schema_version: str = ISSUE_SECONDARY_REVIEW_SCHEMA_VERSION
    engine_version: str = ISSUE_SECONDARY_REVIEW_ENGINE_VERSION
    job_id: UUID
    status: IssueSecondaryReviewStatus
    provider: str
    model: str
    audit_plan_fingerprint: str
    issue_legal_context_fingerprint: str
    issue_primary_audit_fingerprint: str
    total_issue_count: int = Field(ge=0)
    completed_issue_count: int = Field(ge=0)
    results: list[IssueSecondaryReviewResult] = Field(default_factory=list)
    provider_calls: list[IssueSecondaryProviderCall] = Field(default_factory=list)
    provider_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    warnings: list[str] = Field(default_factory=list)
    artifact_fingerprint: str


class IssueSecondaryReviewRunRequest(BaseModel):
    provider: str = Field(default="kimi", min_length=1, max_length=64)
