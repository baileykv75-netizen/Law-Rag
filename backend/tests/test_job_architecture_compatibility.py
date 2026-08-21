from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.job_architecture import resolve_job_architecture
from app.job_architecture_models import JobArchitectureSource, JobAuditArchitecture
from app.main import app
from app.pipeline import _mark_done, _mark_running
from app.pipeline_models import (
    PipelineReport,
    PipelineStage,
    PipelineStageRecord,
    PipelineStageState,
    PipelineStatus,
)
from app.safe_persistence import atomic_write_text

client = TestClient(app)


def _seed_job(root: Path, job_id) -> Path:
    job_dir = root / "jobs" / str(job_id)
    upload_dir = root / "uploads" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "document.json").write_text("{}", encoding="utf-8")
    (job_dir / "evidence.json").write_text("[]", encoding="utf-8")
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\n")
    return job_dir


def _legacy_pipeline(job_id, *, status: PipelineStatus = PipelineStatus.FAILED) -> PipelineReport:
    from app.pipeline import _now

    now = _now()
    return PipelineReport(
        schema_version="1.2.0",
        engine_version="stage13a-1.0.0",
        job_id=job_id,
        status=status,
        current_stage=PipelineStage.PRIMARY_AUDIT,
        progress_percent=55 if status != PipelineStatus.COMPLETE else 100,
        as_of=date(2026, 8, 17),
        use_semantic=False,
        started_at=now,
        updated_at=now,
        completed_at=now if status == PipelineStatus.COMPLETE else None,
        failure_code="legacy-fixture" if status == PipelineStatus.FAILED else None,
        failure_detail="legacy fixture" if status == PipelineStatus.FAILED else None,
        stages=[
            PipelineStageRecord(
                stage=PipelineStage.PRIMARY_AUDIT,
                state=(
                    PipelineStageState.COMPLETE
                    if status == PipelineStatus.COMPLETE
                    else PipelineStageState.FAILED
                ),
                label="检索法律依据并进行主审",
                progress_percent=75,
            ),
            PipelineStageRecord(
                stage=PipelineStage.SECONDARY_REVIEW,
                state=(
                    PipelineStageState.COMPLETE
                    if status == PipelineStatus.COMPLETE
                    else PipelineStageState.PENDING
                ),
                label="进行独立二审",
                progress_percent=90,
            ),
            PipelineStageRecord(
                stage=PipelineStage.REVIEW_REPORT,
                state=(
                    PipelineStageState.COMPLETE
                    if status == PipelineStatus.COMPLETE
                    else PipelineStageState.PENDING
                ),
                label="比较双模型并整理结果",
                progress_percent=100,
            ),
        ],
    )


def _issue_pipeline(job_id) -> PipelineReport:
    from app.pipeline import _initial_stages, _now

    now = _now()
    return PipelineReport(
        job_id=job_id,
        status=PipelineStatus.FAILED,
        current_stage=PipelineStage.AUDIT_PLAN,
        progress_percent=48,
        as_of=date(2026, 8, 18),
        started_at=now,
        updated_at=now,
        failure_code="fixture",
        failure_detail="fixture",
        stages=_initial_stages(),
    )


def _complete_stage(stage: PipelineStage):
    def runner(report: PipelineReport) -> None:
        _mark_running(report, stage, f"compatibility fixture running {stage.value}")
        _mark_done(report, stage, detail=f"compatibility fixture done {stage.value}")

    return runner


def _patch_all_current_stages(monkeypatch) -> None:
    import app.pipeline as pipeline

    monkeypatch.setattr(pipeline, "_run_ocr_stage", _complete_stage(PipelineStage.OCR))
    monkeypatch.setattr(pipeline, "_run_structure_stage", _complete_stage(PipelineStage.STRUCTURE))
    monkeypatch.setattr(pipeline, "_run_rules_stage", _complete_stage(PipelineStage.RULES))
    monkeypatch.setattr(pipeline, "_run_audit_plan_stage", _complete_stage(PipelineStage.AUDIT_PLAN))
    monkeypatch.setattr(
        pipeline,
        "_run_issue_legal_context_stage",
        _complete_stage(PipelineStage.ISSUE_LEGAL_CONTEXT),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_issue_primary_stage",
        _complete_stage(PipelineStage.ISSUE_PRIMARY_AUDIT),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_issue_secondary_stage",
        _complete_stage(PipelineStage.ISSUE_SECONDARY_REVIEW),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_issue_review_stage",
        _complete_stage(PipelineStage.ISSUE_REVIEW_REPORT),
    )


def _wait(job_id, terminal: set[str], timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/documents/{job_id}/pipeline")
        if response.status_code == 200 and response.json()["status"] in terminal:
            return response.json()
        time.sleep(0.02)
    raise AssertionError("pipeline did not reach expected state")


def test_architecture_resolver_keeps_completed_rc2_job_legacy_and_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = _seed_job(tmp_path, job_id)
    legacy = _legacy_pipeline(job_id, status=PipelineStatus.COMPLETE)
    raw = legacy.model_dump_json(indent=2)
    (job_dir / "pipeline.json").write_text(raw, encoding="utf-8")
    (job_dir / "review-report.json").write_text('{"legacy": true}', encoding="utf-8")

    before = (job_dir / "pipeline.json").read_bytes()
    response = client.get(f"/api/documents/{job_id}/architecture")
    assert response.status_code == 200
    body = response.json()
    assert body["architecture"] == "LEGACY_RC2"
    assert body["source"] == "PIPELINE"
    assert body["migration_available"] is False
    assert body["legacy_artifacts"] == ["review-report.json"]
    assert not (job_dir / "job-architecture.json").exists()
    assert (job_dir / "pipeline.json").read_bytes() == before


def test_current_pipeline_is_authoritative_even_when_legacy_reports_are_preserved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = _seed_job(tmp_path, job_id)
    atomic_write_text(job_dir / "pipeline.json", _issue_pipeline(job_id).model_dump_json(indent=2))
    (job_dir / "ai-audit.json").write_text("{}", encoding="utf-8")
    (job_dir / "issue-primary-audit.json").write_text("{}", encoding="utf-8")

    summary = resolve_job_architecture(job_id)
    assert summary.architecture == JobAuditArchitecture.ISSUE_V1
    assert summary.source == JobArchitectureSource.PIPELINE
    assert summary.legacy_artifacts == ["ai-audit.json"]
    assert summary.issue_artifacts == ["issue-primary-audit.json"]
    assert any("historical" not in warning.lower() or warning for warning in summary.warnings)


def test_unowned_mixed_artifacts_fail_closed_as_conflict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = _seed_job(tmp_path, job_id)
    (job_dir / "review-report.json").write_text("{}", encoding="utf-8")
    (job_dir / "issue-review-report.json").write_text("{}", encoding="utf-8")

    summary = resolve_job_architecture(job_id)
    assert summary.architecture == JobAuditArchitecture.CONFLICT
    assert summary.source == JobArchitectureSource.ARTIFACTS
    assert summary.migration_available is False


def test_explicit_legacy_migration_preserves_snapshot_and_historical_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = _seed_job(tmp_path, job_id)
    legacy = _legacy_pipeline(job_id)
    legacy_raw = legacy.model_dump_json(indent=2).encode("utf-8")
    (job_dir / "pipeline.json").write_bytes(legacy_raw)

    historical = {
        "ai-audit.json": b'{"legacy":"primary"}',
        "secondary-review.json": b'{"legacy":"secondary"}',
        "review-report.json": b'{"legacy":"review"}',
    }
    for name, content in historical.items():
        (job_dir / name).write_bytes(content)

    before = client.get(f"/api/documents/{job_id}/architecture")
    assert before.status_code == 200
    assert before.json()["architecture"] == "LEGACY_RC2"
    assert before.json()["migration_available"] is True

    _patch_all_current_stages(monkeypatch)
    migrated = client.post(
        f"/api/documents/{job_id}/pipeline/migrate-legacy",
        json={"provider_mode": "REQUIRE_APPROVAL"},
    )
    assert migrated.status_code == 202, migrated.text
    completed = _wait(job_id, {"COMPLETE"})
    assert completed["current_stage"] == "COMPLETE"
    assert [item["stage"] for item in completed["stages"]] == [
        "INGEST",
        "OCR",
        "STRUCTURE",
        "RULES",
        "AUDIT_PLAN",
        "ISSUE_LEGAL_CONTEXT",
        "ISSUE_PRIMARY_AUDIT",
        "ISSUE_SECONDARY_REVIEW",
        "ISSUE_REVIEW_REPORT",
    ]

    assert (job_dir / "pipeline-legacy-rc2.json").read_bytes() == legacy_raw
    assert (job_dir / "job-architecture.json").exists()
    for name, content in historical.items():
        assert (job_dir / name).read_bytes() == content

    after = client.get(f"/api/documents/{job_id}/architecture")
    assert after.status_code == 200
    body = after.json()
    assert body["architecture"] == "ISSUE_V1"
    assert body["source"] == "MIGRATION_RECORD"
    assert body["migrated_from_legacy"] is True
    assert body["legacy_pipeline_snapshot"] == "pipeline-legacy-rc2.json"
    assert set(body["legacy_artifacts"]) == set(historical)

    second = client.post(
        f"/api/documents/{job_id}/pipeline/migrate-legacy",
        json={"provider_mode": "REQUIRE_APPROVAL"},
    )
    assert second.status_code == 409


def test_completed_legacy_job_cannot_be_rewritten_in_place(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = _seed_job(tmp_path, job_id)
    legacy = _legacy_pipeline(job_id, status=PipelineStatus.COMPLETE)
    raw = legacy.model_dump_json(indent=2).encode("utf-8")
    (job_dir / "pipeline.json").write_bytes(raw)

    response = client.post(
        f"/api/documents/{job_id}/pipeline/migrate-legacy",
        json={"provider_mode": "REQUIRE_APPROVAL"},
    )
    assert response.status_code == 409
    assert (job_dir / "pipeline.json").read_bytes() == raw
    assert not (job_dir / "pipeline-legacy-rc2.json").exists()
    assert not (job_dir / "job-architecture.json").exists()
