from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from .ai_audit_models import ProviderUsage

RESOURCE_BUDGET_SCHEMA_VERSION = "1.0.0"
RESOURCE_BUDGET_ENGINE_VERSION = "stage18.3-1.0.0"


class ResourceBudgetState(str, Enum):
    UNLIMITED = "UNLIMITED"
    WITHIN_BUDGET = "WITHIN_BUDGET"
    EXHAUSTED = "EXHAUSTED"
    USAGE_UNKNOWN_BLOCKED = "USAGE_UNKNOWN_BLOCKED"
    COST_UNKNOWN_BLOCKED = "COST_UNKNOWN_BLOCKED"


class ProviderCallLedgerState(str, Enum):
    STARTED = "STARTED"
    RETURNED_PENDING_RECONCILIATION = "RETURNED_PENDING_RECONCILIATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProviderCallLedgerSource(str, Enum):
    LIVE = "LIVE"
    IMPORTED_CHECKPOINT = "IMPORTED_CHECKPOINT"


class ProviderPrice(BaseModel):
    prompt_per_million: float = Field(ge=0)
    completion_per_million: float = Field(ge=0)


class ResourceBudgetPolicy(BaseModel):
    max_provider_calls: int | None = Field(default=None, ge=1, le=1024)
    max_total_tokens: int | None = Field(default=None, ge=1, le=1_000_000_000)
    max_estimated_cost: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=12)
    provider_prices: dict[str, ProviderPrice] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cost_policy(self) -> "ResourceBudgetPolicy":
        normalized: dict[str, ProviderPrice] = {}
        for provider, price in self.provider_prices.items():
            key = provider.strip().lower()
            if not key or len(key) > 64:
                raise ValueError("Provider pricing keys must be non-empty names up to 64 characters.")
            if key in normalized:
                raise ValueError("Provider pricing keys must be unique after normalization.")
            normalized[key] = price
        self.provider_prices = normalized
        if self.max_estimated_cost is not None:
            if not self.currency or not self.currency.strip():
                raise ValueError("A currency is required when max_estimated_cost is configured.")
            if not self.provider_prices:
                raise ValueError("User-configured provider_prices are required when max_estimated_cost is configured.")
        if self.currency is not None:
            self.currency = self.currency.strip().upper()
        return self

    @property
    def limited(self) -> bool:
        return any(
            value is not None
            for value in (self.max_provider_calls, self.max_total_tokens, self.max_estimated_cost)
        )


class ProviderCallLedgerRecord(BaseModel):
    call_id: UUID
    provider: str
    stage: str
    issue_id: str | None = None
    state: ProviderCallLedgerState
    source: ProviderCallLedgerSource
    started_at: datetime
    finished_at: datetime | None = None
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    error_type: str | None = Field(default=None, max_length=160)
    checkpoint_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_checkpoint_reference(cls, data):
        """Canonicalize only imported historical checkpoint references.

        Production/live ledger writes still require a real 64-character lowercase
        hexadecimal SHA-256 fingerprint. Older Stage 13 test/legacy artifacts may
        carry opaque raw_response_hash identifiers such as ``hash-issue-1``. When
        those already-validated audit checkpoints are imported for accounting, the
        opaque identifier is deterministically SHA-256 hashed so the Stage 18 ledger
        keeps one canonical fingerprint format without mutating the source artifact.
        """

        if not isinstance(data, dict):
            return data
        value = data.get("checkpoint_fingerprint")
        source = data.get("source")
        source_value = source.value if isinstance(source, ProviderCallLedgerSource) else source
        if value is None or source_value != ProviderCallLedgerSource.IMPORTED_CHECKPOINT.value:
            return data
        text = str(value)
        canonical = len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)
        if canonical:
            return data
        normalized = dict(data)
        normalized["checkpoint_fingerprint"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return normalized


class ResourceBudgetArtifact(BaseModel):
    schema_version: str = RESOURCE_BUDGET_SCHEMA_VERSION
    engine_version: str = RESOURCE_BUDGET_ENGINE_VERSION
    job_id: UUID
    policy: ResourceBudgetPolicy = Field(default_factory=ResourceBudgetPolicy)
    calls: list[ProviderCallLedgerRecord] = Field(default_factory=list)
    updated_at: datetime
    artifact_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_unique_calls(self) -> "ResourceBudgetArtifact":
        ids = [item.call_id for item in self.calls]
        if len(ids) != len(set(ids)):
            raise ValueError("Resource budget ledger contains duplicate call IDs.")
        return self


class ResourceBudgetOverview(BaseModel):
    schema_version: str = RESOURCE_BUDGET_SCHEMA_VERSION
    job_id: UUID
    state: ResourceBudgetState
    policy: ResourceBudgetPolicy
    provider_calls_used: int = Field(ge=0)
    completed_calls: int = Field(ge=0)
    failed_calls: int = Field(ge=0)
    in_flight_calls: int = Field(ge=0)
    returned_pending_calls: int = Field(ge=0)
    prompt_tokens_known: int = Field(ge=0)
    completion_tokens_known: int = Field(ge=0)
    total_tokens_known: int = Field(ge=0)
    unknown_usage_calls: int = Field(ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    estimated_cost_unknown_calls: int = Field(default=0, ge=0)
    currency: str | None = None
    call_budget_remaining: int | None = Field(default=None, ge=0)
    token_budget_remaining: int | None = Field(default=None, ge=0)
    estimated_cost_remaining: float | None = Field(default=None, ge=0)
    token_budget_semantics: str = "CONTINUATION_LIMIT_AFTER_REPORTED_USAGE"
    cost_budget_semantics: str = "CONTINUATION_LIMIT_AFTER_USER_CONFIGURED_ESTIMATE"
    warnings: list[str] = Field(default_factory=list)


class ResourceBudgetUpdateRequest(BaseModel):
    policy: ResourceBudgetPolicy


class ResourceBudgetCallReservation(BaseModel):
    call_id: UUID
    job_id: UUID
    provider: str
    stage: str
    issue_id: str | None = None
