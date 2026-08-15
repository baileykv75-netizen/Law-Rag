from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .artifact_integrity import inspect_job_artifact_integrity
from .artifact_integrity_models import JobArtifactIntegrityReport
from .runtime_health_models import RuntimeHealthReport
from .startup_diagnostics import inspect_startup_health

router = APIRouter(prefix="/api/runtime", tags=["runtime-health"])


@router.get("/health", response_model=RuntimeHealthReport)
def runtime_health() -> RuntimeHealthReport:
    """Return local, non-mutating startup/runtime diagnostics without provider/network calls."""

    return inspect_startup_health()


@router.get("/jobs/{job_id}/integrity", response_model=JobArtifactIntegrityReport)
def job_artifact_integrity(job_id: UUID) -> JobArtifactIntegrityReport:
    """Inspect persisted job-artifact schemas and cross-artifact links without mutating them."""

    try:
        return inspect_job_artifact_integrity(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
