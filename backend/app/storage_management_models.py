from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class CleanupTransactionState(str, Enum):
    PREPARED = "PREPARED"
    ROOTS_MOVED = "ROOTS_MOVED"
    REFERENCES_UPDATED = "REFERENCES_UPDATED"


class CleanupTransaction(BaseModel):
    schema_version: str = "1.0.0"
    cleanup_id: UUID
    job_id: UUID
    created_at: datetime
    state: CleanupTransactionState = CleanupTransactionState.PREPARED
    original_storage_bytes: int = Field(ge=0)
    pipeline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    moved_roots: list[str] = Field(default_factory=list)


class JobCleanupResult(BaseModel):
    job_id: UUID
    deleted: bool
    reclaimed_bytes: int = Field(ge=0)
    batch_manifests_updated: int = Field(ge=0)
    latest_batch_repaired: bool
    shared_legal_untouched: bool = True


class BulkJobCleanupRequest(BaseModel):
    job_ids: list[UUID] = Field(min_length=1, max_length=200)
    mode: str = "force_safe"
    confirm: bool


class SkippedJobCleanup(BaseModel):
    job_id: UUID
    reason: str


class BulkJobCleanupResponse(BaseModel):
    deleted: list[JobCleanupResult] = Field(default_factory=list)
    skipped: list[SkippedJobCleanup] = Field(default_factory=list)
    reclaimed_bytes: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    shared_legal_untouched: bool = True


class StorageSummary(BaseModel):
    job_count: int = Field(ge=0)
    terminal_deletable_job_count: int = Field(ge=0)
    active_or_protected_job_count: int = Field(ge=0)
    jobs_bytes: int = Field(ge=0)
    batches_bytes: int = Field(ge=0)
    shared_legal_bytes: int = Field(ge=0)
    cleanup_bytes: int = Field(ge=0)
    other_runtime_bytes: int = Field(ge=0)
    total_runtime_bytes: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
