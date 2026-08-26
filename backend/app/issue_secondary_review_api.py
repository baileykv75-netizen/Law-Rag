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
from .pipeline_control import set_provider_mode
from .pipeline_control_models import ProviderExecutionMode
from .issue_review_report import IssueReviewReportError, build_issue_review_report

router = APIRouter()


@router.post("/api/documents/{job_id}/issue-secondary-review", response_model=IssueSecondaryReviewArtifact)
def create_issue_secondary_review(job_id: UUID, request: IssueSecondaryReviewRunRequest) -> IssueSecondaryReviewArtifact:
    try:
        set_provider_mode(job_id, ProviderExecutionMode.AUTO_CONTINUE)
        artifact = run_issue_secondary_review(
            job_id,
            provider_name=request.provider,
            allow_provider_unavailable=True,
            retry_pending=True,
        )
        build_issue_review_report(job_id)
        return artifact
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
    except IssueReviewReportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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
