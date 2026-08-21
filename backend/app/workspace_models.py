from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


WORKSPACE_SCHEMA_VERSION = "1.1.0"


class WorkspaceArtifactState(str, Enum):
    READY = "READY"
    MISSING = "MISSING"
    NOT_REQUIRED = "NOT_REQUIRED"
    INVALID = "INVALID"


class WorkspaceOverallState(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    INVALID = "INVALID"


class WorkspaceStageSummary(BaseModel):
    stage: str
    label: str
    state: WorkspaceArtifactState
    artifact: str | None = None
    detail: str


class WorkspaceDocumentSummary(BaseModel):
    filename: str
    media_type: str
    document_kind: str
    page_count: int = Field(ge=1)
    route: str
    native_text_pages: int = Field(ge=0)
    ocr_required_pages: int = Field(ge=0)
    ocr_used: bool = False
    low_confidence_ocr_pages: int = Field(default=0, ge=0)
    failed_ocr_pages: int = Field(default=0, ge=0)
    no_text_ocr_pages: int = Field(default=0, ge=0)


class WorkspaceReviewSummary(BaseModel):
    primary_available: bool = False
    primary_provider: str | None = None
    primary_model: str | None = None
    primary_finding_count: int = Field(default=0, ge=0)
    secondary_available: bool = False
    secondary_provider: str | None = None
    secondary_model: str | None = None
    secondary_review_count: int = Field(default=0, ge=0)
    possible_omission_count: int = Field(default=0, ge=0)
    comparison_available: bool = False
    final_review_state: str | None = None
    agent_action_count: int = Field(default=0, ge=0)


class WorkspaceSummary(BaseModel):
    schema_version: str = WORKSPACE_SCHEMA_VERSION
    job_id: UUID
    architecture: Literal["LEGACY_RC2"] = "LEGACY_RC2"
    overall_state: WorkspaceOverallState
    source_available: bool
    document: WorkspaceDocumentSummary | None = None
    stages: list[WorkspaceStageSummary]
    review: WorkspaceReviewSummary
    source_uncertainty: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
