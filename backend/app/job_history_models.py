from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class JobHistoryIntegrity(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


class JobHistoryItem(BaseModel):
    job_id: UUID
    filename: str | None = None
    document_kind: str | None = None
    architecture: str | None = None
    pipeline_status: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    integrity: JobHistoryIntegrity
    terminal: bool
    can_delete: bool
    storage_bytes: int = Field(ge=0)
    warning: str | None = None


class JobHistoryPage(BaseModel):
    total_count: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    items: list[JobHistoryItem]
