from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from .batch_results import (
    BatchNotFoundError,
    BatchResultError,
    create_batch,
    register_batch_job,
    summarize_batch,
    summarize_latest_batch,
)
from .batch_results_models import BatchManifest, BatchResultSummary
from .job_history import JobHistoryError, get_job_history, list_job_history
from .job_history_models import JobHistoryItem, JobHistoryPage
from .storage_management import (
    JobCleanupNotAllowed,
    StorageManagementError,
    delete_job_storage,
    storage_summary,
)
from .storage_management_models import JobCleanupResult, StorageSummary

router = APIRouter(prefix="/api/batches", tags=["batch-results"])


class JobCleanupRequest(BaseModel):
    confirm_job_id: UUID


@router.post("", response_model=BatchManifest, status_code=status.HTTP_201_CREATED)
def create_batch_api() -> BatchManifest:
    return create_batch()


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


@router.get("/recent", response_model=BatchResultSummary | None)
def latest_batch_results_api() -> BatchResultSummary | None:
    try:
        return summarize_latest_batch()
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
        return summarize_batch(batch_id)
    except BatchNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BatchResultError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
