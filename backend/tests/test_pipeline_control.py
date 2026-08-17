from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import _mark_done, _mark_running
from app.pipeline_control import (
    PipelineCancellationRequested,
    begin_provider_call,
    ensure_pipeline_control,
    finish_provider_call,
    get_pipeline_control,
    pipeline_control_path,
    request_pipeline_cancel,
)
from app.pipeline_control_models import ProviderExecutionMode
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStatus
from app.pipeline_recovery import reconcile_interrupted_pipelines
from app.safe_persistence import atomic_write_text

client = TestClient(app)


def _seed_job(root: Path, job_id) -> None:
    job_dir = root / "jobs" / str(job_id)
    upload_dir = root / "uploads" / str(job_id)
    job_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    (job_dir / "document.json").write_text("{}", encoding="utf-8")
    (job_dir / "evidence.json").write_text("[]", encoding="utf-8")
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\n")


def _wait(job_id, terminal: set[str], timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/documents/{job_id}/pipeline")
        if response.status_code == 200 and response.json()["status"] in terminal:
            return response.json()
        time.sleep(0.02)
    raise AssertionError("pipeline did not reach expected state")


def _complete_stage(stage: PipelineStage, calls: list[object] | None = None):
    def runner(report: PipelineReport) -> None:
        if calls is not None:
            calls.append(stage)
        _mark_running(report, stage, f"running {stage.value}")
        _mark_done(report, stage, detail=f"done {stage.value}")

    return runner


def _patch_local_stages(monkeypatch, calls: list[object]) -> None:
    import app.pipeline as pipeline

    monkeypatch.setattr(pipeline, "_run_ocr_stage", _complete_stage(PipelineStage.OCR, calls))
    monkeypatch.setattr(pipeline, "_run_structure_stage", _complete_stage(PipelineStage.STRUCTURE, calls))
    monkeypatch.setattr(pipeline, "_run_rules_stage", _complete_stage(PipelineStage.RULES, calls))


def _patch_primary_context(monkeypatch, calls: list[object]) -> None:
    """Simulate Stage 8 local context construction before its outbound hooks."""

    import app.pipeline as pipeline

    def fake_primary(job_id, request, *, provider_override=None, provider_gate=None, before_provider_generate=None):
        calls.append("PRIMARY_LOCAL_CONTEXT")
        assert provider_gate is not None
        assert before_provider_generate is not None
        provider_gate()
        calls.append("PRIMARY_GATE_ALLOWED")
        before_provider_generate()
        calls.append(PipelineStage.PRIMARY_AUDIT)
        return object()

    monkeypatch.setattr(pipeline, "run_primary_ai_audit", fake_primary)


def test_require_approval_finishes_local_work_and_context_without_provider_call(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    calls: list[object] = []
    _patch_local_stages(monkeypatch, calls)
    _patch_primary_context(monkeypatch, calls)

    def forbidden_provider_stage(*args, **kwargs):
        raise AssertionError("secondary/review stages must not run before explicit approval")

    monkeypatch.setattr(pipeline, "_run_secondary_stage", forbidden_provider_stage)
    monkeypatch.setattr(pipeline, "_run_review_stage", forbidden_provider_stage)

    response = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={
            "as_of": "2026-08-17",
            "use_semantic": False,
            "provider_mode": "REQUIRE_APPROVAL",
        },
    )
    assert response.status_code == 202

    paused = _wait(job_id, {"PAUSED_BEFORE_PROVIDER"})
    assert paused["current_stage"] == "PRIMARY_AUDIT"
    assert paused["failure_code"] == "PROVIDER_APPROVAL_REQUIRED"
    assert paused["progress_percent"] == 55
    assert calls == [
        PipelineStage.OCR,
        PipelineStage.STRUCTURE,
        PipelineStage.RULES,
        "PRIMARY_LOCAL_CONTEXT",
    ]
    control = get_pipeline_control(job_id)
    assert control.active_provider is None


def test_local_only_stops_after_local_context_and_can_be_approved_later(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    calls: list[object] = []
    _patch_local_stages(monkeypatch, calls)
    _patch_primary_context(monkeypatch, calls)
    monkeypatch.setattr(pipeline, "_run_secondary_stage", _complete_stage(PipelineStage.SECONDARY_REVIEW, calls))
    monkeypatch.setattr(pipeline, "_run_review_stage", _complete_stage(PipelineStage.REVIEW_REPORT, calls))

    response = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={"as_of": "2026-08-17", "provider_mode": "LOCAL_ONLY"},
    )
    assert response.status_code == 202
    paused = _wait(job_id, {"PAUSED_BEFORE_PROVIDER"})
    assert paused["failure_code"] == "LOCAL_ONLY_PROVIDER_DISABLED"
    assert PipelineStage.PRIMARY_AUDIT not in calls
    assert "PRIMARY_LOCAL_CONTEXT" in calls

    approved = client.post(f"/api/documents/{job_id}/pipeline/approve-provider")
    assert approved.status_code == 202
    completed = _wait(job_id, {"COMPLETE"})
    assert completed["progress_percent"] == 100
    assert calls[-3:] == [
        PipelineStage.PRIMARY_AUDIT,
        PipelineStage.SECONDARY_REVIEW,
        PipelineStage.REVIEW_REPORT,
    ]


def test_cancelled_pipeline_requires_explicit_resume_and_does_not_bypass_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    calls: list[object] = []
    _patch_local_stages(monkeypatch, calls)
    _patch_primary_context(monkeypatch, calls)
    monkeypatch.setattr(pipeline, "_run_secondary_stage", _complete_stage(PipelineStage.SECONDARY_REVIEW, calls))
    monkeypatch.setattr(pipeline, "_run_review_stage", _complete_stage(PipelineStage.REVIEW_REPORT, calls))

    client.post(
        f"/api/documents/{job_id}/pipeline",
        json={"as_of": "2026-08-17", "provider_mode": "REQUIRE_APPROVAL"},
    )
    _wait(job_id, {"PAUSED_BEFORE_PROVIDER"})

    cancelled = client.post(f"/api/documents/{job_id}/pipeline/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["control"]["cancel_requested"] is True
    assert _wait(job_id, {"CANCELLED"})["failure_code"] == "PIPELINE_CANCELLED"

    retry = client.post(f"/api/documents/{job_id}/pipeline/retry")
    assert retry.status_code == 409

    resumed = client.post(f"/api/documents/{job_id}/pipeline/resume")
    assert resumed.status_code == 202
    paused_again = _wait(job_id, {"PAUSED_BEFORE_PROVIDER"})
    assert paused_again["failure_code"] == "PROVIDER_APPROVAL_REQUIRED"


def test_cancel_after_provider_boundary_blocks_next_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    (tmp_path / "jobs" / str(job_id)).mkdir(parents=True)
    ensure_pipeline_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)

    started = begin_provider_call(job_id, "deepseek")
    assert started.active_provider == "deepseek"

    cancelled = request_pipeline_cancel(job_id)
    assert cancelled.cancel_requested is True
    assert cancelled.active_provider == "deepseek"

    with pytest.raises(PipelineCancellationRequested):
        begin_provider_call(job_id, "kimi")

    finished = finish_provider_call(job_id, "deepseek")
    assert finished.active_provider is None
    assert finished.cancel_requested is True


def test_control_get_for_legacy_job_is_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = tmp_path / "jobs" / str(job_id)
    job_dir.mkdir(parents=True)

    import app.pipeline as pipeline

    now = pipeline._now()
    report = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.FAILED,
        current_stage=PipelineStage.PRIMARY_AUDIT,
        progress_percent=55,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        failure_code="legacy",
        failure_detail="legacy",
        stages=pipeline._initial_stages(),
    )
    atomic_write_text(job_dir / "pipeline.json", report.model_dump_json(indent=2))

    response = client.get(f"/api/documents/{job_id}/pipeline/control")
    assert response.status_code == 200
    assert response.json()["provider_mode"] == "AUTO_CONTINUE"
    assert not pipeline_control_path(job_id).exists()


def test_restart_turns_persisted_cancel_request_into_cancelled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = tmp_path / "jobs" / str(job_id)
    job_dir.mkdir(parents=True)

    import app.pipeline as pipeline

    now = pipeline._now()
    report = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.CANCEL_REQUESTED,
        current_stage=PipelineStage.PRIMARY_AUDIT,
        progress_percent=55,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        stages=pipeline._initial_stages(),
    )
    atomic_write_text(job_dir / "pipeline.json", report.model_dump_json(indent=2))
    ensure_pipeline_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)
    begin_provider_call(job_id, "deepseek")
    request_pipeline_cancel(job_id)

    assert reconcile_interrupted_pipelines() == 1
    recovered = PipelineReport.model_validate_json((job_dir / "pipeline.json").read_text(encoding="utf-8"))
    assert recovered.status == PipelineStatus.CANCELLED
    assert recovered.failure_code == "PIPELINE_CANCELLED"
    control = get_pipeline_control(job_id)
    assert control.active_provider is None
    assert control.cancel_requested is True
