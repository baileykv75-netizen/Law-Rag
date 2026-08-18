from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from .job_architecture import (
    JobArchitectureError,
    persist_legacy_migration_record,
    preserve_legacy_pipeline_snapshot,
    resolve_job_architecture,
)
from .job_architecture_models import JobAuditArchitecture, LegacyPipelineMigrationRequest
from .pipeline import PipelineError, _initial_stages, load_pipeline_report, start_pipeline
from .pipeline_control import get_pipeline_control, set_provider_mode
from .pipeline_models import PipelineReport, PipelineStartRequest, PipelineStatus
from .safe_persistence import atomic_write_text
from .storage import find_source_path, job_pipeline_path, runtime_dir


class LegacyPipelineMigrationError(PipelineError):
    pass


def _validate_job_inputs(job_id: UUID) -> None:
    job_dir = runtime_dir() / "jobs" / str(job_id)
    if not (job_dir / "document.json").exists() or not (job_dir / "evidence.json").exists():
        raise LegacyPipelineMigrationError(
            "Legacy job is missing document.json/evidence.json and cannot be safely re-entered into the current pipeline."
        )
    try:
        find_source_path(job_id)
    except FileNotFoundError as exc:
        raise LegacyPipelineMigrationError(str(exc)) from exc


def migrate_legacy_pipeline(
    job_id: UUID,
    request: LegacyPipelineMigrationRequest,
) -> PipelineReport:
    """Explicitly replace an inactive unfinished RC2 runtime with the Issue V1 pipeline.

    The exact legacy pipeline.json is preserved first. Legacy Stage 8/9 reports are
    deliberately left untouched as historical artifacts. The replacement pipeline
    reuses shared local artifacts through their normal freshness checks, but all
    authoritative audit-provider outputs are written to Stage 13 artifact names.
    """

    _validate_job_inputs(job_id)
    try:
        architecture = resolve_job_architecture(job_id)
    except (FileNotFoundError, JobArchitectureError) as exc:
        raise LegacyPipelineMigrationError(str(exc)) from exc

    if architecture.architecture != JobAuditArchitecture.LEGACY_RC2:
        raise LegacyPipelineMigrationError(
            f"Legacy migration requires a LEGACY_RC2 job; resolved architecture is {architecture.architecture.value}."
        )
    if not architecture.migration_available:
        raise LegacyPipelineMigrationError(
            "This legacy RC2 job is not eligible for in-place migration. Completed jobs remain readable as legacy history; "
            "active/transient jobs must first reach a safe terminal or waiting state."
        )

    legacy = load_pipeline_report(job_id)
    if legacy.status == PipelineStatus.COMPLETE:
        raise LegacyPipelineMigrationError(
            "Completed legacy RC2 jobs remain readable and are not rewritten in place. Start a new audit if a current-architecture rerun is required."
        )

    control = get_pipeline_control(job_id)
    if control.active_provider is not None:
        raise LegacyPipelineMigrationError(
            "Legacy provider activity is still recorded for this job; migration is blocked until recovery clears the stale/in-flight boundary."
        )

    snapshot, digest = preserve_legacy_pipeline_snapshot(job_id, legacy)

    now = datetime.now(timezone.utc)
    stages = _initial_stages()
    stages[0].detail = "已从旧 RC2 任务显式迁移；等待 Stage 13G 当前架构处理。"
    replacement = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.FAILED,
        current_stage=stages[0].stage,
        progress_percent=0,
        as_of=legacy.as_of,
        use_semantic=legacy.use_semantic,
        started_at=now,
        updated_at=now,
        failure_code="LEGACY_MIGRATION_PREPARED",
        failure_detail=(
            "旧 RC2 pipeline 已保留为只读历史快照；当前任务将使用 Issue V1 审计架构重新进入生产 Pipeline。"
        ),
        stages=stages,
    )
    atomic_write_text(job_pipeline_path(job_id), replacement.model_dump_json(indent=2))

    persist_legacy_migration_record(
        job_id,
        legacy_report=legacy,
        snapshot=snapshot,
        snapshot_sha256=digest,
    )
    set_provider_mode(job_id, request.provider_mode)

    return start_pipeline(
        job_id,
        PipelineStartRequest(
            as_of=legacy.as_of,
            use_semantic=legacy.use_semantic,
            provider_mode=request.provider_mode,
        ),
    )
