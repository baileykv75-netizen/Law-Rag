from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .pipeline_control import PipelineControlError, clear_stale_provider_activity, get_pipeline_control
from .pipeline_models import PipelineReport, PipelineStageState, PipelineStatus
from .safe_persistence import atomic_write_text
from .storage import runtime_dir

INTERRUPTED_FAILURE_CODE = "APPLICATION_RESTARTED_RETRY_REQUIRED"
INTERRUPTED_FAILURE_DETAIL = (
    "Law-Rag 上次退出时该任务仍在后台处理中。已完成的本地产物保持不变；"
    "为避免重启后静默继续调用外部模型，请显式点击“继续/重试审计”。"
)
CANCELLED_ON_RESTART_DETAIL = (
    "Law-Rag 上次退出前已收到取消请求。任务现已确认取消；"
    "已有本地产物保持不变，任何外部模型阶段都不会自动恢复。"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cancel_report(report: PipelineReport) -> None:
    current = next((item for item in report.stages if item.stage == report.current_stage), None)
    if current is not None and current.state in {
        PipelineStageState.RUNNING,
        PipelineStageState.WAITING,
        PipelineStageState.PENDING,
    }:
        current.state = PipelineStageState.CANCELLED
        current.detail = CANCELLED_ON_RESTART_DETAIL
        current.finished_at = _now()
    report.status = PipelineStatus.CANCELLED
    report.failure_code = "PIPELINE_CANCELLED"
    report.failure_detail = CANCELLED_ON_RESTART_DETAIL
    report.completed_at = None
    report.updated_at = _now()


def reconcile_interrupted_pipelines() -> int:
    """Fail closed for work that could not survive a process restart.

    ThreadPool futures and HTTP provider requests are process-local. Persisted
    transient work therefore cannot truthfully remain active after restart.
    Explicit cancellation wins over generic interruption recovery. This function
    never resumes OCR, retrieval, providers or the Agent.
    """

    jobs_root = runtime_dir() / "jobs"
    if not jobs_root.exists() or not jobs_root.is_dir():
        return 0

    changed = 0
    for path in jobs_root.glob("*/pipeline.json"):
        if not path.is_file():
            continue
        try:
            report = PipelineReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            # Corrupt pipeline state is surfaced by integrity diagnostics; startup
            # recovery must never overwrite evidence needed to diagnose it.
            continue

        try:
            clear_stale_provider_activity(report.job_id)
            control = get_pipeline_control(report.job_id)
        except PipelineControlError:
            # A corrupt control file is itself a diagnostic condition. Do not
            # overwrite either file during startup recovery.
            continue

        if report.status == PipelineStatus.CANCEL_REQUESTED or control.cancel_requested:
            _cancel_report(report)
            atomic_write_text(path, report.model_dump_json(indent=2))
            changed += 1
            continue

        if report.status not in {
            PipelineStatus.QUEUED,
            PipelineStatus.WAITING_WORKER,
            PipelineStatus.RUNNING,
        }:
            continue

        current = next((item for item in report.stages if item.stage == report.current_stage), None)
        if current is not None and current.state in {
            PipelineStageState.RUNNING,
            PipelineStageState.WAITING,
            PipelineStageState.PENDING,
        }:
            current.state = PipelineStageState.FAILED
            current.detail = INTERRUPTED_FAILURE_DETAIL
            current.finished_at = _now()

        report.status = PipelineStatus.FAILED
        report.failure_code = INTERRUPTED_FAILURE_CODE
        report.failure_detail = INTERRUPTED_FAILURE_DETAIL
        report.completed_at = None
        report.updated_at = _now()
        atomic_write_text(path, report.model_dump_json(indent=2))
        changed += 1

    return changed
