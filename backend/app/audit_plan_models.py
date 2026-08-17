from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .ai_audit_models import ProviderUsage

AUDIT_PLAN_SCHEMA_VERSION = "1.0.0"
AUDIT_PLANNER_VERSION = "stage13b-1.0.0"


class ContractType(str, Enum):
    GENERAL = "GENERAL"
    PURCHASE = "PURCHASE"
    SERVICE = "SERVICE"
    LEASE = "LEASE"
    EMPLOYMENT = "EMPLOYMENT"
    CONSTRUCTION = "CONSTRUCTION"
    TECHNOLOGY = "TECHNOLOGY"
    LOAN = "LOAN"
    EQUITY = "EQUITY"
    UNKNOWN = "UNKNOWN"
    MIXED = "MIXED"


class ContractTypeConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AuditPlanSource(str, Enum):
    BASELINE = "BASELINE"
    DETERMINISTIC_HINT = "DETERMINISTIC_HINT"
    LLM_DYNAMIC = "LLM_DYNAMIC"


class ReviewPriority(str, Enum):
    NORMAL = "NORMAL"
    IMPORTANT = "IMPORTANT"
    HIGH_ATTENTION = "HIGH_ATTENTION"


class PlannerContractItem(BaseModel):
    canonical_object_id: str
    object_type: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class PlannerGlobalFact(BaseModel):
    fact_id: str
    fact_type: str
    label: str
    value: str
    evidence_ids: list[str] = Field(default_factory=list)


class PlannerRuleHint(BaseModel):
    result_id: str
    rule_id: str
    state: str
    reason_code: str
    title: str
    explanation: str
    canonical_object_ids: list[str] = Field(default_factory=list)


class PlannerTopicHint(BaseModel):
    topic: str
    retrieval_query: str
    contract_object_ids: list[str] = Field(default_factory=list)


class AuditPlannerInput(BaseModel):
    job_id: UUID
    contract_schema_version: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    contract_items: list[PlannerContractItem] = Field(default_factory=list)
    global_facts: list[PlannerGlobalFact] = Field(default_factory=list)
    deterministic_rule_hints: list[PlannerRuleHint] = Field(default_factory=list)
    legacy_topic_hints: list[PlannerTopicHint] = Field(default_factory=list)
    total_text_chars: int = Field(ge=0)
    input_fingerprint: str


class ModelAuditPlanIssueDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_issue_id: str = Field(min_length=1, max_length=80)
    topic: str = Field(min_length=1, max_length=160)
    priority: ReviewPriority
    why_review: str = Field(min_length=1, max_length=1600)
    contract_object_ids: list[str] = Field(default_factory=list, max_length=80)
    questions: list[str] = Field(default_factory=list, max_length=30)
    retrieval_queries: list[str] = Field(default_factory=list, max_length=20)


class ModelAuditPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_type: ContractType
    contract_type_confidence: ContractTypeConfidence
    contract_type_reasoning: str = Field(min_length=1, max_length=1200)
    issues: list[ModelAuditPlanIssueDraft] = Field(default_factory=list, max_length=120)


class PlannerProviderResult(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    request_id: str | None = None
    finish_reason: str | None = None
    content: str
    raw_response_hash: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class AuditPlanIssue(BaseModel):
    issue_id: str
    topic: str
    priority: ReviewPriority
    sources: list[AuditPlanSource] = Field(min_length=1)
    why_review: list[str] = Field(default_factory=list)
    contract_object_ids: list[str] = Field(default_factory=list)
    contract_evidence_ids: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    retrieval_queries: list[str] = Field(default_factory=list)
    rule_result_ids: list[str] = Field(default_factory=list)
    legacy_hint_topics: list[str] = Field(default_factory=list)


class AuditPlan(BaseModel):
    schema_version: str = AUDIT_PLAN_SCHEMA_VERSION
    planner_version: str = AUDIT_PLANNER_VERSION
    job_id: UUID
    status: str = "complete"
    contract_type: ContractType
    contract_type_confidence: ContractTypeConfidence
    contract_type_reasoning: str
    provider: str
    model: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    planner_input_fingerprint: str
    planner_response_hash: str
    provider_request_id: str | None = None
    provider_finish_reason: str | None = None
    provider_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    issues: list[AuditPlanIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditPlannerRunRequest(BaseModel):
    provider: str = Field(default="deepseek", min_length=1, max_length=64)


class HierarchicalPlanningRequired(BaseModel):
    code: str = "HIERARCHICAL_PLANNING_REQUIRED"
    detail: str
    total_text_chars: int = Field(ge=0)
    direct_text_char_limit: int = Field(ge=1)
