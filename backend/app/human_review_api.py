from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .human_review import HumanReviewError, load_human_review, record_human_decision
from .human_review_models import HumanDecisionRequest, HumanReviewView


router = APIRouter()


@router.get("/api/documents/{job_id}/human-review", response_model=HumanReviewView)
def get_human_review(job_id: UUID) -> HumanReviewView:
    try:
        return load_human_review(job_id)
    except HumanReviewError as exc:
        message = str(exc)
        http_status = status.HTTP_409_CONFLICT if "review-report.json is required" in message else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=http_status, detail=message) from exc


@router.post("/api/documents/{job_id}/human-review/decisions", response_model=HumanReviewView)
def post_human_decision(job_id: UUID, request: HumanDecisionRequest) -> HumanReviewView:
    try:
        return record_human_decision(job_id, request)
    except HumanReviewError as exc:
        message = str(exc)
        if "review-report.json is required" in message:
            http_status = status.HTTP_409_CONFLICT
        elif "does not exist in the current review report" in message:
            http_status = status.HTTP_404_NOT_FOUND
        else:
            http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=http_status, detail=message) from exc
