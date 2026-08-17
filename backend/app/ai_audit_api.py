from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from .ai_audit import (
    AiAuditConfigurationError,
    AiAuditError,
    AiAuditValidationError,
    load_ai_audit_report,
    run_primary_ai_audit,
)
from .ai_audit_models import AiAuditReport, AiAuditRunRequest, ProviderHealth
from .ai_audit_providers import PrimaryAuditProviderError, provider_from_name
from .audit_planner_api import router as audit_planner_router
from .provider_settings_api import router as provider_settings_router
from .secondary_review_api import router as secondary_review_router
from .workspace_api import router as workspace_router

router = APIRouter()
router.include_router(provider_settings_router)
router.include_router(audit_planner_router)
router.include_router(secondary_review_router)
router.include_router(workspace_router)


@router.get("/api/ai/providers/health", response_model=ProviderHealth)
def primary_provider_health(
    provider: str = Query(default="deepseek", description="Primary Stage 8 audit provider"),
) -> ProviderHealth:
    try:
        return provider_from_name(provider).health()
    except PrimaryAuditProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/api/documents/{job_id}/ai-audit", response_model=AiAuditReport)
def run_ai_audit(job_id: UUID, request: AiAuditRunRequest) -> AiAuditReport:
    try:
        return run_primary_ai_audit(job_id, request)
    except AiAuditConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AiAuditValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except AiAuditError as exc:
        message = str(exc)
        if "required before primary AI audit" in message or "retrieval index is not ready" in message:
            http_status = status.HTTP_409_CONFLICT
        else:
            http_status = status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=http_status, detail=message) from exc


@router.get("/api/documents/{job_id}/ai-audit", response_model=AiAuditReport)
def get_ai_audit(job_id: UUID) -> AiAuditReport:
    try:
        return load_ai_audit_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AiAuditValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
