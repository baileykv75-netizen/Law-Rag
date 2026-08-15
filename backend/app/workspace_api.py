from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from .source_viewer import SourceViewerError, resolve_contract_evidence, source_page_asset
from .source_viewer_models import SourceEvidenceDetail
from .workspace import WorkspaceLoadError, load_workspace_summary
from .workspace_models import WorkspaceSummary


router = APIRouter()


@router.get("/api/documents/{job_id}/workspace", response_model=WorkspaceSummary)
def get_workspace(job_id: UUID) -> WorkspaceSummary:
    """Read a compact local Stage 2-9 job summary without executing pipeline work."""

    try:
        return load_workspace_summary(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkspaceLoadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/source/pages/{page_number}")
def get_source_page(job_id: UUID, page_number: int) -> FileResponse:
    """Return one bounded source page asset; PDF pages are rendered locally with PDFium."""

    try:
        asset = source_page_asset(job_id, page_number)
        return FileResponse(asset.path, media_type=asset.media_type, filename=asset.path.name)
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
