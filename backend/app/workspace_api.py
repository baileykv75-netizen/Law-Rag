from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

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
