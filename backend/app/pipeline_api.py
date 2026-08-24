from __future__ import annotations

import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .job_architecture import JobArchitectureError, resolve_job_architecture
from .job_architecture_models import (
    JobArchitectureSummary,
    LegacyPipelineMigrationRequest,
)
from .legacy_pipeline_migration import LegacyPipelineMigrationError, migrate_legacy_pipeline
from .pipeline import (
    PipelineError,
    PipelineNotFoundError,
    approve_provider_and_resume,
    cancel_pipeline,
    load_pipeline_report,
    pause_before_provider,
    resume_cancelled_pipeline,
    retry_pipeline,
    set_pipeline_provider_mode,
    start_pipeline,
)
from .pipeline_control import PipelineControlError, get_pipeline_control
from .pipeline_control_models import (
    PipelineControl,
    PipelineControlActionResponse,
    PipelineControlUpdateRequest,
)
from .pipeline_models import PipelineReport, PipelineStartRequest

router = APIRouter()


def _raise_pipeline_http(exc: Exception) -> None:
    if isinstance(exc, PipelineNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, PipelineControlError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _load_pipeline_report_for_poll(job_id: UUID, *, attempts: int = 5) -> PipelineReport:
    """Tolerate a short Windows persistence/read transition during UI polling.

    Polling is read-only and must never turn one transient filesystem/validation window
    into a user-visible failed audit. Genuine persistent corruption still fails after a
    short bounded retry window and remains fail-closed.
    """

    last_error: PipelineError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return load_pipeline_report(job_id)
        except PipelineNotFoundError:
            raise
        except PipelineError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(min(0.03 * (2 ** (attempt - 1)), 0.3))
    assert last_error is not None
    raise last_error


@router.get("/api/documents/{job_id}/architecture", response_model=JobArchitectureSummary)
def get_document_architecture(job_id: UUID) -> JobArchitectureSummary:
    """Resolve the authoritative audit artifact family without mutating the job."""

    try:
        return resolve_job_architecture(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except JobArchitectureError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post(
    "/api/documents/{job_id}/pipeline",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_document_pipeline(job_id: UUID, request: PipelineStartRequest) -> PipelineReport:
    """Queue the application-owned audit pipeline and return immediately.

    Provider execution follows the explicit provider_mode in this request. Polling
    the GET endpoint never performs provider work.
    """

    try:
        return start_pipeline(job_id, request)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.get("/api/documents/{job_id}/pipeline", response_model=PipelineReport)
def get_document_pipeline(job_id: UUID) -> PipelineReport:
    """Read persisted pipeline state only; this endpoint never resumes or calls providers."""

    try:
        return _load_pipeline_report_for_poll(job_id)
    except PipelineNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="本地任务状态暂时无法稳定读取，请稍后重试。",
            headers={"Retry-After": "1"},
        ) from exc


@router.get("/api/documents/{job_id}/pipeline/control", response_model=PipelineControl)
def get_document_pipeline_control(job_id: UUID) -> PipelineControl:
    """Read provider/cancel intent only. Missing legacy control is synthesized and not persisted."""

    try:
        _load_pipeline_report_for_poll(job_id)
        return get_pipeline_control(job_id)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.put("/api/documents/{job_id}/pipeline/control", response_model=PipelineControl)
def update_document_pipeline_control(job_id: UUID, request: PipelineControlUpdateRequest) -> PipelineControl:
    """Change future provider behavior without killing an active worker/provider request."""

    try:
        return set_pipeline_provider_mode(job_id, request.provider_mode)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.post(
    "/api/documents/{job_id}/pipeline/approve-provider",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def approve_document_provider(job_id: UUID) -> PipelineReport:
    """Explicitly approve the bounded DeepSeek + Kimi provider phase and resume."""

    try:
        return approve_provider_and_resume(job_id)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.post(
    "/api/documents/{job_id}/pipeline/pause-provider",
    response_model=PipelineControl,
)
def pause_document_provider(job_id: UUID) -> PipelineControl:
    """Require approval before any provider call that has not already started."""

    try:
        return pause_before_provider(job_id)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.post(
    "/api/documents/{job_id}/pipeline/cancel",
    response_model=PipelineControlActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_document_pipeline(job_id: UUID) -> PipelineControlActionResponse:
    """Persist a cooperative cancel request.

    If an external request has already crossed the provider boundary, that request
    cannot be retracted; Law-Rag stops before any subsequent stage.
    """

    try:
        report, control = cancel_pipeline(job_id)
        in_flight = control.active_provider is not None
        return PipelineControlActionResponse(
            control=control,
            provider_in_flight=in_flight,
            detail=report.failure_detail or "取消请求已记录。",
        )
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.post(
    "/api/documents/{job_id}/pipeline/resume",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_document_pipeline(job_id: UUID) -> PipelineReport:
    """Explicitly restart a previously cancelled pipeline with its existing provider policy."""

    try:
        return resume_cancelled_pipeline(job_id)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.post(
    "/api/documents/{job_id}/pipeline/retry",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_document_pipeline(job_id: UUID) -> PipelineReport:
    """Resume a failed/waiting pipeline using its original settings and provider policy."""

    try:
        return retry_pipeline(job_id)
    except (PipelineNotFoundError, PipelineControlError, PipelineError) as exc:
        _raise_pipeline_http(exc)
        raise AssertionError("unreachable")


@router.post(
    "/api/documents/{job_id}/pipeline/migrate-legacy",
    response_model=PipelineReport,
    status_code=status.HTTP_202_ACCEPTED,
)
def migrate_document_legacy_pipeline(
    job_id: UUID,
    request: LegacyPipelineMigrationRequest,
) -> PipelineReport:
    """Explicitly move an eligible unfinished RC2 job onto the Issue V1 pipeline.

    The old pipeline state is preserved before replacement. Legacy Stage 8/9
    reports stay on disk as historical artifacts and are not consumed by the new
    authoritative chain.
    """

    try:
        return migrate_legacy_pipeline(job_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (JobArchitectureError, LegacyPipelineMigrationError, PipelineControlError, PipelineError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
