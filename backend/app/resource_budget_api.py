from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .resource_budget import (
    ResourceBudgetError,
    resource_budget_overview,
    set_resource_budget_policy,
)
from .resource_budget_models import ResourceBudgetOverview, ResourceBudgetUpdateRequest

router = APIRouter(tags=["resource-budget"])


@router.get("/api/documents/{job_id}/resource-budget", response_model=ResourceBudgetOverview)
def get_resource_budget(job_id: UUID) -> ResourceBudgetOverview:
    """Read local provider usage/budget state without invoking a provider."""

    try:
        return resource_budget_overview(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResourceBudgetError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.put("/api/documents/{job_id}/resource-budget", response_model=ResourceBudgetOverview)
def put_resource_budget(job_id: UUID, request: ResourceBudgetUpdateRequest) -> ResourceBudgetOverview:
    """Persist user-selected per-Job provider limits; this never starts provider work."""

    try:
        return set_resource_budget_policy(job_id, request.policy)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResourceBudgetError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
