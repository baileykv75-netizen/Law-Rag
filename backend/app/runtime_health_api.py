from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .artifact_integrity import inspect_job_artifact_integrity
from .artifact_integrity_models import JobArtifactIntegrityReport
from .runtime_encryption import (
    RuntimeEncryptionError,
    RuntimeEncryptionRequiredError,
    runtime_encryption_overview,
    set_runtime_encryption_mode,
)
from .runtime_encryption_models import RuntimeEncryptionOverview, RuntimeEncryptionUpdateRequest
from .runtime_health_models import RuntimeHealthReport
from .startup_diagnostics import inspect_startup_health

router = APIRouter(prefix="/api/runtime", tags=["runtime-health"])


@router.get("/health", response_model=RuntimeHealthReport)
def runtime_health() -> RuntimeHealthReport:
    """Return local, non-mutating startup/runtime diagnostics without provider/network calls."""

    return inspect_startup_health()


@router.get("/encryption", response_model=RuntimeEncryptionOverview)
def runtime_encryption_status() -> RuntimeEncryptionOverview:
    """Inspect Law-Rag managed at-rest protection without changing filesystem state."""

    try:
        return runtime_encryption_overview()
    except RuntimeEncryptionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.put("/encryption", response_model=RuntimeEncryptionOverview)
def update_runtime_encryption(request: RuntimeEncryptionUpdateRequest) -> RuntimeEncryptionOverview:
    """Apply/persist OFF, AUTO, or REQUIRED runtime-encryption policy.

    Disabling the managed policy never decrypts files that Windows already
    protects. REQUIRED fails closed when the platform cannot verify EFS.
    """

    try:
        return set_runtime_encryption_mode(request.mode)
    except RuntimeEncryptionRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeEncryptionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/integrity", response_model=JobArtifactIntegrityReport)
def job_artifact_integrity(job_id: UUID) -> JobArtifactIntegrityReport:
    """Inspect persisted job-artifact schemas and cross-artifact links without mutating them."""

    try:
        return inspect_job_artifact_integrity(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
