from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

BATCH_SCHEMA_VERSION = "1.0.0"
BATCH_RESULT_SCHEMA_VERSION = "1.0.0"


class BatchManifest(BaseModel):
    schema_version: str = BATCH_SCHEMA_VERSION
    batch_id: UUID
    created_at: datetime
    job_ids: list[UUID] = Field(default_factory=list)


class BatchJobState(str, Enum):
    PROCESSING = "PROCESSING"
    WAITING = "WAITING"
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
    final_review_state: str | None = None
    human_review_required: bool = False
    finding_counts: SeverityCounts = Field(default_factory=SeverityCounts)
    possible_omissions: int = Field(default=0, ge=0)
    material_disagreement: bool = False
    needs_attention: bool = False
    priority_rank: int = Field(default=0, ge=0)


class BatchResultSummary(BaseModel):
    schema_version: str = BATCH_RESULT_SCHEMA_VERSION
    batch_id: UUID
    created_at: datetime
    jobs: list[BatchJobResult] = Field(default_factory=list)
    total_jobs: int = Field(ge=0)
    complete_jobs: int = Field(ge=0)
    waiting_jobs: int = Field(ge=0)
    failed_jobs: int = Field(ge=0)
    human_review_required_jobs: int = Field(ge=0)
    processing_jobs: int = Field(ge=0)
