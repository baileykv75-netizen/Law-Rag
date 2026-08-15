from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .contract_models import SourceSpan
from .legal.retrieval_models import RetrievalResponse

AI_AUDIT_SCHEMA_VERSION = "1.0.0"
AI_AUDIT_ENGINE_VERSION = "stage8-1.0.0"
AI_CONTEXT_SCHEMA_VERSION = "1.0.0"
AI_CONTEXT_BUILDER_VERSION = "stage8-context-1.0.0"


class FindingState(str, Enum):
    SUPPORTED_FINDING = "SUPPORTED_FINDING"
    NO_FINDING = "NO_FINDING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceSufficiency(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL_CORPUS = "PARTIAL_CORPUS"
    INSUFFICIENT_CORPUS = "INSUFFICIENT_CORPUS"
    VERSION_UNCERTAIN = "VERSION_UNCERTAIN"
    SOURCE_UNCERTAIN = "SOURCE_UNCERTAIN"


class ProviderHealth(BaseModel):
    provider: str
    configured: bool
    model: str
    base_url: str | None = None
    detail: str


class AiAuditRunRequest(BaseModel):
    as_of: date
    provider: str = Field(default="deepseek", min_length=1, max_length=64)
    use_semantic: bool = False


class ContractContextItem(BaseModel):
    canonical_object_id: str
    object_type: str
    text: str = Field(max_length=12000)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class RuleContextItem(BaseModel):
    result_id: str
    rule_id: str
    state: str
    reason_code: str
    explanation: str = Field(max_length=4000)
    canonical_object_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


class AuditIssuePackage(BaseModel):
    issue_id: str
    topic: str
    query_method: str
    retrieval_query: str
    contract_object_ids: list[str] = Field(default_factory=list)
    contract_evidence_ids: list[str] = Field(default_factory=list)
    retrieval: RetrievalResponse


class AuditContextPackage(BaseModel):
    schema_version: str = AI_CONTEXT_SCHEMA_VERSION
    builder_version: str = AI_CONTEXT_BUILDER_VERSION
    job_id: UUID
    as_of: date
    contract_schema_version: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    contract_items: list[ContractContextItem] = Field(default_factory=list)
    rule_items: list[RuleContextItem] = Field(default_factory=list)
    issues: list[AuditIssuePackage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    context_fingerprint: str


class ModelFindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_finding_id: str = Field(min_length=1, max_length=80)
    state: FindingState
    risk_category: str = Field(min_length=1, max_length=120)
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=240)
    reasoning_summary: str = Field(min_length=1, max_length=3000)
    suggestion: str = Field(min_length=1, max_length=2000)
    issue_ids: list[str] = Field(default_factory=list, max_length=20)
    canonical_object_ids: list[str] = Field(default_factory=list, max_length=40)
    contract_evidence_ids: list[str] = Field(default_factory=list, max_length=80)
    legal_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    review_reasons: list[str] = Field(default_factory=list, max_length=20)


class ModelAuditEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ModelFindingDraft] = Field(default_factory=list, max_length=50)


class ProviderUsage(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class ProviderAuditResult(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    request_id: str | None = None
    finish_reason: str | None = None
    content: str
    raw_response_hash: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class AiAuditFinding(BaseModel):
    finding_id: str
    state: FindingState
    evidence_sufficiency: EvidenceSufficiency
    risk_category: str
    severity: FindingSeverity
    title: str
    reasoning_summary: str
    suggestion: str
    issue_ids: list[str] = Field(default_factory=list)
    canonical_object_ids: list[str] = Field(default_factory=list)
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


class AiAuditReport(BaseModel):
    schema_version: str = AI_AUDIT_SCHEMA_VERSION
    engine_version: str = AI_AUDIT_ENGINE_VERSION
    job_id: UUID
    status: str = "complete"
    as_of: date
    provider: str
    model: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    context_fingerprint: str
    raw_response_hash: str
    provider_request_id: str | None = None
    provider_finish_reason: str | None = None
    provider_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    findings: list[AiAuditFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    supplied_legal_evidence_ids: list[str] = Field(default_factory=list)
    supplied_contract_evidence_ids: list[str] = Field(default_factory=list)
