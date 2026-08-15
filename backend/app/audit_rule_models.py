from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .contract_models import SourceSpan

AUDIT_RULE_SCHEMA_VERSION = "1.0.0"
RULE_ENGINE_VERSION = "stage5-1.0.0"
DEFAULT_PROFILE_ID = "basic-bilateral-v1"


class RuleState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AuditProfile(BaseModel):
    profile_id: str
    version: str
    title: str
    required_title: bool = True
    min_resolved_parties: int = Field(default=2, ge=0)
    min_distinct_party_roles: int = Field(default=2, ge=0)


class ObservedValue(BaseModel):
    label: str
    value: str
    canonical_object_id: str | None = None


class RuleResult(BaseModel):
    result_id: str
    rule_id: str
    rule_version: str
    family: str
    title: str
    state: RuleState
    deterministic_state: RuleState
    severity: RuleSeverity | None = None
    reason_code: str
    explanation: str
    canonical_object_ids: list[str] = Field(default_factory=list)
    source_spans: list[SourceSpan] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    observed_values: list[ObservedValue] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


class RuleEngineError(BaseModel):
    rule_id: str
    error_type: str
    message: str


class RuleCounts(BaseModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    review: int = Field(ge=0)
    not_applicable: int = Field(ge=0)


class AuditRuleReport(BaseModel):
    schema_version: str = AUDIT_RULE_SCHEMA_VERSION
    engine_version: str = RULE_ENGINE_VERSION
    job_id: UUID
    status: str = "complete"
    contract_schema_version: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    profile: AuditProfile
    counts: RuleCounts
    results: list[RuleResult] = Field(default_factory=list)
    engine_errors: list[RuleEngineError] = Field(default_factory=list)
