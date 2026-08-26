from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


HUMAN_REVIEW_SCHEMA_VERSION = "1.1.0"


class HumanDecisionState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    NEEDS_MORE_REVIEW = "NEEDS_MORE_REVIEW"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    MODIFIED = "MODIFIED"
    NEEDS_LAWYER_REVIEW = "NEEDS_LAWYER_REVIEW"


class HumanReviewTargetType(str, Enum):
    # Legacy RC2 identities remain valid historical targets.
    FINDING = "finding"
    OMISSION = "omission"
    # Issue V1 decisions bind directly to the authoritative AuditPlan identity.
    ISSUE = "issue"


class HumanDecisionRequest(BaseModel):
    target_type: HumanReviewTargetType
    target_id: str = Field(min_length=1, max_length=160)
    state: HumanDecisionState
    reviewer_note: str = Field(default="", max_length=4000)


class HumanDecisionRevision(BaseModel):
    schema_version: str = HUMAN_REVIEW_SCHEMA_VERSION
    decision_id: str
    revision: int = Field(ge=1)
    job_id: UUID
    target_type: HumanReviewTargetType
    target_id: str
    state: HumanDecisionState
    reviewer_note: str
    decided_at: datetime
    contract_evidence_ids: list[str] = Field(default_factory=list)
    legal_evidence_ids: list[str] = Field(default_factory=list)
    # Kept under the historical field name so old RC2 revisions remain readable.
    # For target_type=issue this stores issue-review-report.json's artifact fingerprint.
    review_report_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class HumanDecisionView(HumanDecisionRevision):
    is_stale: bool = False


class HumanReviewArtifact(BaseModel):
    schema_version: str = HUMAN_REVIEW_SCHEMA_VERSION
    job_id: UUID
    revisions: list[HumanDecisionRevision] = Field(default_factory=list)


class HumanReviewView(BaseModel):
    schema_version: str = HUMAN_REVIEW_SCHEMA_VERSION
    job_id: UUID
    authoritative_architecture: Literal["LEGACY_RC2", "ISSUE_V1"]
    current_review_report_artifact: Literal["review-report.json", "issue-review-report.json"]
    current_review_report_fingerprint: str
    revisions: list[HumanDecisionView] = Field(default_factory=list)
    latest_by_target: dict[str, HumanDecisionView] = Field(default_factory=dict)
