from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .issue_review_report import (
    IssueReviewReportError,
    IssueReviewReportPrerequisiteError,
    IssueReviewReportStaleError,
    IssueReviewReportValidationError,
    build_issue_review_report,
    load_issue_review_report,
)
from .issue_review_report_models import IssueReviewReport

router = APIRouter()


@router.post(
    "/api/documents/{job_id}/issue-review-report",
    response_model=IssueReviewReport,
)
def create_issue_review_report(job_id: UUID) -> IssueReviewReport:
    try:
        return build_issue_review_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssueReviewReportPrerequisiteError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ISSUE_REVIEW_REPORT_PREREQUISITE", "detail": str(exc)},
        ) from exc
    except IssueReviewReportStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ISSUE_REVIEW_REPORT_STALE", "detail": str(exc)},
        ) from exc
    except IssueReviewReportValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except IssueReviewReportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/api/documents/{job_id}/issue-review-report",
    response_model=IssueReviewReport,
)
def get_issue_review_report(job_id: UUID) -> IssueReviewReport:
    try:
        return load_issue_review_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssueReviewReportStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ISSUE_REVIEW_REPORT_STALE", "detail": str(exc)},
        ) from exc
    except IssueReviewReportValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
