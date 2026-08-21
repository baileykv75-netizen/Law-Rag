from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .ai_audit_models import ProviderUsage

UAT_CAPTURE_SCHEMA_VERSION = "1.0.0"
UAT_CAPTURE_VERSION = "stage16d-1.0.0"


class UATCaptureMode(str, Enum):
    TEST_DOUBLE = "TEST_DOUBLE"
    REAL_PROVIDER = "REAL_PROVIDER"


class UATChainState(str, Enum):
    COMPLETE = "COMPLETE"
    PRIMARY_INTERRUPTED = "PRIMARY_INTERRUPTED"
    SECONDARY_INTERRUPTED = "SECONDARY_INTERRUPTED"


class UATProviderStage(str, Enum):
    PLANNER = "PLANNER"
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class UATArtifactProvenance(BaseModel):
    artifact: str
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedded_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class UATProviderCallProvenance(BaseModel):
    stage: UATProviderStage
    issue_id: str | None = None
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=240)
    request_id: str | None = Field(default=None, max_length=500)
    finish_reason: str | None = Field(default=None, max_length=200)
    raw_response_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class UATIssueCoverage(BaseModel):
    issue_id: str
    primary_result_present: bool
    primary_provider_call_present: bool
    secondary_result_present: bool
    secondary_provider_call_present: bool
    comparison_present: bool


class IssueV1UATObservation(BaseModel):
    schema_version: str = UAT_CAPTURE_SCHEMA_VERSION
    capture_version: str = UAT_CAPTURE_VERSION
    capture_mode: UATCaptureMode
    captured_at: str = Field(min_length=20, max_length=80)
    architecture: str = "ISSUE_V1"
    job_id: UUID
    chain_state: UATChainState
    pipeline_status: str
    pipeline_failure_code: str | None = None
    audit_plan_issue_count: int = Field(ge=0)
    primary_completed_issue_count: int = Field(ge=0)
    secondary_completed_issue_count: int = Field(ge=0)
    compared_issue_count: int = Field(ge=0)
    issue_coverage: list[UATIssueCoverage] = Field(default_factory=list)
    provider_calls: list[UATProviderCallProvenance] = Field(default_factory=list)
    artifacts: list[UATArtifactProvenance] = Field(default_factory=list)
    observation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class UATProviderSummary(BaseModel):
    stage: UATProviderStage
    provider: str
    model: str
    provider_call_count: int = Field(ge=0)
    total_prompt_tokens: int | None = Field(default=None, ge=0)
    total_completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class IssueV1UATSanitizedReport(BaseModel):
    schema_version: str = UAT_CAPTURE_SCHEMA_VERSION
    capture_version: str = UAT_CAPTURE_VERSION
    capture_mode: UATCaptureMode
    architecture: str = "ISSUE_V1"
    chain_state: UATChainState
    pipeline_status: str
    pipeline_failure_code_present: bool
    audit_plan_issue_count: int = Field(ge=0)
    primary_completed_issue_count: int = Field(ge=0)
    secondary_completed_issue_count: int = Field(ge=0)
    compared_issue_count: int = Field(ge=0)
    provider_summaries: list[UATProviderSummary] = Field(default_factory=list)
    artifact_fingerprints: dict[str, str] = Field(default_factory=dict)
    observation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    warnings: list[str] = Field(default_factory=list)
