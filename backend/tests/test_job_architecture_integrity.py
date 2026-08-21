from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.job_architecture import resolve_job_architecture
from app.job_architecture_models import (
    JobAuditArchitecture,
    LegacyPipelineMigrationRecord,
)
from app.pipeline import _initial_stages
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStatus


def test_tampered_legacy_pipeline_snapshot_forces_architecture_conflict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = tmp_path / "jobs" / str(job_id)
    upload_dir = tmp_path / "uploads" / str(job_id)
    job_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    (job_dir / "document.json").write_text("{}", encoding="utf-8")
    (job_dir / "evidence.json").write_text("[]", encoding="utf-8")
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\n")

    now = datetime.now(timezone.utc)
    current = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.FAILED,
        current_stage=PipelineStage.AUDIT_PLAN,
        progress_percent=48,
        as_of=now.date(),
        started_at=now,
        updated_at=now,
        failure_code="fixture",
        failure_detail="fixture",
        stages=_initial_stages(),
    )
    (job_dir / "pipeline.json").write_text(current.model_dump_json(indent=2), encoding="utf-8")

    original_snapshot = b'{"legacy":"pipeline"}'
    snapshot_path = job_dir / "pipeline-legacy-rc2.json"
    snapshot_path.write_bytes(original_snapshot)
    record = LegacyPipelineMigrationRecord(
        job_id=job_id,
        migrated_at=now,
        legacy_pipeline_snapshot=snapshot_path.name,
        legacy_pipeline_sha256=hashlib.sha256(original_snapshot).hexdigest(),
        legacy_pipeline_engine_version="stage13a-1.0.0",
        legacy_pipeline_status="FAILED",
    )
    (job_dir / "job-architecture.json").write_text(record.model_dump_json(indent=2), encoding="utf-8")

    snapshot_path.write_bytes(b'{"legacy":"tampered"}')
    summary = resolve_job_architecture(job_id)
    assert summary.architecture == JobAuditArchitecture.CONFLICT
    assert summary.migrated_from_legacy is True
    assert summary.migration_available is False
    assert any("SHA-256" in warning for warning in summary.warnings)
