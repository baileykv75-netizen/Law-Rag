from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from .issue_legal_context import (
    IssueLegalContextError,
    IssueLegalContextStaleError,
    build_issue_legal_context,
    load_issue_legal_context,
)
from .issue_legal_context_models import IssueLegalContextArtifact, IssueLegalContextRunRequest
from .legal.retrieval import RetrievalIndexError
from .legal.store import LegalStoreError

router = APIRouter()


@router.post("/api/documents/{job_id}/issue-legal-context", response_model=IssueLegalContextArtifact)
def create_issue_legal_context(job_id: UUID, request: IssueLegalContextRunRequest) -> IssueLegalContextArtifact:
    """Build Stage 13D issue-based Legal RAG from the persisted Audit Plan.

    This step is local-only. It does not call DeepSeek, Kimi, or any external model provider.
    """

    try:
        return build_issue_legal_context(
            job_id,
            as_of=request.as_of,
            use_semantic=request.use_semantic,
            top_k_per_query=request.top_k_per_query,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (IssueLegalContextError, LegalStoreError, RetrievalIndexError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/api/documents/{job_id}/issue-legal-context", response_model=IssueLegalContextArtifact)
def get_issue_legal_context(job_id: UUID) -> IssueLegalContextArtifact:
    """Read the persisted Stage 13D artifact and verify local freshness; never runs retrieval."""

    try:
        return load_issue_legal_context(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IssueLegalContextStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ISSUE_LEGAL_CONTEXT_STALE", "detail": str(exc)},
        ) from exc
    except (IssueLegalContextError, LegalStoreError, RetrievalIndexError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
