from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

BATCH_SCHEMA_VERSION = "1.0.0"
BATCH_RESULT_SCHEMA_VERSION = "1.4.0"


class BatchManifest(BaseModel):
    schema_version: str = BATCH_SCHEMA_VERSION
    batch_id: UUID
    created_at: datetime
    job_ids: list[UUID] = Field(default_factory=list)


class BatchJobState(str, Enum):
    PROCESSING = "PROCESSING"
    WAITING = "WAITING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"
    INVALID = "INVALID"


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class BatchJobResult(BaseModel):
    job_id: UUID
    filename: str
    state: BatchJobState
    progress_percent: int = Field(ge=0, le=100)
    pipeline_status: str | None = None
    failure_code: str | None = None
    failure_detail: str | None = None
    architecture: str | None = None
    final_review_state: str | None = None
    human_review_required: bool = False
    finding_counts: SeverityCounts = Field(default_factory=SeverityCounts)
    issue_count: int = Field(default=0, ge=0)
    possible_omissions: int = Field(default=0, ge=0)
    material_disagreement: bool = False
    material_disagreement_count: int = Field(default=0, ge=0)
    insufficient_evidence_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    planning_coverage_complete: bool | None = None
    planning_coverage_reviewed_count: int = Field(default=0, ge=0)
    planning_coverage_total_count: int = Field(default=0, ge=0)
    human_review_resolved_count: int = Field(default=0, ge=0)
    human_review_outstanding_count: int = Field(default=0, ge=0)
    human_review_stale_count: int = Field(default=0, ge=0)
    needs_attention: bool = False
    priority_rank: int = Field(default=0, ge=0)


class BatchResultSummary(BaseModel):
    schema_version: str = BATCH_RESULT_SCHEMA_VERSION
    batch_id: UUID
    created_at: datetime
    jobs: list[BatchJobResult] = Field(default_factory=list)
    # total_jobs intentionally counts only recoverable/valid contract tasks. Corrupt
    # historical records remain visible in jobs for cleanup but cannot inflate the
    # contract denominator or legal-risk statistics.
    total_jobs: int = Field(ge=0)
    complete_jobs: int = Field(ge=0)
    waiting_jobs: int = Field(ge=0)
    external_service_waiting_jobs: int = Field(default=0, ge=0)
    cancelled_jobs: int = Field(default=0, ge=0)
    failed_jobs: int = Field(ge=0)
    invalid_jobs: int = Field(default=0, ge=0)
    provider_failed_jobs: int = Field(default=0, ge=0)
    system_error_jobs: int = Field(default=0, ge=0)
    human_review_required_jobs: int = Field(ge=0)
    processing_jobs: int = Field(ge=0)
    issue_v1_jobs: int = Field(default=0, ge=0)
    legacy_rc2_jobs: int = Field(default=0, ge=0)
    coverage_incomplete_jobs: int = Field(default=0, ge=0)
