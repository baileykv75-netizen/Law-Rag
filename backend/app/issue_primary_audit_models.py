from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .ai_audit_models import FindingSeverity, ProviderUsage
from .audit_plan_models import AuditPlanSource, ReviewPriority
from .issue_legal_context_models import IssueLegalSupportState, IssueLegalEvidenceHit

ISSUE_PRIMARY_AUDIT_SCHEMA_VERSION = "1.0.0"
ISSUE_PRIMARY_AUDIT_ENGINE_VERSION = "stage13e-1.0.0"


class IssuePrimaryAuditState(str, Enum):
    SUPPORTED_FINDING = "SUPPORTED_FINDING"
    NO_MATERIAL_RISK_FOUND = "NO_MATERIAL_RISK_FOUND"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class IssueEvidenceSufficiency(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL_LEGAL_CORPUS = "PARTIAL_LEGAL_CORPUS"
    INSUFFICIENT_LEGAL_CORPUS = "INSUFFICIENT_LEGAL_CORPUS"
    LEGAL_VERSION_UNCERTAIN = "LEGAL_VERSION_UNCERTAIN"
    SOURCE_UNCERTAIN = "SOURCE_UNCERTAIN"
    CONTRACT_EVIDENCE_INSUFFICIENT = "CONTRACT_EVIDENCE_INSUFFICIENT"


class IssuePrimaryAuditStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    INTERRUPTED = "INTERRUPTED"


class IssueContextRelation(str, Enum):
    TARGET = "TARGET"
    RELATED = "RELATED"


class IssueTargetSelectionMethod(str, Enum):
    EXPLICIT_PLAN = "EXPLICIT_PLAN"
    DETERMINISTIC_CONTRACT_RETRIEVAL = "DETERMINISTIC_CONTRACT_RETRIEVAL"
    NONE = "NONE"


class IssuePrimaryContractItem(BaseModel):
    canonical_object_id: str
    object_type: str
    relation: IssueContextRelation
    text: str = Field(max_length=60000)
    evidence_ids: list[str] = Field(default_factory=list)
    source_uncertain: bool = False


class IssuePrimaryGlobalFact(BaseModel):
    fact_id: str
    fact_type: str
    label: str
    value: str = Field(max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list)


class IssuePrimaryRuleHint(BaseModel):
    result_id: str
    rule_id: str
    state: str
    reason_code: str
    explanation: str = Field(max_length=4000)
    canonical_object_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class IssuePrimaryAuditContext(BaseModel):
    job_id: UUID
    issue_id: str
    topic: str
    priority: ReviewPriority
    sources: list[AuditPlanSource] = Field(min_length=1)
    why_review: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    as_of: date
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    audit_plan_fingerprint: str
    issue_legal_context_fingerprint: str
    legal_support_state: IssueLegalSupportState
    target_selection_method: IssueTargetSelectionMethod
    target_items: list[IssuePrimaryContractItem] = Field(default_factory=list)
    related_items: list[IssuePrimaryContractItem] = Field(default_factory=list)
    global_facts: list[IssuePrimaryGlobalFact] = Field(default_factory=list)
    deterministic_hints: list[IssuePrimaryRuleHint] = Field(default_factory=list)
    legal_evidence: list[IssueLegalEvidenceHit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    context_fingerprint: str


class ModelIssuePrimaryAuditDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: IssuePrimaryAuditState
    legal_conclusion: bool
    risk_category: str = Field(min_length=1, max_length=120)
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=240)
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    suggestion: str = Field(min_length=1, max_length=2000)
    canonical_object_ids: list[str] = Field(default_factory=list, max_length=40)
    contract_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    legal_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    review_reasons: list[str] = Field(default_factory=list, max_length=30)


class IssuePrimaryProviderCall(BaseModel):
    issue_id: str
    provider: str
    model: str
    request_id: str | None = None
    finish_reason: str | None = None
    raw_response_hash: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class IssuePrimaryAuditResult(BaseModel):
    issue_id: str
    topic: str
    state: IssuePrimaryAuditState
    evidence_sufficiency: IssueEvidenceSufficiency
    legal_support_state: IssueLegalSupportState
    legal_conclusion: bool
    risk_category: str
    severity: FindingSeverity
    title: str
    reasoning_summary: str
    suggestion: str
    canonical_object_ids: list[str] = Field(default_factory=list)
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    context_fingerprint: str


class IssuePrimaryAuditArtifact(BaseModel):
    schema_version: str = ISSUE_PRIMARY_AUDIT_SCHEMA_VERSION
    engine_version: str = ISSUE_PRIMARY_AUDIT_ENGINE_VERSION
    job_id: UUID
    status: IssuePrimaryAuditStatus
    as_of: date
    provider: str
    model: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    audit_plan_fingerprint: str
    issue_legal_context_fingerprint: str
    total_issue_count: int = Field(ge=0)
    completed_issue_count: int = Field(ge=0)
    results: list[IssuePrimaryAuditResult] = Field(default_factory=list)
    provider_calls: list[IssuePrimaryProviderCall] = Field(default_factory=list)
    provider_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    warnings: list[str] = Field(default_factory=list)
    artifact_fingerprint: str


class IssuePrimaryAuditRunRequest(BaseModel):
    provider: str = Field(default="deepseek", min_length=1, max_length=64)
