from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .pipeline_control_models import PipelineControl, ProviderExecutionMode
from .safe_persistence import atomic_write_text
from .storage import runtime_dir


class PipelineControlError(RuntimeError):
    pass


class ProviderBoundaryPaused(PipelineControlError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class PipelineCancellationRequested(PipelineControlError):
    pass


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


def pipeline_control_path(job_id: UUID) -> Path:
    return runtime_dir() / "jobs" / str(job_id) / "pipeline-control.json"


def _new_control(job_id: UUID, provider_mode: ProviderExecutionMode) -> PipelineControl:
    return PipelineControl(job_id=job_id, provider_mode=provider_mode, updated_at=_now())


def _read_existing(job_id: UUID) -> PipelineControl | None:
    path = pipeline_control_path(job_id)
    if not path.exists():
        return None
    try:
        control = PipelineControl.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise PipelineControlError(f"Persisted pipeline control is invalid for job {job_id}.") from exc
    if control.job_id != job_id:
        raise PipelineControlError(f"Persisted pipeline control belongs to another job: {job_id}.")
    return control


def _persist(control: PipelineControl) -> PipelineControl:
    control.updated_at = _now()
    path = pipeline_control_path(control.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, control.model_dump_json(indent=2))
    return control


def get_pipeline_control(
    job_id: UUID,
    *,
    fallback_mode: ProviderExecutionMode = ProviderExecutionMode.AUTO_CONTINUE,
) -> PipelineControl:
    """Read current control without creating a file when none exists."""

    with _lock_for(job_id):
        existing = _read_existing(job_id)
        return existing if existing is not None else _new_control(job_id, fallback_mode)


def ensure_pipeline_control(job_id: UUID, provider_mode: ProviderExecutionMode) -> PipelineControl:
    with _lock_for(job_id):
        existing = _read_existing(job_id)
        if existing is not None:
            return existing
        return _persist(_new_control(job_id, provider_mode))


def set_provider_mode(job_id: UUID, provider_mode: ProviderExecutionMode) -> PipelineControl:
    with _lock_for(job_id):
        control = _read_existing(job_id) or _new_control(job_id, provider_mode)
        control.provider_mode = provider_mode
        if provider_mode in {ProviderExecutionMode.REQUIRE_APPROVAL, ProviderExecutionMode.LOCAL_ONLY}:
            control.provider_approved = False
        control.cancel_requested = False
        control.cancel_requested_at = None
        return _persist(control)


def approve_provider_phase(job_id: UUID) -> PipelineControl:
    with _lock_for(job_id):
        control = _read_existing(job_id) or _new_control(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)
        control.provider_mode = ProviderExecutionMode.REQUIRE_APPROVAL
        control.provider_approved = True
        control.cancel_requested = False
        control.cancel_requested_at = None
        return _persist(control)


def request_pipeline_cancel(job_id: UUID) -> PipelineControl:
    with _lock_for(job_id):
        control = _read_existing(job_id) or _new_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)
        control.cancel_requested = True
        control.cancel_requested_at = control.cancel_requested_at or _now()
        return _persist(control)


def clear_pipeline_cancel(job_id: UUID) -> PipelineControl:
    with _lock_for(job_id):
        control = _read_existing(job_id) or _new_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)
        control.cancel_requested = False
        control.cancel_requested_at = None
        return _persist(control)


def assert_pipeline_not_cancelled(job_id: UUID) -> PipelineControl:
    control = get_pipeline_control(job_id)
    if control.cancel_requested:
        raise PipelineCancellationRequested("Pipeline cancellation was requested.")
    return control


def assert_provider_allowed(job_id: UUID) -> PipelineControl:
    control = assert_pipeline_not_cancelled(job_id)
    if control.provider_mode == ProviderExecutionMode.LOCAL_ONLY:
        raise ProviderBoundaryPaused(
            "LOCAL_ONLY_PROVIDER_DISABLED",
            "本地处理已完成；当前批次设置为仅本地处理，尚未向 DeepSeek/Kimi 发送合同证据。",
        )
    if control.provider_mode == ProviderExecutionMode.REQUIRE_APPROVAL and not control.provider_approved:
        raise ProviderBoundaryPaused(
            "PROVIDER_APPROVAL_REQUIRED",
            "本地处理已完成；发送受限合同/法律证据到 DeepSeek 与 Kimi 前需要你的明确确认。",
        )
    return control


def begin_provider_call(job_id: UUID, provider: str) -> PipelineControl:
    """Atomically cross every local guard before one outbound model request.

    Provider approval/cancellation is checked first. The active-provider marker
    is safely persisted before a Stage 18.3 budget reservation is created. If
    that reservation fails, the active marker is rolled back before returning.
    Once this function returns successfully, the caller is allowed to execute
    exactly one external `provider.generate(...)` request and that request has a
    durable call-ledger reservation.
    """

    with _lock_for(job_id):
        control = _read_existing(job_id) or _new_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)
        if control.cancel_requested:
            raise PipelineCancellationRequested("Pipeline cancellation was requested.")
        if control.provider_mode == ProviderExecutionMode.LOCAL_ONLY:
            raise ProviderBoundaryPaused(
                "LOCAL_ONLY_PROVIDER_DISABLED",
                "当前任务设置为仅本地处理，未授权外部模型调用。",
            )
        if control.provider_mode == ProviderExecutionMode.REQUIRE_APPROVAL and not control.provider_approved:
            raise ProviderBoundaryPaused(
                "PROVIDER_APPROVAL_REQUIRED",
                "外部模型调用需要明确确认。",
            )

        control.active_provider = provider
        control.active_provider_started_at = _now()
        control = _persist(control)
        try:
            from .resource_budget import ResourceBudgetError, ResourceBudgetExceeded, reserve_provider_call

            reserve_provider_call(job_id, provider=provider)
        except ResourceBudgetExceeded as exc:
            control.active_provider = None
            control.active_provider_started_at = None
            _persist(control)
            raise ProviderBoundaryPaused(exc.code, exc.detail) from exc
        except (ResourceBudgetError, FileNotFoundError) as exc:
            control.active_provider = None
            control.active_provider_started_at = None
            _persist(control)
            raise ProviderBoundaryPaused(
                "RESOURCE_BUDGET_INVALID",
                f"本地资源预算状态无法安全验证，未发送外部模型请求：{exc}",
            ) from exc
        return control


def finish_provider_call(job_id: UUID, provider: str) -> PipelineControl:
    with _lock_for(job_id):
        control = _read_existing(job_id) or _new_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)
        if control.active_provider == provider:
            try:
                from .resource_budget import ResourceBudgetError, mark_latest_provider_call_returned

                mark_latest_provider_call_returned(job_id, provider)
            except (ResourceBudgetError, FileNotFoundError) as exc:
                control.active_provider = None
                control.active_provider_started_at = None
                _persist(control)
                raise ProviderBoundaryPaused(
                    "RESOURCE_BUDGET_ACCOUNTING_ERROR",
                    f"外部模型请求已结束，但本地资源用量账本无法安全更新：{exc}",
                ) from exc
            control.active_provider = None
            control.active_provider_started_at = None
        return _persist(control)


def clear_stale_provider_activity(job_id: UUID) -> None:
    """Clear process-local provider activity during startup recovery only.

    Stage 18.3 deliberately does not erase the corresponding STARTED resource
    ledger row. A process crash after the provider boundary is conservatively
    counted as a call with unknown usage; token/cost-limited continuation then
    requires explicit attention instead of assuming the lost usage was zero.
    """

    with _lock_for(job_id):
        control = _read_existing(job_id)
        if control is None or control.active_provider is None:
            return
        control.active_provider = None
        control.active_provider_started_at = None
        _persist(control)
