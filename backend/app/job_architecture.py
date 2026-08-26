from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .job_architecture_models import (
    JobArchitectureSource,
    JobArchitectureSummary,
    JobAuditArchitecture,
    LegacyPipelineMigrationRecord,
)
from .pipeline_models import PipelineReport, PipelineStage, PipelineStatus
from .safe_persistence import atomic_write_bytes, atomic_write_text, read_text_with_retry
from .storage import runtime_dir


class JobArchitectureError(RuntimeError):
    pass


LEGACY_ARTIFACT_NAMES = (
    "ai-audit.json",
    "secondary-review.json",
    "review-report.json",
)

ISSUE_ARTIFACT_NAMES = (
    "audit-plan.json",
    "issue-legal-context.json",
    "issue-primary-audit.json",
    "issue-secondary-review.json",
    "issue-review-report.json",
)

LEGACY_PIPELINE_STAGES = {
    PipelineStage.PRIMARY_AUDIT,
    PipelineStage.SECONDARY_REVIEW,
    PipelineStage.REVIEW_REPORT,
}

ISSUE_PIPELINE_STAGES = {
    PipelineStage.AUDIT_PLAN,
    PipelineStage.ISSUE_LEGAL_CONTEXT,
    PipelineStage.ISSUE_PRIMARY_AUDIT,
    PipelineStage.ISSUE_SECONDARY_REVIEW,
    PipelineStage.ISSUE_REVIEW_REPORT,
}

MIGRATION_RECORD_NAME = "job-architecture.json"
LEGACY_PIPELINE_SNAPSHOT_NAME = "pipeline-legacy-rc2.json"


def _job_dir(job_id: UUID) -> Path:
    return runtime_dir() / "jobs" / str(job_id)


def _migration_record_path(job_id: UUID) -> Path:
    return _job_dir(job_id) / MIGRATION_RECORD_NAME


def _legacy_snapshot_path(job_id: UUID) -> Path:
    return _job_dir(job_id) / LEGACY_PIPELINE_SNAPSHOT_NAME


def _pipeline_path(job_id: UUID) -> Path:
    return _job_dir(job_id) / "pipeline.json"


def _job_exists(job_id: UUID) -> bool:
    job_dir = _job_dir(job_id)
    upload_dir = runtime_dir() / "uploads" / str(job_id)
    if job_dir.exists() and any(job_dir.iterdir()):
        return True
    return upload_dir.exists() and any(upload_dir.glob("source.*"))


def _present(job_id: UUID, names: tuple[str, ...]) -> list[str]:
    root = _job_dir(job_id)
    return [name for name in names if (root / name).exists()]


def _load_pipeline_if_present(job_id: UUID) -> PipelineReport | None:
    path = _pipeline_path(job_id)
    if not path.exists():
        return None
    try:
        report = PipelineReport.model_validate_json(read_text_with_retry(path, encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise JobArchitectureError(f"Persisted pipeline.json is invalid for job {job_id}.") from exc
    if report.job_id != job_id:
        raise JobArchitectureError("Persisted pipeline.json belongs to a different job ID.")
    return report


def _pipeline_architecture(report: PipelineReport | None) -> JobAuditArchitecture | None:
    if report is None:
        return None
    has_legacy = any(item.stage in LEGACY_PIPELINE_STAGES for item in report.stages)
    has_issue = any(item.stage in ISSUE_PIPELINE_STAGES for item in report.stages)
    if has_legacy and has_issue:
        return JobAuditArchitecture.CONFLICT
    if has_issue:
        return JobAuditArchitecture.ISSUE_V1
    if has_legacy:
        return JobAuditArchitecture.LEGACY_RC2
    return None


def load_legacy_migration_record(job_id: UUID) -> LegacyPipelineMigrationRecord | None:
    path = _migration_record_path(job_id)
    if not path.exists():
        return None
    try:
        record = LegacyPipelineMigrationRecord.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise JobArchitectureError(f"Persisted {MIGRATION_RECORD_NAME} is invalid for job {job_id}.") from exc
    if record.job_id != job_id:
        raise JobArchitectureError(f"Persisted {MIGRATION_RECORD_NAME} belongs to a different job ID.")
    return record


def resolve_job_architecture(job_id: UUID) -> JobArchitectureSummary:
    """Resolve which audit artifact family is authoritative without mutating the job.

    Pipeline shape is stronger evidence than loose historical files. This matters
    after an explicit migration: old RC2 reports intentionally remain on disk for
    auditability, while the new pipeline and migration record make Issue V1
    authoritative. A mixed pipeline definition or damaged migration snapshot is a
    hard conflict rather than a reason to guess which report family should win.
    """

    if not _job_exists(job_id):
        raise FileNotFoundError(f"No local Law-Rag job exists for {job_id}.")

    legacy_artifacts = _present(job_id, LEGACY_ARTIFACT_NAMES)
    issue_artifacts = _present(job_id, ISSUE_ARTIFACT_NAMES)
    pipeline = _load_pipeline_if_present(job_id)
    pipeline_architecture = _pipeline_architecture(pipeline)
    record = load_legacy_migration_record(job_id)
    warnings: list[str] = []

    if pipeline_architecture == JobAuditArchitecture.CONFLICT:
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.CONFLICT,
            source=JobArchitectureSource.PIPELINE,
            pipeline_architecture=pipeline_architecture,
            legacy_artifacts=legacy_artifacts,
            issue_artifacts=issue_artifacts,
            migrated_from_legacy=record is not None,
            legacy_pipeline_snapshot=(record.legacy_pipeline_snapshot if record else None),
            migration_available=False,
            warnings=["pipeline.json mixes legacy RC2 and Issue V1 stage records; no audit report family is authoritative."],
        )

    if record is not None:
        snapshot = _job_dir(job_id) / record.legacy_pipeline_snapshot
        snapshot_problem: str | None = None
        if not snapshot.exists():
            snapshot_problem = "Legacy migration record exists but its preserved pipeline snapshot is missing."
        else:
            snapshot_digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            if snapshot_digest != record.legacy_pipeline_sha256:
                snapshot_problem = "Preserved legacy pipeline snapshot failed SHA-256 validation; migration history is not trustworthy."
        if snapshot_problem is not None:
            return JobArchitectureSummary(
                job_id=job_id,
                architecture=JobAuditArchitecture.CONFLICT,
                source=JobArchitectureSource.MIGRATION_RECORD,
                pipeline_architecture=pipeline_architecture,
                legacy_artifacts=legacy_artifacts,
                issue_artifacts=issue_artifacts,
                migrated_from_legacy=True,
                legacy_pipeline_snapshot=record.legacy_pipeline_snapshot,
                migration_available=False,
                warnings=[snapshot_problem],
            )
        if pipeline_architecture == JobAuditArchitecture.LEGACY_RC2:
            return JobArchitectureSummary(
                job_id=job_id,
                architecture=JobAuditArchitecture.CONFLICT,
                source=JobArchitectureSource.MIGRATION_RECORD,
                pipeline_architecture=pipeline_architecture,
                legacy_artifacts=legacy_artifacts,
                issue_artifacts=issue_artifacts,
                migrated_from_legacy=True,
                legacy_pipeline_snapshot=record.legacy_pipeline_snapshot,
                migration_available=False,
                warnings=[
                    "Migration record declares Issue V1 authoritative but current pipeline.json is still legacy RC2."
                ],
            )
        if pipeline_architecture is None:
            warnings.append("Migrated job has no current Issue V1 pipeline; migration history is retained but runtime state is incomplete.")
        if legacy_artifacts:
            warnings.append("Legacy Stage 8/9 reports are preserved as historical artifacts and are not authoritative for this migrated job.")
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.ISSUE_V1,
            source=JobArchitectureSource.MIGRATION_RECORD,
            pipeline_architecture=pipeline_architecture,
            legacy_artifacts=legacy_artifacts,
            issue_artifacts=issue_artifacts,
            migrated_from_legacy=True,
            legacy_pipeline_snapshot=record.legacy_pipeline_snapshot,
            migration_available=False,
            warnings=warnings,
        )

    if pipeline_architecture == JobAuditArchitecture.ISSUE_V1:
        if legacy_artifacts:
            warnings.append("Legacy Stage 8/9 reports are present, but the current pipeline shape makes Issue V1 authoritative.")
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.ISSUE_V1,
            source=JobArchitectureSource.PIPELINE,
            pipeline_architecture=pipeline_architecture,
            legacy_artifacts=legacy_artifacts,
            issue_artifacts=issue_artifacts,
            migration_available=False,
            warnings=warnings,
        )

    if pipeline_architecture == JobAuditArchitecture.LEGACY_RC2:
        if issue_artifacts:
            warnings.append("Issue V1 artifacts exist beside a legacy production pipeline; they are non-authoritative until an explicit migration occurs.")
        migration_available = pipeline is not None and pipeline.status not in {
            PipelineStatus.COMPLETE,
            PipelineStatus.QUEUED,
            PipelineStatus.WAITING_WORKER,
            PipelineStatus.RUNNING,
            PipelineStatus.CANCEL_REQUESTED,
        }
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.LEGACY_RC2,
            source=JobArchitectureSource.PIPELINE,
            pipeline_architecture=pipeline_architecture,
            legacy_artifacts=legacy_artifacts,
            issue_artifacts=issue_artifacts,
            migration_available=migration_available,
            warnings=warnings,
        )

    if legacy_artifacts and issue_artifacts:
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.CONFLICT,
            source=JobArchitectureSource.ARTIFACTS,
            legacy_artifacts=legacy_artifacts,
            issue_artifacts=issue_artifacts,
            migration_available=False,
            warnings=["Both legacy RC2 and Issue V1 audit artifacts exist without a pipeline or migration record to establish authority."],
        )
    if issue_artifacts:
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.ISSUE_V1,
            source=JobArchitectureSource.ARTIFACTS,
            issue_artifacts=issue_artifacts,
            migration_available=False,
        )
    if legacy_artifacts:
        return JobArchitectureSummary(
            job_id=job_id,
            architecture=JobAuditArchitecture.LEGACY_RC2,
            source=JobArchitectureSource.ARTIFACTS,
            legacy_artifacts=legacy_artifacts,
            migration_available=False,
            warnings=["Legacy reports are readable, but no legacy pipeline.json is available for explicit migration."],
        )

    # Jobs that never reached an audit-provider stage can safely enter the current
    # architecture because there is no legacy authoritative audit result to mix.
    return JobArchitectureSummary(
        job_id=job_id,
        architecture=JobAuditArchitecture.ISSUE_V1,
        source=JobArchitectureSource.CURRENT_DEFAULT,
        migration_available=False,
    )


def preserve_legacy_pipeline_snapshot(job_id: UUID, report: PipelineReport) -> tuple[Path, str]:
    """Atomically preserve the exact legacy pipeline bytes before replacement."""

    if report.job_id != job_id:
        raise JobArchitectureError("Legacy pipeline report belongs to a different job ID.")
    source = _pipeline_path(job_id)
    if not source.exists():
        raise JobArchitectureError("Legacy pipeline.json is missing; migration cannot preserve its runtime history.")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = _legacy_snapshot_path(job_id)
    if snapshot.exists():
        existing = snapshot.read_bytes()
        existing_digest = hashlib.sha256(existing).hexdigest()
        if existing_digest != digest:
            raise JobArchitectureError("A different legacy pipeline snapshot already exists; refusing to overwrite migration history.")
        return snapshot, digest
    atomic_write_bytes(snapshot, raw)
    return snapshot, digest


def persist_legacy_migration_record(
    job_id: UUID,
    *,
    legacy_report: PipelineReport,
    snapshot: Path,
    snapshot_sha256: str,
) -> LegacyPipelineMigrationRecord:
    record = LegacyPipelineMigrationRecord(
        job_id=job_id,
        migrated_at=datetime.now(timezone.utc),
        legacy_pipeline_snapshot=snapshot.name,
        legacy_pipeline_sha256=snapshot_sha256,
        legacy_pipeline_engine_version=legacy_report.engine_version,
        legacy_pipeline_status=legacy_report.status.value,
    )
    atomic_write_text(_migration_record_path(job_id), record.model_dump_json(indent=2))
    return record
