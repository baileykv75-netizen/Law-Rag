from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import ValidationError

from .ai_audit_models import ProviderUsage
from .issue_primary_audit_models import IssuePrimaryAuditArtifact
from .issue_secondary_review_models import IssueSecondaryReviewArtifact
from .resource_budget_models import (
    ProviderCallLedgerRecord,
    ProviderCallLedgerSource,
    ProviderCallLedgerState,
    ResourceBudgetArtifact,
    ResourceBudgetCallReservation,
    ResourceBudgetOverview,
    ResourceBudgetPolicy,
    ResourceBudgetState,
)
from .safe_persistence import atomic_write_text
from .storage import (
    job_issue_primary_audit_path,
    job_issue_secondary_review_path,
    runtime_dir,
)


class ResourceBudgetError(RuntimeError):
    pass


class ResourceBudgetExceeded(ResourceBudgetError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lock_for(job_id: UUID) -> threading.RLock:
    key = str(job_id)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


def resource_budget_path(job_id: UUID) -> Path:
    return runtime_dir() / "jobs" / str(job_id) / "resource-budget.json"


def _job_dir(job_id: UUID) -> Path:
    path = runtime_dir() / "jobs" / str(job_id)
    if not path.is_dir():
        raise FileNotFoundError(f"No local Law-Rag job exists for {job_id}.")
    if path.is_symlink():
        raise ResourceBudgetError("Job runtime directory must not be a symlink.")
    return path


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _new_artifact(job_id: UUID) -> ResourceBudgetArtifact:
    payload = {
        "schema_version": "1.0.0",
        "engine_version": "stage18.3-1.0.0",
        "job_id": str(job_id),
        "policy": ResourceBudgetPolicy().model_dump(mode="json"),
        "calls": [],
        "updated_at": _now().isoformat(),
    }
    return ResourceBudgetArtifact(**payload, artifact_fingerprint=_fingerprint(payload))


def _read(job_id: UUID) -> ResourceBudgetArtifact:
    _job_dir(job_id)
    path = resource_budget_path(job_id)
    if path.is_symlink():
        raise ResourceBudgetError("resource-budget.json must not be a symlink.")
    if not path.exists():
        return _new_artifact(job_id)
    try:
        artifact = ResourceBudgetArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ResourceBudgetError("Persisted resource-budget.json is invalid.") from exc
    if artifact.job_id != job_id:
        raise ResourceBudgetError("Persisted resource budget belongs to another job.")
    payload = artifact.model_dump(mode="json", exclude={"artifact_fingerprint"})
    if artifact.artifact_fingerprint != _fingerprint(payload):
        raise ResourceBudgetError("Persisted resource-budget.json fingerprint is invalid.")
    return artifact


def _persist(artifact: ResourceBudgetArtifact) -> ResourceBudgetArtifact:
    path = resource_budget_path(artifact.job_id)
    if path.is_symlink():
        raise ResourceBudgetError("resource-budget.json must not be a symlink.")
    artifact.updated_at = _now()
    payload = artifact.model_dump(mode="json", exclude={"artifact_fingerprint"})
    artifact.artifact_fingerprint = _fingerprint(payload)
    atomic_write_text(path, artifact.model_dump_json(indent=2))
    return artifact


def _normalized_usage(usage: ProviderUsage) -> ProviderUsage:
    prompt = usage.prompt_tokens
    completion = usage.completion_tokens
    total = usage.total_tokens
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return ProviderUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


def _checkpoint_time(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _imported_call_id(job_id: UUID, stage: str, issue_id: str, raw_response_hash: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"law-rag:{job_id}:{stage}:{issue_id}:{raw_response_hash}")


def _checkpoint_records(job_id: UUID) -> list[ProviderCallLedgerRecord]:
    records: list[ProviderCallLedgerRecord] = []
    sources = (
        ("PRIMARY", job_issue_primary_audit_path(job_id), IssuePrimaryAuditArtifact),
        ("SECONDARY", job_issue_secondary_review_path(job_id), IssueSecondaryReviewArtifact),
    )
    for stage, path, model in sources:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            artifact = model.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            # Budget accounting never repairs or trusts malformed audit artifacts.
            # Their normal artifact readers remain responsible for surfacing the
            # underlying integrity failure.
            continue
        if artifact.job_id != job_id:
            continue
        stamp = _checkpoint_time(path)
        for call in artifact.provider_calls:
            records.append(
                ProviderCallLedgerRecord(
                    call_id=_imported_call_id(job_id, stage, call.issue_id, call.raw_response_hash),
                    provider=call.provider.strip().lower(),
                    stage=stage,
                    issue_id=call.issue_id,
                    state=ProviderCallLedgerState.COMPLETED,
                    source=ProviderCallLedgerSource.IMPORTED_CHECKPOINT,
                    started_at=stamp,
                    finished_at=stamp,
                    usage=_normalized_usage(call.usage),
                    checkpoint_fingerprint=call.raw_response_hash,
                )
            )
    return records


def _reconcile_checkpoints(artifact: ResourceBudgetArtifact) -> bool:
    changed = False
    known_fingerprints = {
        item.checkpoint_fingerprint
        for item in artifact.calls
        if item.checkpoint_fingerprint is not None
    }
    known_import_ids = {item.call_id for item in artifact.calls}
    for imported in _checkpoint_records(artifact.job_id):
        if imported.checkpoint_fingerprint in known_fingerprints or imported.call_id in known_import_ids:
            continue
        artifact.calls.append(imported)
        known_fingerprints.add(imported.checkpoint_fingerprint)
        known_import_ids.add(imported.call_id)
        changed = True
    return changed


def _usage_totals(calls: list[ProviderCallLedgerRecord]) -> tuple[int, int, int, int]:
    prompt = 0
    completion = 0
    total = 0
    unknown = 0
    for call in calls:
        if call.state == ProviderCallLedgerState.STARTED:
            unknown += 1
            continue
        usage = _normalized_usage(call.usage)
        if usage.prompt_tokens is not None:
            prompt += usage.prompt_tokens
        if usage.completion_tokens is not None:
            completion += usage.completion_tokens
        if usage.total_tokens is None:
            unknown += 1
        else:
            total += usage.total_tokens
    return prompt, completion, total, unknown


def _cost_totals(calls: list[ProviderCallLedgerRecord], policy: ResourceBudgetPolicy) -> tuple[float | None, int]:
    if not policy.provider_prices:
        return None, 0
    total_cost = 0.0
    unknown = 0
    for call in calls:
        if call.state == ProviderCallLedgerState.STARTED:
            unknown += 1
            continue
        price = policy.provider_prices.get(call.provider.strip().lower())
        usage = _normalized_usage(call.usage)
        if price is None or usage.prompt_tokens is None or usage.completion_tokens is None:
            unknown += 1
            continue
        total_cost += (
            (usage.prompt_tokens / 1_000_000.0) * price.prompt_per_million
            + (usage.completion_tokens / 1_000_000.0) * price.completion_per_million
        )
    return round(total_cost, 8), unknown


def _overview(artifact: ResourceBudgetArtifact) -> ResourceBudgetOverview:
    calls = list(artifact.calls)
    used = len(calls)
    completed = sum(item.state == ProviderCallLedgerState.COMPLETED for item in calls)
    failed = sum(item.state == ProviderCallLedgerState.FAILED for item in calls)
    in_flight = sum(item.state == ProviderCallLedgerState.STARTED for item in calls)
    prompt, completion, total_tokens, unknown_usage = _usage_totals(calls)
    estimated_cost, unknown_cost = _cost_totals(calls, artifact.policy)
    policy = artifact.policy
    warnings: list[str] = []

    call_remaining = None
    if policy.max_provider_calls is not None:
        call_remaining = max(0, policy.max_provider_calls - used)
    token_remaining = None
    if policy.max_total_tokens is not None:
        token_remaining = max(0, policy.max_total_tokens - total_tokens)
    cost_remaining = None
    if policy.max_estimated_cost is not None and estimated_cost is not None:
        cost_remaining = max(0.0, round(policy.max_estimated_cost - estimated_cost, 8))

    if not policy.limited:
        state = ResourceBudgetState.UNLIMITED
    elif policy.max_provider_calls is not None and used >= policy.max_provider_calls:
        state = ResourceBudgetState.EXHAUSTED
    elif policy.max_total_tokens is not None and unknown_usage:
        state = ResourceBudgetState.USAGE_UNKNOWN_BLOCKED
    elif policy.max_total_tokens is not None and total_tokens >= policy.max_total_tokens:
        state = ResourceBudgetState.EXHAUSTED
    elif policy.max_estimated_cost is not None and unknown_cost:
        state = ResourceBudgetState.COST_UNKNOWN_BLOCKED
    elif (
        policy.max_estimated_cost is not None
        and estimated_cost is not None
        and estimated_cost >= policy.max_estimated_cost
    ):
        state = ResourceBudgetState.EXHAUSTED
    else:
        state = ResourceBudgetState.WITHIN_BUDGET

    if policy.max_total_tokens is not None:
        warnings.append(
            "Token budget is a continuation limit based on provider-reported usage. A single in-flight request can report usage above the remaining threshold; Law-Rag then blocks every subsequent provider call."
        )
    if policy.max_estimated_cost is not None:
        warnings.append(
            "Estimated cost uses only the user's configured price table and provider-reported prompt/completion tokens. It is not a provider invoice or live vendor price."
        )
    if unknown_usage:
        warnings.append(
            f"{unknown_usage} provider call(s) have unknown total-token usage; token-limited continuation is blocked rather than counting unknown usage as zero."
        )
    if unknown_cost and policy.max_estimated_cost is not None:
        warnings.append(
            f"{unknown_cost} provider call(s) cannot be priced from the configured table/usage; cost-limited continuation is blocked."
        )

    return ResourceBudgetOverview(
        job_id=artifact.job_id,
        state=state,
        policy=policy,
        provider_calls_used=used,
        completed_calls=completed,
        failed_calls=failed,
        in_flight_calls=in_flight,
        prompt_tokens_known=prompt,
        completion_tokens_known=completion,
        total_tokens_known=total_tokens,
        unknown_usage_calls=unknown_usage,
        estimated_cost=estimated_cost,
        estimated_cost_unknown_calls=unknown_cost,
        currency=policy.currency,
        call_budget_remaining=call_remaining,
        token_budget_remaining=token_remaining,
        estimated_cost_remaining=cost_remaining,
        warnings=warnings,
    )


def resource_budget_overview(job_id: UUID) -> ResourceBudgetOverview:
    with _lock_for(job_id):
        artifact = _read(job_id)
        if _reconcile_checkpoints(artifact):
            artifact = _persist(artifact)
        return _overview(artifact)


def set_resource_budget_policy(job_id: UUID, policy: ResourceBudgetPolicy) -> ResourceBudgetOverview:
    with _lock_for(job_id):
        artifact = _read(job_id)
        _reconcile_checkpoints(artifact)
        artifact.policy = policy
        artifact = _persist(artifact)
        return _overview(artifact)


def _raise_for_overview(overview: ResourceBudgetOverview, *, provider: str) -> None:
    policy = overview.policy
    normalized_provider = provider.strip().lower()
    if policy.max_estimated_cost is not None and normalized_provider not in policy.provider_prices:
        raise ResourceBudgetExceeded(
            "RESOURCE_COST_PRICE_UNKNOWN",
            f"Provider {normalized_provider} has no user-configured price entry, so the configured estimated-cost limit cannot be enforced truthfully.",
        )
    if overview.state == ResourceBudgetState.EXHAUSTED:
        raise ResourceBudgetExceeded(
            "RESOURCE_BUDGET_EXHAUSTED",
            "The configured provider call/token/estimated-cost continuation limit has been reached. No new external provider request was sent.",
        )
    if overview.state == ResourceBudgetState.USAGE_UNKNOWN_BLOCKED:
        raise ResourceBudgetExceeded(
            "RESOURCE_TOKEN_USAGE_UNKNOWN",
            "A previous provider call has unknown token usage. Because a token budget is configured, Law-Rag will not treat unknown usage as zero or start another provider request.",
        )
    if overview.state == ResourceBudgetState.COST_UNKNOWN_BLOCKED:
        raise ResourceBudgetExceeded(
            "RESOURCE_COST_USAGE_UNKNOWN",
            "A previous provider call cannot be priced from provider-reported usage and the user-configured price table. Another request was not started.",
        )


def assert_provider_budget_allows(job_id: UUID, provider: str) -> ResourceBudgetOverview:
    with _lock_for(job_id):
        artifact = _read(job_id)
        if _reconcile_checkpoints(artifact):
            artifact = _persist(artifact)
        overview = _overview(artifact)
        _raise_for_overview(overview, provider=provider)
        return overview


def reserve_provider_call(
    job_id: UUID,
    *,
    provider: str,
    stage: str,
    issue_id: str | None,
) -> ResourceBudgetCallReservation:
    with _lock_for(job_id):
        artifact = _read(job_id)
        _reconcile_checkpoints(artifact)
        overview = _overview(artifact)
        _raise_for_overview(overview, provider=provider)
        call_id = uuid4()
        record = ProviderCallLedgerRecord(
            call_id=call_id,
            provider=provider.strip().lower(),
            stage=stage,
            issue_id=issue_id,
            state=ProviderCallLedgerState.STARTED,
            source=ProviderCallLedgerSource.LIVE,
            started_at=_now(),
        )
        artifact.calls.append(record)
        _persist(artifact)
        return ResourceBudgetCallReservation(
            call_id=call_id,
            job_id=job_id,
            provider=record.provider,
            stage=stage,
            issue_id=issue_id,
        )


def complete_provider_call(
    reservation: ResourceBudgetCallReservation,
    *,
    usage: ProviderUsage,
    raw_response_hash: str | None = None,
) -> ResourceBudgetOverview:
    with _lock_for(reservation.job_id):
        artifact = _read(reservation.job_id)
        record = next((item for item in artifact.calls if item.call_id == reservation.call_id), None)
        if record is None:
            raise ResourceBudgetError("Provider budget reservation does not exist.")
        if record.state != ProviderCallLedgerState.STARTED:
            raise ResourceBudgetError("Provider budget reservation is already terminal.")
        record.state = ProviderCallLedgerState.COMPLETED
        record.finished_at = _now()
        record.usage = _normalized_usage(usage)
        if raw_response_hash is not None:
            if len(raw_response_hash) != 64 or any(ch not in "0123456789abcdef" for ch in raw_response_hash):
                raise ResourceBudgetError("Provider raw-response fingerprint is invalid.")
            record.checkpoint_fingerprint = raw_response_hash
        artifact = _persist(artifact)
        return _overview(artifact)


def fail_provider_call(
    reservation: ResourceBudgetCallReservation,
    *,
    error_type: str,
) -> ResourceBudgetOverview:
    with _lock_for(reservation.job_id):
        artifact = _read(reservation.job_id)
        record = next((item for item in artifact.calls if item.call_id == reservation.call_id), None)
        if record is None:
            raise ResourceBudgetError("Provider budget reservation does not exist.")
        if record.state == ProviderCallLedgerState.STARTED:
            record.state = ProviderCallLedgerState.FAILED
            record.finished_at = _now()
            record.error_type = error_type[:160]
            artifact = _persist(artifact)
        return _overview(artifact)
