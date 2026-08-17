from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .pipeline import (
    PipelineError,
    PipelineNotFoundError,
    load_pipeline_report,
    retry_pipeline,
    start_pipeline,
)
from .pipeline_models import PipelineReport, PipelineStartRequest

router = APIRouter()


@router.post(
    "/api/documents/{job_id}/pipeline",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_document_pipeline(job_id: UUID, request: PipelineStartRequest) -> PipelineReport:
    """Queue the application-owned audit pipeline and return immediately.

    The worker may perform explicit DeepSeek/Kimi calls as part of the normal audit
    pipeline. Polling the GET endpoint never performs provider work.
    """

    try:
        return start_pipeline(job_id, request)
    except PipelineNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/pipeline", response_model=PipelineReport)
def get_document_pipeline(job_id: UUID) -> PipelineReport:
    """Read persisted pipeline state only; this endpoint never resumes or calls providers."""

    try:
        return load_pipeline_report(job_id)
    except PipelineNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post(
    "/api/documents/{job_id}/pipeline/retry",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_document_pipeline(job_id: UUID) -> PipelineReport:
    """Resume a failed/waiting pipeline using its original as_of and semantic settings."""

    try:
        return retry_pipeline(job_id)
    except PipelineNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
