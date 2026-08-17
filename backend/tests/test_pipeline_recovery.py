from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.pipeline_models import PipelineReport, PipelineStage, PipelineStageRecord, PipelineStageState, PipelineStatus
from app.pipeline_recovery import INTERRUPTED_FAILURE_CODE, reconcile_interrupted_pipelines


def _write_pipeline(root: Path, status: PipelineStatus, stage_state: PipelineStageState) -> Path:
    job_id = uuid4()
    job_dir = root / "jobs" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    report = PipelineReport(
        job_id=job_id,
        status=status,
        current_stage=PipelineStage.PRIMARY_AUDIT,
        progress_percent=55,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        stages=[
            PipelineStageRecord(
                stage=PipelineStage.PRIMARY_AUDIT,
                state=stage_state,
                label="检索法律依据并进行主审",
                progress_percent=75,
            )
        ],
    )
    path = job_dir / "pipeline.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    return path


def test_restart_reconciliation_marks_transient_pipeline_retry_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    path = _write_pipeline(tmp_path, PipelineStatus.RUNNING, PipelineStageState.RUNNING)

    assert reconcile_interrupted_pipelines() == 1
    recovered = PipelineReport.model_validate_json(path.read_text(encoding="utf-8"))
    assert recovered.status == PipelineStatus.FAILED
    assert recovered.failure_code == INTERRUPTED_FAILURE_CODE
    assert recovered.stages[0].state == PipelineStageState.FAILED
    assert "显式" in (recovered.failure_detail or "")


def test_restart_reconciliation_leaves_intentional_waiting_and_complete_untouched(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    waiting = _write_pipeline(tmp_path, PipelineStatus.WAITING_CONFIGURATION, PipelineStageState.WAITING)
    complete = _write_pipeline(tmp_path, PipelineStatus.COMPLETE, PipelineStageState.COMPLETE)
    waiting_before = waiting.read_bytes()
    complete_before = complete.read_bytes()

    assert reconcile_interrupted_pipelines() == 0
    assert waiting.read_bytes() == waiting_before
    assert complete.read_bytes() == complete_before


def test_restart_reconciliation_does_not_create_runtime_when_absent(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "does-not-exist"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    assert reconcile_interrupted_pipelines() == 0
    assert not runtime.exists()
