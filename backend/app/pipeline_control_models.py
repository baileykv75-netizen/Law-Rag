from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

PIPELINE_CONTROL_SCHEMA_VERSION = "1.0.0"


class ProviderExecutionMode(str, Enum):
    AUTO_CONTINUE = "AUTO_CONTINUE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    LOCAL_ONLY = "LOCAL_ONLY"


class PipelineControl(BaseModel):
    schema_version: str = PIPELINE_CONTROL_SCHEMA_VERSION
    job_id: UUID
    provider_mode: ProviderExecutionMode = ProviderExecutionMode.AUTO_CONTINUE
    provider_approved: bool = False
    cancel_requested: bool = False
    cancel_requested_at: datetime | None = None
    active_provider: str | None = None
    active_provider_started_at: datetime | None = None
    updated_at: datetime


class PipelineControlUpdateRequest(BaseModel):
    provider_mode: ProviderExecutionMode


class PipelineControlActionResponse(BaseModel):
    control: PipelineControl
    provider_in_flight: bool = False
    detail: str
