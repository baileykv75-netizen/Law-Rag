from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from .human_review_api import router as human_review_router
from .issue_workspace import IssueWorkspaceError, load_issue_workspace_detail, load_issue_workspace_summary
from .issue_workspace_models import IssueWorkspaceDetail, IssueWorkspaceSummary
from .job_architecture import JobArchitectureError, resolve_job_architecture
from .job_architecture_models import JobAuditArchitecture
from .source_viewer import SourceViewerError, resolve_contract_evidence, source_page_asset
from .source_viewer_models import SourceEvidenceDetail
from .workspace import WorkspaceLoadError, load_workspace_summary
from .workspace_models import WorkspaceSummary


router = APIRouter()
router.include_router(human_review_router)


@router.get(
    "/api/documents/{job_id}/workspace",
    response_model=WorkspaceSummary | IssueWorkspaceSummary,
)
def get_workspace(job_id: UUID) -> WorkspaceSummary | IssueWorkspaceSummary:
    """Read the authoritative local workspace model without executing pipeline/provider work.

    Stage 13G.4 architecture ownership is resolved first. Legacy RC2 jobs keep the
    existing Stage 8/9 workstation response. Issue V1 jobs use the Stage 13B-G
    workspace read model. Mixed/conflicting jobs fail closed instead of guessing.
    """

    try:
        architecture = resolve_job_architecture(job_id)
        if architecture.architecture == JobAuditArchitecture.CONFLICT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job audit architecture is conflicted; workspace will not mix legacy RC2 and Issue V1 artifacts.",
            )
        if architecture.architecture == JobAuditArchitecture.LEGACY_RC2:
            return load_workspace_summary(job_id)
        return load_issue_workspace_summary(job_id)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (WorkspaceLoadError, IssueWorkspaceError, JobArchitectureError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get(
    "/api/documents/{job_id}/workspace/issues/{issue_id}",
    response_model=IssueWorkspaceDetail,
)
def get_workspace_issue(job_id: UUID, issue_id: str) -> IssueWorkspaceDetail:
    """Read one Issue V1 review context only; never calls Planner/DeepSeek/Kimi."""

    try:
        architecture = resolve_job_architecture(job_id)
        if architecture.architecture != JobAuditArchitecture.ISSUE_V1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Issue workspace detail is available only for authoritative ISSUE_V1 jobs."
                    if architecture.architecture == JobAuditArchitecture.LEGACY_RC2
                    else "Job audit architecture is conflicted; issue detail is unavailable."
                ),
            )
        return load_issue_workspace_detail(job_id, issue_id)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (IssueWorkspaceError, JobArchitectureError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/source/pages/{page_number}")
def get_source_page(job_id: UUID, page_number: int) -> FileResponse:
    """Return one bounded source page asset; PDF pages are rendered locally with PDFium."""

    try:
        asset = source_page_asset(job_id, page_number)
        return FileResponse(asset.path, media_type=asset.media_type)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SourceViewerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get(
    "/api/documents/{job_id}/evidence/{evidence_id}",
    response_model=SourceEvidenceDetail,
)
def get_contract_evidence(job_id: UUID, evidence_id: str) -> SourceEvidenceDetail:
    """Resolve one contract Evidence ID back to page/span/bbox metadata."""

    try:
        return resolve_contract_evidence(job_id, evidence_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SourceViewerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
