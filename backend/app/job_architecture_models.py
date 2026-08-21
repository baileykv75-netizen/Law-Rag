from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .pipeline_control_models import ProviderExecutionMode

JOB_ARCHITECTURE_SCHEMA_VERSION = "1.0.0"
JOB_ARCHITECTURE_ENGINE_VERSION = "stage13g-4-1.0.0"


class JobAuditArchitecture(str, Enum):
    ISSUE_V1 = "ISSUE_V1"
    LEGACY_RC2 = "LEGACY_RC2"
    CONFLICT = "CONFLICT"


class JobArchitectureSource(str, Enum):
    MIGRATION_RECORD = "MIGRATION_RECORD"
    PIPELINE = "PIPELINE"
    ARTIFACTS = "ARTIFACTS"
    CURRENT_DEFAULT = "CURRENT_DEFAULT"


class JobArchitectureSummary(BaseModel):
    schema_version: str = JOB_ARCHITECTURE_SCHEMA_VERSION
    engine_version: str = JOB_ARCHITECTURE_ENGINE_VERSION
    job_id: UUID
    architecture: JobAuditArchitecture
    source: JobArchitectureSource
    pipeline_architecture: JobAuditArchitecture | None = None
    legacy_artifacts: list[str] = Field(default_factory=list)
    issue_artifacts: list[str] = Field(default_factory=list)
    migrated_from_legacy: bool = False
    legacy_pipeline_snapshot: str | None = None
    migration_available: bool = False
    warnings: list[str] = Field(default_factory=list)


class LegacyPipelineMigrationRecord(BaseModel):
    schema_version: str = JOB_ARCHITECTURE_SCHEMA_VERSION
    engine_version: str = JOB_ARCHITECTURE_ENGINE_VERSION
    job_id: UUID
    authoritative_architecture: Literal[JobAuditArchitecture.ISSUE_V1] = JobAuditArchitecture.ISSUE_V1
    migrated_from: Literal[JobAuditArchitecture.LEGACY_RC2] = JobAuditArchitecture.LEGACY_RC2
    migrated_at: datetime
    legacy_pipeline_snapshot: str
    legacy_pipeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    legacy_pipeline_engine_version: str
    legacy_pipeline_status: str


class LegacyPipelineMigrationRequest(BaseModel):
    """Explicitly choose provider policy for a legacy -> Issue V1 migration.

    REQUIRE_APPROVAL is intentionally the safe default: migrating old local state
    must never imply consent to send contract evidence to a cloud provider.
    """

    provider_mode: ProviderExecutionMode = ProviderExecutionMode.REQUIRE_APPROVAL
