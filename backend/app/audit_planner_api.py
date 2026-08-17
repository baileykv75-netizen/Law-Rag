from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .audit_plan_models import AuditPlan, AuditPlannerRunRequest
from .audit_planner import (
    AuditPlannerError,
    AuditPlannerValidationError,
    load_audit_plan,
    run_audit_planner,
)
from .audit_planner_provider import AuditPlannerProviderError
from .pipeline_control import PipelineCancellationRequested, ProviderBoundaryPaused

router = APIRouter()


@router.post("/api/documents/{job_id}/audit-plan", response_model=AuditPlan)
def create_audit_plan(job_id: UUID, request: AuditPlannerRunRequest) -> AuditPlan:
    """Create the evidence-bounded Audit Plan.

    Contracts within the direct budget use one Planner pass. Larger contracts
    automatically use Stage 13C hierarchical chunk planning plus a global
    synthesis pass. Every external pass crosses the Stage 13A provider boundary.
    """

    try:
        return run_audit_planner(job_id, provider_name=request.provider)
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
    except AuditPlannerProviderError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (AuditPlannerValidationError, AuditPlannerError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/audit-plan", response_model=AuditPlan)
def get_audit_plan(job_id: UUID) -> AuditPlan:
    """Read the persisted Audit Plan only; this endpoint never calls a provider."""

    try:
        return load_audit_plan(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AuditPlannerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
