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
from .issue_legal_context_api import router as issue_legal_context_router
from .issue_primary_audit_api import router as issue_primary_audit_router
from .issue_review_report_api import router as issue_review_report_router
from .issue_secondary_review_api import router as issue_secondary_review_router
from .provider_settings_api import router as provider_settings_router
from .report_export_api import router as report_export_router
from .resource_budget_api import router as resource_budget_router
from .secondary_review_api import router as secondary_review_router
from .workspace_api import router as workspace_router

router = APIRouter()
router.include_router(provider_settings_router)
router.include_router(audit_planner_router)
router.include_router(issue_legal_context_router)
router.include_router(issue_primary_audit_router)
router.include_router(issue_secondary_review_router)
router.include_router(issue_review_report_router)
router.include_router(secondary_review_router)
router.include_router(workspace_router)
router.include_router(report_export_router)
router.include_router(resource_budget_router)


@router.get("/api/ai/providers/health", response_model=ProviderHealth)
def primary_provider_health(
    provider: str = Query(default="deepseek", description="Primary Stage 8 audit provider"),
) -> ProviderHealth:
    try:
        return provider_from_name(provider).health()
    except PrimaryAuditProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/api/documents/{job_id}/ai-audit", response_model=AiAuditReport)
def run_document_ai_audit(job_id: UUID, request: AiAuditRunRequest) -> AiAuditReport:
    try:
        return run_primary_ai_audit(job_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AiAuditConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AiAuditValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except AiAuditError as exc:
        detail = str(exc)
        if detail.startswith("Stage "):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc


@router.get("/api/documents/{job_id}/ai-audit", response_model=AiAuditReport)
def get_document_ai_audit(job_id: UUID) -> AiAuditReport:
    try:
        return load_ai_audit_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AiAuditValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
