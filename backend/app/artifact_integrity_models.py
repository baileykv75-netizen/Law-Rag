from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

ARTIFACT_INTEGRITY_SCHEMA_VERSION = "1.0.0"
ARTIFACT_INTEGRITY_INSPECTOR_VERSION = "stage11c-1.0.0"


class ArtifactIntegrityState(str, Enum):
    READY = "READY"
    MISSING = "MISSING"
    CORRUPT = "CORRUPT"
    MISMATCH = "MISMATCH"
    STALE = "STALE"


class ArtifactIntegrityCheck(BaseModel):
    artifact: str
    state: ArtifactIntegrityState
    detail: str
    action: str | None = None


class ArtifactLinkCheck(BaseModel):
    link_id: str
    state: ArtifactIntegrityState
    detail: str
    artifacts: list[str] = Field(default_factory=list)
    action: str | None = None


class JobArtifactIntegrityReport(BaseModel):
    schema_version: str = ARTIFACT_INTEGRITY_SCHEMA_VERSION
    inspector_version: str = ARTIFACT_INTEGRITY_INSPECTOR_VERSION
    job_id: UUID
    source_available: bool
    all_present_artifacts_valid: bool
    action_required: bool
    artifacts: list[ArtifactIntegrityCheck]
    links: list[ArtifactLinkCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
