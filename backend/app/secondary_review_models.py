from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .ai_audit_models import (
    AiAuditReport,
    AuditContextPackage,
    FindingSeverity,
    ProviderUsage,
)

SECONDARY_REVIEW_SCHEMA_VERSION = "1.0.0"
SECONDARY_REVIEW_ENGINE_VERSION = "stage9b-1.0.0"
SECONDARY_CONTEXT_SCHEMA_VERSION = "1.0.0"
SECONDARY_CONTEXT_BUILDER_VERSION = "stage9a-context-1.0.0"


class SecondaryAssessment(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DisagreementCategory(str, Enum):
    AGREE_SUPPORTED = "AGREE_SUPPORTED"
    AGREE_REVIEW_REQUIRED = "AGREE_REVIEW_REQUIRED"
    DISAGREE_RISK_EXISTS = "DISAGREE_RISK_EXISTS"
    DISAGREE_SEVERITY = "DISAGREE_SEVERITY"
    DISAGREE_LEGAL_BASIS = "DISAGREE_LEGAL_BASIS"
    DISAGREE_CONTRACT_EVIDENCE = "DISAGREE_CONTRACT_EVIDENCE"
    POSSIBLE_PRIMARY_OMISSION = "POSSIBLE_PRIMARY_OMISSION"
    INSUFFICIENT_TO_COMPARE = "INSUFFICIENT_TO_COMPARE"


class SecondaryReviewRunRequest(BaseModel):
    provider: str = Field(default="kimi", min_length=1, max_length=64)
    use_semantic: bool = False


class SecondaryReviewContext(BaseModel):
    schema_version: str = SECONDARY_CONTEXT_SCHEMA_VERSION
    builder_version: str = SECONDARY_CONTEXT_BUILDER_VERSION
    job_id: UUID
    as_of: date
    primary_report: AiAuditReport
    audit_context: AuditContextPackage
    context_fingerprint: str


class ModelSecondaryFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_finding_id: str = Field(min_length=1, max_length=120)
    assessment: SecondaryAssessment
    severity: FindingSeverity
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    suggestion: str = Field(min_length=1, max_length=2000)
    contract_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    legal_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    disagreement_categories: list[DisagreementCategory] = Field(default_factory=list, max_length=12)
    review_reasons: list[str] = Field(default_factory=list, max_length=20)


class ModelSecondaryOmissionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_omission_id: str = Field(min_length=1, max_length=80)
    risk_category: str = Field(min_length=1, max_length=120)
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=240)
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    suggestion: str = Field(min_length=1, max_length=2000)
    canonical_object_ids: list[str] = Field(default_factory=list, max_length=40)
    contract_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    legal_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    review_reasons: list[str] = Field(default_factory=list, max_length=20)


class ModelSecondaryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_reviews: list[ModelSecondaryFindingDraft] = Field(default_factory=list, max_length=50)
    possible_omissions: list[ModelSecondaryOmissionDraft] = Field(default_factory=list, max_length=20)


class SecondaryFindingReview(BaseModel):
    review_id: str
    primary_finding_id: str
    assessment: SecondaryAssessment
    severity: FindingSeverity
    reasoning_summary: str
    suggestion: str
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    disagreement_categories: list[DisagreementCategory] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


class SecondaryPossibleOmission(BaseModel):
    omission_id: str
    risk_category: str
    severity: FindingSeverity
    title: str
    reasoning_summary: str
    suggestion: str
    canonical_object_ids: list[str] = Field(default_factory=list)
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


class SecondaryReviewReport(BaseModel):
    schema_version: str = SECONDARY_REVIEW_SCHEMA_VERSION
    engine_version: str = SECONDARY_REVIEW_ENGINE_VERSION
    job_id: UUID
    status: str = "complete"
    as_of: date
    primary_provider: str
    primary_model: str
    primary_context_fingerprint: str
    secondary_context_fingerprint: str
    provider: str
    model: str
    raw_response_hash: str
    provider_request_id: str | None = None
    provider_finish_reason: str | None = None
    provider_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    finding_reviews: list[SecondaryFindingReview] = Field(default_factory=list)
    possible_omissions: list[SecondaryPossibleOmission] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supplied_contract_evidence_ids: list[str] = Field(default_factory=list)
    supplied_legal_evidence_ids: list[str] = Field(default_factory=list)
