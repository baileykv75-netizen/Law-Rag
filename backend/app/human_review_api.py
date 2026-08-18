from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .human_review import HumanReviewError, load_human_review, record_human_decision
from .human_review_models import HumanDecisionRequest, HumanReviewView


router = APIRouter()


def _http_error(exc: HumanReviewError) -> HTTPException:
    message = str(exc)
    if (
        "required before human review" in message
        or "architecture is conflicted" in message
        or "not valid for an authoritative" in message
        or "Unable to resolve the authoritative audit architecture" in message
    ):
        http_status = status.HTTP_409_CONFLICT
    elif "does not exist in the current" in message:
        http_status = status.HTTP_404_NOT_FOUND
    else:
        http_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=http_status, detail=message)


@router.get("/api/documents/{job_id}/human-review", response_model=HumanReviewView)
def get_human_review(job_id: UUID) -> HumanReviewView:
    try:
        return load_human_review(job_id)
    except HumanReviewError as exc:
        raise _http_error(exc) from exc


@router.post("/api/documents/{job_id}/human-review/decisions", response_model=HumanReviewView)
def post_human_decision(job_id: UUID, request: HumanDecisionRequest) -> HumanReviewView:
    try:
        return record_human_decision(job_id, request)
    except HumanReviewError as exc:
        raise _http_error(exc) from exc
