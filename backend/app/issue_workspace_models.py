from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .ai_audit_models import FindingSeverity
from .audit_plan_models import AuditPlanIssue, AuditPlanPlanningMode, ContractType, ReviewPriority
from .issue_legal_context_models import IssueLegalEvidenceHit, IssueLegalSupportState
from .issue_primary_audit_models import IssuePrimaryAuditResult, IssuePrimaryAuditState
from .issue_review_report_models import IssueReviewComparison, IssueReviewComparisonState, IssueReviewFinalState
from .issue_secondary_review_models import (
    IssueSecondaryReviewResult,
    SecondaryCoverageAssessment,
    SecondaryIssueAssessment,
)
from .workspace_models import (
    WorkspaceDocumentSummary,
    WorkspaceOverallState,
    WorkspaceStageSummary,
)

ISSUE_WORKSPACE_SCHEMA_VERSION = "1.0.0"
ISSUE_WORKSPACE_ENGINE_VERSION = "stage13g-5-1.0.0"


class IssueWorkspaceCoverageSummary(BaseModel):
    planning_mode: AuditPlanPlanningMode
    contract_type: ContractType
    coverage_complete: bool
    canonical_object_count: int = Field(ge=0)
    reviewed_with_issue_count: int = Field(ge=0)
    reviewed_no_specific_issue_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)


class IssueWorkspaceReviewSummary(BaseModel):
    primary_available: bool = False
    primary_provider: str | None = None
    primary_model: str | None = None
    primary_completed_issue_count: int = Field(default=0, ge=0)
    secondary_available: bool = False
    secondary_provider: str | None = None
    secondary_model: str | None = None
    secondary_completed_issue_count: int = Field(default=0, ge=0)
    comparison_available: bool = False
    final_review_state: IssueReviewFinalState | None = None
    compared_issue_count: int = Field(default=0, ge=0)
    human_review_required_count: int = Field(default=0, ge=0)
    material_disagreement_count: int = Field(default=0, ge=0)
    possible_omission_count: int = Field(default=0, ge=0)
    insufficient_evidence_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    consistent_with_review_count: int = Field(default=0, ge=0)


class IssueWorkspaceQueueItem(BaseModel):
    issue_id: str
    topic: str
    priority: ReviewPriority
    source_labels: list[str] = Field(default_factory=list)
    contract_evidence_count: int = Field(default=0, ge=0)
    legal_evidence_count: int = Field(default=0, ge=0)
    legal_support_state: IssueLegalSupportState | None = None
    primary_state: IssuePrimaryAuditState | None = None
    primary_severity: FindingSeverity | None = None
    secondary_assessment: SecondaryIssueAssessment | None = None
    coverage_assessment: SecondaryCoverageAssessment | None = None
    comparison_state: IssueReviewComparisonState | None = None
    requires_human_review: bool = False


class IssueWorkspaceSummary(BaseModel):
    schema_version: str = ISSUE_WORKSPACE_SCHEMA_VERSION
    engine_version: str = ISSUE_WORKSPACE_ENGINE_VERSION
    job_id: UUID
    architecture: Literal["ISSUE_V1"] = "ISSUE_V1"
    overall_state: WorkspaceOverallState
    source_available: bool
    document: WorkspaceDocumentSummary | None = None
    stages: list[WorkspaceStageSummary]
    coverage: IssueWorkspaceCoverageSummary | None = None
    review: IssueWorkspaceReviewSummary
    issues: list[IssueWorkspaceQueueItem] = Field(default_factory=list)
    source_uncertainty: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IssueWorkspaceDetail(BaseModel):
    schema_version: str = ISSUE_WORKSPACE_SCHEMA_VERSION
    engine_version: str = ISSUE_WORKSPACE_ENGINE_VERSION
    job_id: UUID
    issue_id: str
    as_of: str | None = None
    plan_issue: AuditPlanIssue
    legal_support_state: IssueLegalSupportState | None = None
    legal_evidence: list[IssueLegalEvidenceHit] = Field(default_factory=list)
    primary: IssuePrimaryAuditResult | None = None
    secondary: IssueSecondaryReviewResult | None = None
    comparison: IssueReviewComparison | None = None
    warnings: list[str] = Field(default_factory=list)
