from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .issue_primary_audit import (
    IssuePrimaryAuditConfigurationError,
    IssuePrimaryAuditError,
    IssuePrimaryAuditStaleError,
    IssuePrimaryAuditValidationError,
    load_issue_primary_audit,
    run_issue_primary_audit,
)
from .issue_primary_audit_models import IssuePrimaryAuditArtifact, IssuePrimaryAuditRunRequest
from .pipeline_control import PipelineCancellationRequested, ProviderBoundaryPaused

router = APIRouter()


@router.post("/api/documents/{job_id}/issue-primary-audit", response_model=IssuePrimaryAuditArtifact)
def create_issue_primary_audit(job_id: UUID, request: IssuePrimaryAuditRunRequest) -> IssuePrimaryAuditArtifact:
    """Run the Stage 13E DeepSeek primary audit one planned issue at a time.

    Every outbound issue request crosses the persisted Stage 13A provider boundary.
    The artifact is checkpointed after each completed issue; incomplete checkpoints
    are never represented as a complete audit.
    """

    try:
        return run_issue_primary_audit(job_id, provider_name=request.provider)
    except ProviderBoundaryPaused as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "detail": exc.detail},
        ) from exc
    except PipelineCancellationRequested as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "PIPELINE_CANCEL_REQUESTED", "detail": str(exc)},
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssuePrimaryAuditConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except IssuePrimaryAuditStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ISSUE_PRIMARY_AUDIT_STALE", "detail": str(exc)},
        ) from exc
    except IssuePrimaryAuditValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except IssuePrimaryAuditError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/issue-primary-audit", response_model=IssuePrimaryAuditArtifact)
def get_issue_primary_audit(job_id: UUID) -> IssuePrimaryAuditArtifact:
    """Read the persisted Stage 13E checkpoint/result only; never calls a provider."""

    try:
        return load_issue_primary_audit(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssuePrimaryAuditStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ISSUE_PRIMARY_AUDIT_STALE", "detail": str(exc)},
        ) from exc
    except IssuePrimaryAuditValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
