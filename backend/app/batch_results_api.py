from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from .batch_results import (
    BatchNotFoundError,
    BatchResultError,
    create_batch,
    load_batch,
    register_batch_job,
    summarize_batch,
    summarize_latest_batch,
)
from .batch_results_models import BatchJobState, BatchManifest, BatchResultSummary
from .job_history import JobHistoryError, get_job_history, list_job_history
from .job_history_models import JobHistoryItem, JobHistoryPage
from .safe_persistence import atomic_write_text
from .storage import runtime_dir
from .storage_management import (
    JobCleanupNotAllowed,
    StorageManagementError,
    delete_jobs_storage_bulk,
    delete_job_storage,
    storage_summary,
)
from .storage_management_models import BulkJobCleanupRequest, BulkJobCleanupResponse, JobCleanupResult, StorageSummary

router = APIRouter(prefix="/api/batches", tags=["batch-results"])


class JobCleanupRequest(BaseModel):
    confirm_job_id: UUID


def _is_provider_failure(code: str | None, detail: str | None) -> bool:
    value = f"{code or ''} {detail or ''}".lower()
    markers = (
        "deepseek",
        "kimi",
        "provider",
        "rate_limit",
        "service_unavailable",
        "network_transient",
        "api key",
        "credential",
    )
    return any(marker in value for marker in markers)


def _normalize_user_summary(summary: BatchResultSummary) -> BatchResultSummary:
    """Keep technical/system states distinct from completed contract results.

    Corrupt historical rows remain visible for cleanup but never inflate the
    valid-contract denominator. A recoverable provider outage is normalized to
    WAITING even when older batch code initially rendered any non-terminal
    pipeline state as PROCESSING.
    """

    for item in summary.jobs:
        if item.pipeline_status == "WAITING_EXTERNAL_SERVICE" and item.state != BatchJobState.INVALID:
            item.state = BatchJobState.WAITING
            item.needs_attention = True

    valid_jobs = [item for item in summary.jobs if item.state != BatchJobState.INVALID]
    invalid_jobs = [item for item in summary.jobs if item.state == BatchJobState.INVALID]
    failed_jobs = [item for item in valid_jobs if item.state == BatchJobState.FAILED]
    provider_failed = [
        item for item in failed_jobs if _is_provider_failure(item.failure_code, item.failure_detail)
    ]
    summary.total_jobs = len(valid_jobs)
    summary.complete_jobs = sum(item.state == BatchJobState.COMPLETE for item in valid_jobs)
    summary.waiting_jobs = sum(item.state == BatchJobState.WAITING for item in valid_jobs)
    summary.external_service_waiting_jobs = sum(
        item.pipeline_status == "WAITING_EXTERNAL_SERVICE" for item in valid_jobs
    )
    summary.cancelled_jobs = sum(item.state == BatchJobState.CANCELLED for item in valid_jobs)
    summary.processing_jobs = sum(item.state == BatchJobState.PROCESSING for item in valid_jobs)
    summary.failed_jobs = len(failed_jobs)
    summary.invalid_jobs = len(invalid_jobs)
    summary.provider_failed_jobs = len(provider_failed)
    summary.system_error_jobs = len(invalid_jobs) + (len(failed_jobs) - len(provider_failed))
    return summary


@router.post("", response_model=BatchManifest, status_code=status.HTTP_201_CREATED)
def create_batch_api() -> BatchManifest:
    return create_batch()


@router.post("/history/jobs/delete", response_model=BulkJobCleanupResponse)
def delete_jobs_storage_bulk_api(request: BulkJobCleanupRequest) -> BulkJobCleanupResponse:
    """Delete selected job-private runtime roots without requiring UUID typing."""

    try:
        return delete_jobs_storage_bulk(request.job_ids, confirm=request.confirm, mode=request.mode)
    except JobCleanupNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (StorageManagementError, JobHistoryError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/{batch_id}/jobs/{job_id}", response_model=BatchManifest)
def register_batch_job_api(batch_id: UUID, job_id: UUID) -> BatchManifest:
    try:
        return register_batch_job(batch_id, job_id)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BatchResultError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.delete("/{batch_id}/invalid-jobs/{job_id}", response_model=BatchResultSummary)
def remove_invalid_job_from_batch_api(batch_id: UUID, job_id: UUID) -> BatchResultSummary:
    """Detach one corrupt/orphan record from a batch without deleting local files.

    This action is intentionally conservative: only a record already classified as
    INVALID may be detached. The Law-Rag runtime copy remains available in History
    for diagnostics or a later explicit storage cleanup.
    """

    try:
        summary = summarize_batch(batch_id)
        candidate = next((item for item in summary.jobs if item.job_id == job_id), None)
        if candidate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该任务不在此批次中。")
        if candidate.state != BatchJobState.INVALID:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="只有已确认损坏或不可恢复的旧任务记录才能从批次中移除。",
            )
        manifest = load_batch(batch_id)
        manifest.job_ids = [value for value in manifest.job_ids if value != job_id]
        path = runtime_dir() / "batches" / f"{batch_id}.json"
        atomic_write_text(path, manifest.model_dump_json(indent=2))
        return _normalize_user_summary(summarize_batch(batch_id))
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BatchResultError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/recent", response_model=BatchResultSummary | None)
def latest_batch_results_api() -> BatchResultSummary | None:
    try:
        summary = summarize_latest_batch()
        return None if summary is None else _normalize_user_summary(summary)
    except BatchResultError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/history/jobs", response_model=JobHistoryPage)
def job_history_api(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> JobHistoryPage:
    """List persisted local jobs without triggering OCR, retrieval or providers."""

    try:
        return list_job_history(offset=offset, limit=limit)
    except JobHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/history/storage", response_model=StorageSummary)
def storage_summary_api() -> StorageSummary:
    """Report local runtime storage without mutating job or legal data."""

    try:
        return storage_summary()
    except (StorageManagementError, JobHistoryError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/history/jobs/{job_id}", response_model=JobHistoryItem)
def job_history_item_api(job_id: UUID) -> JobHistoryItem:
    try:
        return get_job_history(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.delete("/history/jobs/{job_id}", response_model=JobCleanupResult)
def delete_job_storage_api(job_id: UUID, request: JobCleanupRequest) -> JobCleanupResult:
    """Delete one terminal Job's private runtime roots after explicit UUID confirmation."""

    try:
        return delete_job_storage(job_id, confirm_job_id=request.confirm_job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobCleanupNotAllowed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (StorageManagementError, JobHistoryError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/{batch_id}", response_model=BatchResultSummary)
def batch_results_api(batch_id: UUID) -> BatchResultSummary:
    try:
        return _normalize_user_summary(summarize_batch(batch_id))
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BatchResultError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
