from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

RUNTIME_HEALTH_SCHEMA_VERSION = "1.0.0"
RUNTIME_HEALTH_INSPECTOR_VERSION = "stage11c-1.0.0"


class RuntimeHealthState(str, Enum):
    OK = "OK"
    OPTIONAL_NOT_CONFIGURED = "OPTIONAL_NOT_CONFIGURED"
    MISSING = "MISSING"
    STALE = "STALE"
    CORRUPT = "CORRUPT"
    MISCONFIGURED = "MISCONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class RuntimeHealthSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class RuntimeHealthCheck(BaseModel):
    check_id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=240)
    state: RuntimeHealthState
    severity: RuntimeHealthSeverity
    required_for_base_app: bool
    detail: str = Field(min_length=1, max_length=2000)
    action: str | None = Field(default=None, max_length=1000)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RuntimeHealthReport(BaseModel):
    schema_version: str = RUNTIME_HEALTH_SCHEMA_VERSION
    inspector_version: str = RUNTIME_HEALTH_INSPECTOR_VERSION
    base_app_ready: bool
    action_required: bool
    checks: list[RuntimeHealthCheck]
    warnings: list[str] = Field(default_factory=list)
