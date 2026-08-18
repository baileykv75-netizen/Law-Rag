from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .issue_secondary_review import (
    IssueSecondaryReviewError,
    IssueSecondaryReviewStaleError,
    IssueSecondaryReviewValidationError,
    load_issue_secondary_review,
    run_issue_secondary_review,
)
from .issue_secondary_review_models import IssueSecondaryReviewArtifact, IssueSecondaryReviewRunRequest
from .pipeline_control import PipelineCancellationRequested, ProviderBoundaryPaused

router = APIRouter()


@router.post("/api/documents/{job_id}/issue-secondary-review", response_model=IssueSecondaryReviewArtifact)
def create_issue_secondary_review(job_id: UUID, request: IssueSecondaryReviewRunRequest) -> IssueSecondaryReviewArtifact:
    try:
        return run_issue_secondary_review(job_id, provider_name=request.provider)
    except ProviderBoundaryPaused as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "detail": exc.detail}) from exc
    except PipelineCancellationRequested as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "PIPELINE_CANCEL_REQUESTED", "detail": str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssueSecondaryReviewStaleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "ISSUE_SECONDARY_REVIEW_STALE", "detail": str(exc)}) from exc
    except IssueSecondaryReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except IssueSecondaryReviewError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/issue-secondary-review", response_model=IssueSecondaryReviewArtifact)
def get_issue_secondary_review(job_id: UUID) -> IssueSecondaryReviewArtifact:
    try:
        return load_issue_secondary_review(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssueSecondaryReviewStaleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "ISSUE_SECONDARY_REVIEW_STALE", "detail": str(exc)}) from exc
    except IssueSecondaryReviewValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
