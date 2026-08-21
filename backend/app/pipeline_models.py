from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .pipeline_control_models import ProviderExecutionMode

PIPELINE_SCHEMA_VERSION = "1.3.0"
PIPELINE_ENGINE_VERSION = "stage13g-4-1.0.0"


class PipelineStatus(str, Enum):
    QUEUED = "QUEUED"
    WAITING_WORKER = "WAITING_WORKER"
    RUNNING = "RUNNING"
    WAITING_CONFIGURATION = "WAITING_CONFIGURATION"
    WAITING_OPTIONAL_COMPONENT = "WAITING_OPTIONAL_COMPONENT"
    PAUSED_BEFORE_PROVIDER = "PAUSED_BEFORE_PROVIDER"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETE = "COMPLETE"


class PipelineStage(str, Enum):
    INGEST = "INGEST"
    OCR = "OCR"
    STRUCTURE = "STRUCTURE"
    RULES = "RULES"

    # Stage 13G authoritative production chain.
    AUDIT_PLAN = "AUDIT_PLAN"
    ISSUE_LEGAL_CONTEXT = "ISSUE_LEGAL_CONTEXT"
    ISSUE_PRIMARY_AUDIT = "ISSUE_PRIMARY_AUDIT"
    ISSUE_SECONDARY_REVIEW = "ISSUE_SECONDARY_REVIEW"
    ISSUE_REVIEW_REPORT = "ISSUE_REVIEW_REPORT"

    # Retained so persisted RC2/Stage 13A pipeline.json files remain parseable.
    # New pipelines never emit these legacy stage records.
    PRIMARY_AUDIT = "PRIMARY_AUDIT"
    SECONDARY_REVIEW = "SECONDARY_REVIEW"
    REVIEW_REPORT = "REVIEW_REPORT"

    COMPLETE = "COMPLETE"


class PipelineStageState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    SKIPPED = "SKIPPED"
    WAITING = "WAITING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PipelineStartRequest(BaseModel):
    as_of: date = Field(default_factory=date.today)
    use_semantic: bool = False
    provider_mode: ProviderExecutionMode = ProviderExecutionMode.AUTO_CONTINUE


class PipelineStageRecord(BaseModel):
    stage: PipelineStage
    state: PipelineStageState = PipelineStageState.PENDING
    label: str
    progress_percent: int = Field(ge=0, le=100)
    detail: str = ""
    reused_existing_artifact: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PipelineReport(BaseModel):
    schema_version: str = PIPELINE_SCHEMA_VERSION
    engine_version: str = PIPELINE_ENGINE_VERSION
    job_id: UUID
    status: PipelineStatus
    current_stage: PipelineStage
    progress_percent: int = Field(ge=0, le=100)
    as_of: date
    use_semantic: bool = False
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_detail: str | None = None
    stages: list[PipelineStageRecord] = Field(default_factory=list)
