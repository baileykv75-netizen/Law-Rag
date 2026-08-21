from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .ai_audit_models import FindingSeverity
from .audit_plan_models import ReviewPriority
from .issue_legal_context_models import IssueLegalSupportState
from .issue_primary_audit_models import IssueEvidenceSufficiency, IssuePrimaryAuditState
from .issue_secondary_review_models import (
    SecondaryCoverageAssessment,
    SecondaryIssueAssessment,
)

ISSUE_REVIEW_REPORT_SCHEMA_VERSION = "1.0.0"
ISSUE_REVIEW_REPORT_ENGINE_VERSION = "stage13g-issue-comparison-1.0.0"


class IssueReviewComparisonState(str, Enum):
    CONSISTENT = "CONSISTENT"
    CONSISTENT_WITH_REVIEW = "CONSISTENT_WITH_REVIEW"
    MATERIAL_DISAGREEMENT = "MATERIAL_DISAGREEMENT"
    POSSIBLE_OMISSION = "POSSIBLE_OMISSION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class IssueReviewFinalState(str, Enum):
    NO_MANDATORY_REVIEW = "NO_MANDATORY_REVIEW"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class IssueEvidenceAlignmentState(str, Enum):
    AGREE = "AGREE"
    PARTIAL_OVERLAP = "PARTIAL_OVERLAP"
    DISJOINT = "DISJOINT"
    PRIMARY_ONLY = "PRIMARY_ONLY"
    SECONDARY_ONLY = "SECONDARY_ONLY"
    BOTH_EMPTY = "BOTH_EMPTY"


class IssueEvidenceAlignment(BaseModel):
    state: IssueEvidenceAlignmentState
    shared: list[str] = Field(default_factory=list)
    primary_only: list[str] = Field(default_factory=list)
    secondary_only: list[str] = Field(default_factory=list)


class IssueReviewComparison(BaseModel):
    issue_id: str
    topic: str
    plan_priority: ReviewPriority
    primary_state: IssuePrimaryAuditState
    primary_evidence_sufficiency: IssueEvidenceSufficiency
    legal_support_state: IssueLegalSupportState
    primary_legal_conclusion: bool
    secondary_assessment: SecondaryIssueAssessment
    coverage_assessment: SecondaryCoverageAssessment
    primary_severity: FindingSeverity
    secondary_severity: FindingSeverity
    severity_distance: int = Field(ge=0)
    contract_evidence: IssueEvidenceAlignment
    legal_evidence: IssueEvidenceAlignment
    overall_state: IssueReviewComparisonState
    requires_human_review: bool
    reasons: list[str] = Field(default_factory=list)
    omission_title: str | None = None
    omission_reasoning: str | None = None


class IssueReviewSummary(BaseModel):
    total_issue_count: int = Field(ge=0)
    consistent_count: int = Field(ge=0)
    consistent_with_review_count: int = Field(ge=0)
    material_disagreement_count: int = Field(ge=0)
    possible_omission_count: int = Field(ge=0)
    insufficient_evidence_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    human_review_required_count: int = Field(ge=0)


class IssueReviewReport(BaseModel):
    schema_version: str = ISSUE_REVIEW_REPORT_SCHEMA_VERSION
    engine_version: str = ISSUE_REVIEW_REPORT_ENGINE_VERSION
    job_id: UUID
    status: Literal["COMPLETE"] = "COMPLETE"
    as_of: str
    final_state: IssueReviewFinalState
    primary_provider: str
    primary_model: str
    secondary_provider: str
    secondary_model: str
    audit_plan_fingerprint: str
    issue_primary_audit_fingerprint: str
    issue_secondary_review_fingerprint: str
    planning_coverage_complete: bool
    issue_coverage_complete: bool
    total_issue_count: int = Field(ge=0)
    compared_issue_count: int = Field(ge=0)
    summary: IssueReviewSummary
    comparisons: list[IssueReviewComparison] = Field(default_factory=list)
    final_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifact_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_complete_issue_coverage(self):
        if not self.issue_coverage_complete:
            raise ValueError("A COMPLETE issue review report must have complete AuditPlan issue coverage.")
        if self.total_issue_count != self.compared_issue_count:
            raise ValueError("A COMPLETE issue review report must compare every AuditPlan issue.")
        if self.compared_issue_count != len(self.comparisons):
            raise ValueError("Compared issue count does not match the comparison list.")
        if self.summary.total_issue_count != self.total_issue_count:
            raise ValueError("Issue review summary total does not match the report total.")

        state_total = (
            self.summary.consistent_count
            + self.summary.consistent_with_review_count
            + self.summary.material_disagreement_count
            + self.summary.possible_omission_count
            + self.summary.insufficient_evidence_count
            + self.summary.review_required_count
        )
        if state_total != self.total_issue_count:
            raise ValueError("Issue review summary state counts do not cover every AuditPlan issue.")

        human_count = sum(item.requires_human_review for item in self.comparisons)
        if self.summary.human_review_required_count != human_count:
            raise ValueError("Human review summary count does not match issue comparisons.")

        must_review = (not self.planning_coverage_complete) or human_count > 0
        expected_final = (
            IssueReviewFinalState.HUMAN_REVIEW_REQUIRED
            if must_review
            else IssueReviewFinalState.NO_MANDATORY_REVIEW
        )
        if self.final_state != expected_final:
            raise ValueError("Final review state does not match deterministic issue review requirements.")
        return self
