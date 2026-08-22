from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.resource_budget as resource_budget
from app.ai_audit_models import ProviderUsage
from app.main import app
from app.pipeline_control import (
    ProviderBoundaryPaused,
    begin_provider_call,
    finish_provider_call,
    set_provider_mode,
)
from app.pipeline_control_models import ProviderExecutionMode
from app.resource_budget import (
    complete_provider_call,
    reserve_provider_call,
    resource_budget_overview,
    set_resource_budget_policy,
)
from app.resource_budget_models import (
    ProviderCallLedgerRecord,
    ProviderCallLedgerSource,
    ProviderCallLedgerState,
    ProviderPrice,
    ResourceBudgetPolicy,
    ResourceBudgetState,
)


def _job(tmp_path: Path, monkeypatch) -> UUID:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    (tmp_path / "jobs" / str(job_id)).mkdir(parents=True)
    return job_id


def _checkpoint_record(job_id: UUID, *, provider: str = "deepseek") -> ProviderCallLedgerRecord:
    del job_id
    stamp = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    return ProviderCallLedgerRecord(
        call_id=uuid4(),
        provider=provider,
        stage="PRIMARY" if provider == "deepseek" else "SECONDARY",
        issue_id="ISSUE-1",
        state=ProviderCallLedgerState.COMPLETED,
        source=ProviderCallLedgerSource.IMPORTED_CHECKPOINT,
        started_at=stamp,
        finished_at=stamp,
        usage=ProviderUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        checkpoint_fingerprint="a" * 64,
    )


def test_default_budget_is_unlimited_and_non_mutating(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)

    overview = resource_budget_overview(job_id)

    assert overview.state == ResourceBudgetState.UNLIMITED
    assert overview.provider_calls_used == 0
    assert overview.unknown_usage_calls == 0
    assert not (tmp_path / "jobs" / str(job_id) / "resource-budget.json").exists()


def test_call_budget_is_hard_boundary_at_provider_entry(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(job_id, ResourceBudgetPolicy(max_provider_calls=1))

    begin_provider_call(job_id, "deepseek")
    finish_provider_call(job_id, "deepseek")

    with pytest.raises(ProviderBoundaryPaused) as exc_info:
        begin_provider_call(job_id, "kimi")

    assert exc_info.value.code == "RESOURCE_BUDGET_EXHAUSTED"
    overview = resource_budget_overview(job_id)
    assert overview.provider_calls_used == 1
    assert overview.call_budget_remaining == 0


def test_local_only_rejection_consumes_no_budget(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(job_id, ResourceBudgetPolicy(max_provider_calls=1))
    set_provider_mode(job_id, ProviderExecutionMode.LOCAL_ONLY)

    with pytest.raises(ProviderBoundaryPaused) as exc_info:
        begin_provider_call(job_id, "deepseek")

    assert exc_info.value.code == "LOCAL_ONLY_PROVIDER_DISABLED"
    assert resource_budget_overview(job_id).provider_calls_used == 0


def test_unapproved_provider_rejection_consumes_no_budget(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(job_id, ResourceBudgetPolicy(max_provider_calls=1))
    set_provider_mode(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)

    with pytest.raises(ProviderBoundaryPaused) as exc_info:
        begin_provider_call(job_id, "deepseek")

    assert exc_info.value.code == "PROVIDER_APPROVAL_REQUIRED"
    assert resource_budget_overview(job_id).provider_calls_used == 0


def test_unknown_usage_blocks_token_limited_continuation(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(job_id, ResourceBudgetPolicy(max_total_tokens=100))

    begin_provider_call(job_id, "deepseek")
    finish_provider_call(job_id, "deepseek")
    overview = resource_budget_overview(job_id)
    assert overview.state == ResourceBudgetState.USAGE_UNKNOWN_BLOCKED
    assert overview.returned_pending_calls == 1
    assert overview.unknown_usage_calls == 1

    with pytest.raises(ProviderBoundaryPaused) as exc_info:
        begin_provider_call(job_id, "deepseek")
    assert exc_info.value.code == "RESOURCE_TOKEN_USAGE_UNKNOWN"
    assert resource_budget_overview(job_id).provider_calls_used == 1


def test_checkpoint_reconciliation_fills_live_usage_without_double_counting(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(job_id, ResourceBudgetPolicy(max_total_tokens=100))
    begin_provider_call(job_id, "deepseek")
    finish_provider_call(job_id, "deepseek")

    imported = _checkpoint_record(job_id)
    monkeypatch.setattr(resource_budget, "_checkpoint_records", lambda _: [imported])
    overview = resource_budget_overview(job_id)

    assert overview.provider_calls_used == 1
    assert overview.completed_calls == 1
    assert overview.returned_pending_calls == 0
    assert overview.unknown_usage_calls == 0
    assert overview.total_tokens_known == 30
    assert overview.token_budget_remaining == 70
    assert overview.state == ResourceBudgetState.WITHIN_BUDGET

    # Re-reading the exact same checkpoint remains idempotent.
    second = resource_budget_overview(job_id)
    assert second.provider_calls_used == 1
    assert second.total_tokens_known == 30


def test_historical_checkpoint_is_imported_once(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    imported = _checkpoint_record(job_id)
    monkeypatch.setattr(resource_budget, "_checkpoint_records", lambda _: [imported])

    first = resource_budget_overview(job_id)
    second = resource_budget_overview(job_id)

    assert first.provider_calls_used == 1
    assert second.provider_calls_used == 1
    assert second.total_tokens_known == 30


def test_legacy_imported_checkpoint_reference_is_canonicalized() -> None:
    stamp = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    opaque = "hash-issue-1"

    record = ProviderCallLedgerRecord(
        call_id=uuid4(),
        provider="deepseek",
        stage="PRIMARY",
        issue_id="ISSUE-1",
        state=ProviderCallLedgerState.COMPLETED,
        source=ProviderCallLedgerSource.IMPORTED_CHECKPOINT,
        started_at=stamp,
        finished_at=stamp,
        checkpoint_fingerprint=opaque,
    )

    assert record.checkpoint_fingerprint == hashlib.sha256(opaque.encode("utf-8")).hexdigest()


def test_live_checkpoint_reference_remains_strict_sha256() -> None:
    stamp = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        ProviderCallLedgerRecord(
            call_id=uuid4(),
            provider="deepseek",
            stage="PRIMARY",
            issue_id="ISSUE-1",
            state=ProviderCallLedgerState.COMPLETED,
            source=ProviderCallLedgerSource.LIVE,
            started_at=stamp,
            finished_at=stamp,
            checkpoint_fingerprint="hash-issue-1",
        )


def test_user_price_table_produces_estimate_and_cost_continuation_limit(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    policy = ResourceBudgetPolicy(
        max_estimated_cost=0.00002,
        currency="USD",
        provider_prices={
            "deepseek": ProviderPrice(prompt_per_million=1.0, completion_per_million=1.0),
        },
    )
    set_resource_budget_policy(job_id, policy)
    reservation = reserve_provider_call(job_id, provider="deepseek", stage="TEST", issue_id="ISSUE-1")
    overview = complete_provider_call(
        reservation,
        usage=ProviderUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        raw_response_hash="b" * 64,
    )

    assert overview.estimated_cost == pytest.approx(0.00003)
    assert overview.currency == "USD"
    assert overview.state == ResourceBudgetState.EXHAUSTED


def test_cost_limit_rejects_provider_missing_from_user_price_table(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(
        job_id,
        ResourceBudgetPolicy(
            max_estimated_cost=1.0,
            currency="CNY",
            provider_prices={"deepseek": ProviderPrice(prompt_per_million=1, completion_per_million=2)},
        ),
    )

    with pytest.raises(ProviderBoundaryPaused) as exc_info:
        begin_provider_call(job_id, "kimi")

    assert exc_info.value.code == "RESOURCE_COST_PRICE_UNKNOWN"
    assert resource_budget_overview(job_id).provider_calls_used == 0


def test_started_call_survives_as_conservative_crash_accounting(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    set_resource_budget_policy(job_id, ResourceBudgetPolicy(max_total_tokens=100))
    reserve_provider_call(job_id, provider="deepseek", stage="PRIMARY", issue_id="ISSUE-1")

    overview = resource_budget_overview(job_id)

    assert overview.provider_calls_used == 1
    assert overview.in_flight_calls == 1
    assert overview.unknown_usage_calls == 1
    assert overview.state == ResourceBudgetState.USAGE_UNKNOWN_BLOCKED


def test_budget_api_round_trip_never_calls_provider(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    client = TestClient(app)

    put = client.put(
        f"/api/documents/{job_id}/resource-budget",
        json={"policy": {"max_provider_calls": 4, "max_total_tokens": 5000}},
    )
    assert put.status_code == 200
    assert put.json()["policy"]["max_provider_calls"] == 4

    get = client.get(f"/api/documents/{job_id}/resource-budget")
    assert get.status_code == 200
    assert get.json()["provider_calls_used"] == 0
    assert get.json()["state"] == "WITHIN_BUDGET"


def test_budget_file_symlink_fails_closed(tmp_path: Path, monkeypatch) -> None:
    job_id = _job(tmp_path, monkeypatch)
    outside = tmp_path / "outside.json"
    outside.write_text("do-not-touch", encoding="utf-8")
    budget_path = tmp_path / "jobs" / str(job_id) / "resource-budget.json"
    try:
        budget_path.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")

    with pytest.raises(resource_budget.ResourceBudgetError, match="symlink"):
        resource_budget_overview(job_id)
    assert outside.read_text(encoding="utf-8") == "do-not-touch"
