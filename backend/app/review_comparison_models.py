from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .ai_audit_models import FindingSeverity

REVIEW_COMPARISON_SCHEMA_VERSION = "1.0.0"
REVIEW_COMPARISON_ENGINE_VERSION = "stage9c-comparison-1.0.0"
AGENT_ACTION_SCHEMA_VERSION = "1.0.0"
AGENT_POLICY_VERSION = "stage9c-agent-policy-1.0.0"
MAX_FOLLOW_UP_CYCLES = 2


class RiskComparisonState(str, Enum):
    AGREE_SUPPORTED = "AGREE_SUPPORTED"
    AGREE_NO_FINDING = "AGREE_NO_FINDING"
    AGREE_REVIEW_REQUIRED = "AGREE_REVIEW_REQUIRED"
    AGREE_INSUFFICIENT_EVIDENCE = "AGREE_INSUFFICIENT_EVIDENCE"
    DISAGREE_RISK_EXISTS = "DISAGREE_RISK_EXISTS"
    DISAGREE_EVIDENCE_SUFFICIENCY = "DISAGREE_EVIDENCE_SUFFICIENCY"
    STATE_DIFFERENCE = "STATE_DIFFERENCE"


class SeverityComparisonState(str, Enum):
    AGREE = "AGREE"
    MINOR_DISAGREEMENT = "MINOR_DISAGREEMENT"
    MATERIAL_DISAGREEMENT = "MATERIAL_DISAGREEMENT"


class EvidenceSetComparisonState(str, Enum):
    AGREE = "AGREE"
    PARTIAL_OVERLAP = "PARTIAL_OVERLAP"
    DISJOINT = "DISJOINT"
    PRIMARY_ONLY = "PRIMARY_ONLY"
    SECONDARY_ONLY = "SECONDARY_ONLY"
    BOTH_EMPTY = "BOTH_EMPTY"


class OverallComparisonState(str, Enum):
    AGREEMENT = "AGREEMENT"
    AGREEMENT_WITH_REVIEW = "AGREEMENT_WITH_REVIEW"
    MINOR_DISAGREEMENT = "MINOR_DISAGREEMENT"
    REQUIRES_MORE_EVIDENCE = "REQUIRES_MORE_EVIDENCE"
    MATERIAL_DISAGREEMENT = "MATERIAL_DISAGREEMENT"


class AgentFollowUpDecision(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    FOLLOW_UP_REQUIRED = "FOLLOW_UP_REQUIRED"


class AgentPlanState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    ACTIONS_PLANNED = "ACTIONS_PLANNED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class AgentToolName(str, Enum):
    INSPECT_CONTRACT_EVIDENCE = "inspect_contract_evidence"
    GET_CLAUSE_CONTEXT = "get_clause_context"
    INSPECT_LEGAL_EVIDENCE = "inspect_legal_evidence"
    RETRIEVE_MORE_LEGAL = "retrieve_more_legal"
    RESOLVE_CONTRACT_REFERENCE = "resolve_contract_reference"
    REQUEST_OCR_RETRY = "request_ocr_retry"


class AgentActionState(str, Enum):
    REQUESTED = "REQUESTED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class EvidenceSetComparison(BaseModel):
    state: EvidenceSetComparisonState
    shared: list[str] = Field(default_factory=list)
    primary_only: list[str] = Field(default_factory=list)
    secondary_only: list[str] = Field(default_factory=list)


class SeverityComparison(BaseModel):
    primary: FindingSeverity
    secondary: FindingSeverity
    distance: int = Field(ge=0)
    state: SeverityComparisonState


class FindingComparison(BaseModel):
    comparison_id: str
    primary_finding_id: str
    risk_state: RiskComparisonState
    severity: SeverityComparison
    contract_evidence: EvidenceSetComparison
    legal_basis: EvidenceSetComparison
    overall_state: OverallComparisonState
    material_reasons: list[str] = Field(default_factory=list)
    follow_up: AgentFollowUpDecision


class OmissionComparison(BaseModel):
    omission_id: str
    risk_category: str
    severity: FindingSeverity
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    overall_state: OverallComparisonState = OverallComparisonState.MATERIAL_DISAGREEMENT
    follow_up: AgentFollowUpDecision = AgentFollowUpDecision.FOLLOW_UP_REQUIRED
    reason: str = "SECONDARY_IDENTIFIED_POSSIBLE_PRIMARY_OMISSION"


class ReviewComparisonReport(BaseModel):
    schema_version: str = REVIEW_COMPARISON_SCHEMA_VERSION
    engine_version: str = REVIEW_COMPARISON_ENGINE_VERSION
    job_id: str
    primary_context_fingerprint: str
    secondary_context_fingerprint: str
    finding_comparisons: list[FindingComparison] = Field(default_factory=list)
    omission_comparisons: list[OmissionComparison] = Field(default_factory=list)
    overall_state: OverallComparisonState
    follow_up: AgentFollowUpDecision
    follow_up_reasons: list[str] = Field(default_factory=list)
    max_follow_up_cycles: int = MAX_FOLLOW_UP_CYCLES


class AgentActionRecord(BaseModel):
    schema_version: str = AGENT_ACTION_SCHEMA_VERSION
    policy_version: str = AGENT_POLICY_VERSION
    action_id: str
    cycle: int = Field(ge=1, le=MAX_FOLLOW_UP_CYCLES)
    tool_name: AgentToolName
    state: AgentActionState
    reason: str
    normalized_arguments: dict = Field(default_factory=dict)
    input_evidence_ids: list[str] = Field(default_factory=list)
    output_evidence_ids: list[str] = Field(default_factory=list)
    result_payload: dict = Field(default_factory=dict)
    provider_call_occurred: bool = False
    private_contract_evidence_left_machine: bool = False
    validation_or_error: str | None = None


class AgentFollowUpPlan(BaseModel):
    policy_version: str = AGENT_POLICY_VERSION
    job_id: str
    comparison_engine_version: str
    state: AgentPlanState
    max_cycles: int = MAX_FOLLOW_UP_CYCLES
    actions: list[AgentActionRecord] = Field(default_factory=list, max_length=MAX_FOLLOW_UP_CYCLES)
    reasons: list[str] = Field(default_factory=list)
