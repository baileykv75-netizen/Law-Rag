from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from .ai_audit_models import ProviderHealth
from .review_report import ReviewReport, ReviewReportError, build_review_report, load_review_report
from .secondary_review import (
    SecondaryReviewConfigurationError,
    SecondaryReviewContextError,
    SecondaryReviewError,
    SecondaryReviewValidationError,
    load_secondary_review_report,
    run_secondary_review,
)
from .secondary_review_models import SecondaryReviewReport, SecondaryReviewRunRequest
from .secondary_review_providers import SecondaryReviewProviderError, secondary_provider_from_name

router = APIRouter()


@router.get("/api/ai/secondary/health", response_model=ProviderHealth)
def secondary_provider_health(
    provider: str = Query(default="kimi", description="Stage 9 secondary review provider"),
) -> ProviderHealth:
    try:
        return secondary_provider_from_name(provider).health()
    except SecondaryReviewProviderError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/api/documents/{job_id}/secondary-review", response_model=SecondaryReviewReport)
def run_secondary_review_api(job_id: UUID, request: SecondaryReviewRunRequest) -> SecondaryReviewReport:
    """Make the one explicit Stage 9 contract-level secondary-model call."""

    try:
        return run_secondary_review(job_id, request)
    except SecondaryReviewConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except SecondaryReviewContextError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SecondaryReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except SecondaryReviewError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/secondary-review", response_model=SecondaryReviewReport)
def get_secondary_review_api(job_id: UUID) -> SecondaryReviewReport:
    try:
        return load_secondary_review_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SecondaryReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/api/documents/{job_id}/review-report", response_model=ReviewReport)
def build_review_report_api(job_id: UUID) -> ReviewReport:
    """Run only local deterministic comparison/tool follow-up and persist review-report.json."""

    try:
        return build_review_report(job_id)
    except ReviewReportError as exc:
        message = str(exc)
        http_status = (
            status.HTTP_409_CONFLICT
            if "does not exist" in message or "required" in message
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(status_code=http_status, detail=message) from exc


@router.get("/api/documents/{job_id}/review-report", response_model=ReviewReport)
def get_review_report_api(job_id: UUID) -> ReviewReport:
    try:
        return load_review_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ReviewReportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
