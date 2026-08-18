from __future__ import annotations

import threading
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline import _mark_done, _mark_running, _run_structure_stage
from app.pipeline_models import (
    PipelineReport,
    PipelineStage,
    PipelineStageState,
    PipelineStartRequest,
    PipelineStatus,
)
from app.storage import job_contract_path

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
    raise AssertionError("pipeline did not reach a terminal/waiting state")


def _complete_stage(stage: PipelineStage, calls: list[PipelineStage] | None = None):
    def runner(report: PipelineReport) -> None:
        if calls is not None:
            calls.append(stage)
        _mark_running(report, stage, f"running {stage.value}")
        _mark_done(report, stage, detail=f"done {stage.value}")

    return runner


def _patch_stage13_tail(monkeypatch, calls: list[PipelineStage] | None = None) -> None:
    import app.pipeline as pipeline

    monkeypatch.setattr(pipeline, "_run_audit_plan_stage", _complete_stage(PipelineStage.AUDIT_PLAN, calls))
    monkeypatch.setattr(
        pipeline,
        "_run_issue_legal_context_stage",
        _complete_stage(PipelineStage.ISSUE_LEGAL_CONTEXT, calls),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_issue_primary_stage",
        _complete_stage(PipelineStage.ISSUE_PRIMARY_AUDIT, calls),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_issue_secondary_stage",
        _complete_stage(PipelineStage.ISSUE_SECONDARY_REVIEW, calls),
    )
    monkeypatch.setattr(
        pipeline,
        "_run_issue_review_stage",
        _complete_stage(PipelineStage.ISSUE_REVIEW_REPORT, calls),
    )


def test_pipeline_runs_in_background_persists_real_stage_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    calls: list[PipelineStage] = []
    monkeypatch.setattr(pipeline, "_run_ocr_stage", _complete_stage(PipelineStage.OCR, calls))
    monkeypatch.setattr(pipeline, "_run_structure_stage", _complete_stage(PipelineStage.STRUCTURE, calls))
    monkeypatch.setattr(pipeline, "_run_rules_stage", _complete_stage(PipelineStage.RULES, calls))
    _patch_stage13_tail(monkeypatch, calls)

    response = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={"as_of": "2026-08-17", "use_semantic": False},
    )
    assert response.status_code == 202

    body = _wait(job_id, {"COMPLETE"})
    assert body["progress_percent"] == 100
    assert body["current_stage"] == "COMPLETE"
    assert calls == [
        PipelineStage.OCR,
        PipelineStage.STRUCTURE,
        PipelineStage.RULES,
        PipelineStage.AUDIT_PLAN,
        PipelineStage.ISSUE_LEGAL_CONTEXT,
        PipelineStage.ISSUE_PRIMARY_AUDIT,
        PipelineStage.ISSUE_SECONDARY_REVIEW,
        PipelineStage.ISSUE_REVIEW_REPORT,
    ]
    assert (tmp_path / "jobs" / str(job_id) / "pipeline.json").exists()
    assert body["stages"][0]["stage"] == "INGEST"
    assert body["stages"][0]["state"] == "COMPLETE"
    assert [item["stage"] for item in body["stages"]] == [
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


def test_pipeline_stops_at_missing_deepseek_configuration_and_retry_resumes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    monkeypatch.setattr(pipeline, "_run_ocr_stage", _complete_stage(PipelineStage.OCR))
    monkeypatch.setattr(pipeline, "_run_structure_stage", _complete_stage(PipelineStage.STRUCTURE))
    monkeypatch.setattr(pipeline, "_run_rules_stage", _complete_stage(PipelineStage.RULES))

    def missing_planner(report: PipelineReport) -> None:
        _mark_running(report, PipelineStage.AUDIT_PLAN, "planner")
        raise pipeline._StageWaitingConfiguration(
            PipelineStage.AUDIT_PLAN,
            "DEEPSEEK_NOT_CONFIGURED",
            "DeepSeek API key is not configured.",
        )

    monkeypatch.setattr(pipeline, "_run_audit_plan_stage", missing_planner)
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

    response = client.post(f"/api/documents/{job_id}/pipeline", json={"as_of": "2026-08-17"})
    assert response.status_code == 202
    waiting = _wait(job_id, {"WAITING_CONFIGURATION"})
    assert waiting["current_stage"] == "AUDIT_PLAN"
    assert waiting["failure_code"] == "DEEPSEEK_NOT_CONFIGURED"
    assert waiting["progress_percent"] == 48

    monkeypatch.setattr(pipeline, "_run_audit_plan_stage", _complete_stage(PipelineStage.AUDIT_PLAN))
    retry = client.post(f"/api/documents/{job_id}/pipeline/retry")
    assert retry.status_code == 202
    completed = _wait(job_id, {"COMPLETE"})
    assert completed["progress_percent"] == 100


def test_pipeline_get_is_read_only_and_never_calls_model_functions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    now = pipeline._now()
    report = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.WAITING_CONFIGURATION,
        current_stage=PipelineStage.AUDIT_PLAN,
        progress_percent=48,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        failure_code="DEEPSEEK_NOT_CONFIGURED",
        failure_detail="not configured",
        stages=pipeline._initial_stages(),
    )
    pipeline._persist(report)

    def forbidden(*args, **kwargs):
        raise AssertionError("polling must not execute a provider or pipeline stage")

    monkeypatch.setattr(pipeline, "run_audit_planner", forbidden)
    monkeypatch.setattr(pipeline, "run_issue_primary_audit", forbidden)
    monkeypatch.setattr(pipeline, "run_issue_secondary_review", forbidden)

    response = client.get(f"/api/documents/{job_id}/pipeline")
    assert response.status_code == 200
    assert response.json()["status"] == "WAITING_CONFIGURATION"


def test_structure_stage_reuses_valid_existing_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)
    job_contract_path(job_id).write_text("{}", encoding="utf-8")

    import app.pipeline as pipeline

    monkeypatch.setattr(pipeline, "load_contract_structure", lambda _: SimpleNamespace(job_id=job_id))

    def forbidden_build(*args, **kwargs):
        raise AssertionError("valid existing contract artifact must be reused")

    monkeypatch.setattr(pipeline, "build_contract_structure", forbidden_build)
    now = pipeline._now()
    report = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.RUNNING,
        current_stage=PipelineStage.STRUCTURE,
        progress_percent=25,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        stages=pipeline._initial_stages(),
    )
    pipeline._persist(report)

    _run_structure_stage(report)
    record = next(item for item in report.stages if item.stage == PipelineStage.STRUCTURE)
    assert record.state == PipelineStageState.COMPLETE
    assert record.reused_existing_artifact is True


def test_unknown_job_pipeline_start_does_not_create_empty_job_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    response = client.post(f"/api/documents/{job_id}/pipeline", json={"as_of": "2026-08-17"})
    assert response.status_code == 404
    assert not (tmp_path / "jobs" / str(job_id)).exists()


def test_stage12c_scheduler_limits_are_explicit_and_bounded() -> None:
    import app.pipeline as pipeline

    assert pipeline.PIPELINE_MAX_WORKERS == 4
    assert pipeline.LOCAL_STAGE_CONCURRENCY == 2
    assert pipeline.OCR_STAGE_CONCURRENCY == 1
    assert pipeline.EXTERNAL_PROVIDER_CONCURRENCY == 2


def test_resource_contention_persists_waiting_worker_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_job(tmp_path, job_id)

    import app.pipeline as pipeline

    now = pipeline._now()
    report = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.RUNNING,
        current_stage=PipelineStage.STRUCTURE,
        progress_percent=25,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        stages=pipeline._initial_stages(),
    )
    pipeline._persist(report)

    semaphore = threading.Semaphore(0)
    acquired = threading.Event()

    def wait_for_slot() -> None:
        pipeline._acquire_resource(report, PipelineStage.STRUCTURE, semaphore, "等待本地处理名额。")
        acquired.set()
        semaphore.release()

    worker = threading.Thread(target=wait_for_slot)
    worker.start()
    waiting = _wait(job_id, {"WAITING_WORKER"})
    assert waiting["current_stage"] == "STRUCTURE"
    assert waiting["failure_code"] is None
    stage = next(item for item in waiting["stages"] if item["stage"] == "STRUCTURE")
    assert stage["state"] == "WAITING"
    assert "等待本地处理名额" in stage["detail"]

    semaphore.release()
    worker.join(timeout=1)
    assert acquired.is_set()
