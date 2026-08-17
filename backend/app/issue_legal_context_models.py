from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .audit_plan_models import AuditPlanSource, ReviewPriority
from .legal.retrieval_models import RetrievalCandidate, RetrievalResponse

ISSUE_LEGAL_CONTEXT_SCHEMA_VERSION = "1.0.0"
ISSUE_LEGAL_CONTEXT_BUILDER_VERSION = "stage13d-1.0.0"


class IssueLegalSupportState(str, Enum):
    EVIDENCE_FOUND = "EVIDENCE_FOUND"
    EVIDENCE_FOUND_WITH_LIMITATIONS = "EVIDENCE_FOUND_WITH_LIMITATIONS"
    NO_MATCH_IN_LOCAL_CORPUS = "NO_MATCH_IN_LOCAL_CORPUS"
    VERSION_REVIEW_REQUIRED = "VERSION_REVIEW_REQUIRED"


class IssueRetrievalRun(BaseModel):
    query_index: int = Field(ge=1)
    query: str
    response: RetrievalResponse


class IssueLegalEvidenceHit(BaseModel):
    legal_evidence_id: str
    matched_query_indexes: list[int] = Field(min_length=1)
    best_rank: int = Field(ge=1)
    candidate: RetrievalCandidate


class IssueLegalEvidencePackage(BaseModel):
    issue_id: str
    topic: str
    priority: ReviewPriority
    sources: list[AuditPlanSource] = Field(min_length=1)
    questions: list[str] = Field(default_factory=list)
    contract_object_ids: list[str] = Field(default_factory=list)
    contract_evidence_ids: list[str] = Field(default_factory=list)
    retrieval_runs: list[IssueRetrievalRun] = Field(min_length=1)
    legal_evidence: list[IssueLegalEvidenceHit] = Field(default_factory=list)
    support_state: IssueLegalSupportState
    warnings: list[str] = Field(default_factory=list)


class IssueLegalContextArtifact(BaseModel):
    schema_version: str = ISSUE_LEGAL_CONTEXT_SCHEMA_VERSION
    builder_version: str = ISSUE_LEGAL_CONTEXT_BUILDER_VERSION
    job_id: UUID
    as_of: date
    use_semantic: bool
    top_k_per_query: int = Field(ge=1, le=20)
    audit_plan_schema_version: str
    audit_planner_version: str
    audit_plan_fingerprint: str
    contract_source_fingerprint: str
    contract_content_fingerprint: str
    legal_source_fingerprint: str
    lexical_index_version: str | None = None
    total_issue_count: int = Field(ge=0)
    total_query_count: int = Field(ge=0)
    issues: list[IssueLegalEvidencePackage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifact_fingerprint: str


class IssueLegalContextRunRequest(BaseModel):
    as_of: date
    use_semantic: bool = False
    top_k_per_query: int = Field(default=5, ge=1, le=20)
