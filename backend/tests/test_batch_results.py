from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.ai_audit_models import AiAuditFinding, EvidenceSufficiency, FindingSeverity, FindingState
from app.batch_results import create_batch, register_batch_job, summarize_batch, summarize_latest_batch
from app.batch_results_models import BatchJobState
from app.main import app
from app.models import DocumentInspection, DocumentKind, DocumentRoute, PageEvidence, PageRoute, SourceMethod
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStageRecord, PipelineStageState, PipelineStatus
from app.review_comparison_models import AgentFollowUpDecision, OverallComparisonState, ReviewComparisonReport
from app.review_report import ReviewReport
from app.review_workflow import Stage9cWorkflowState

client = TestClient(app)


def _write_document(root: Path, job_id, filename: str) -> None:
    job_dir = root / "jobs" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    page = PageEvidence(
        evidence_id=f"evidence:{job_id}:p1",
        page_number=1,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text="synthetic contract",
        character_count=18,
        non_whitespace_count=17,
        meaningful_ratio=1.0,
        suspicious_character_count=0,
        route=PageRoute.NATIVE_TEXT_USABLE,
        route_reason="synthetic",
        source_locator="page:1",
    )
    document = DocumentInspection(
        job_id=job_id,
        filename=filename,
        media_type="application/pdf",
        document_kind=DocumentKind.PDF,
        page_count=1,
        route=DocumentRoute.NATIVE_TEXT,
        native_text_pages=1,
        ocr_required_pages=0,
        pages=[page],
    )
    payload = document.model_dump(mode="json")
    payload.pop("pages")
    (job_dir / "document.json").write_text(__import__("json").dumps(payload), encoding="utf-8")
    (job_dir / "evidence.json").write_text(__import__("json").dumps([page.model_dump(mode="json")]), encoding="utf-8")


def _write_pipeline(root: Path, job_id, status: PipelineStatus, progress: int, *, failure_code=None) -> None:
    now = datetime.now(timezone.utc)
    report = PipelineReport(
        job_id=job_id,
        status=status,
        current_stage=PipelineStage.COMPLETE if status == PipelineStatus.COMPLETE else PipelineStage.PRIMARY_AUDIT,
        progress_percent=progress,
        as_of=date(2026, 8, 17),
        started_at=now,
        updated_at=now,
        completed_at=now if status == PipelineStatus.COMPLETE else None,
        failure_code=failure_code,
        failure_detail="synthetic failure" if failure_code else None,
        stages=[
            PipelineStageRecord(
                stage=PipelineStage.INGEST,
                state=PipelineStageState.COMPLETE,
                label="文件已接收",
                progress_percent=10,
            )
        ],
    )
    (root / "jobs" / str(job_id) / "pipeline.json").write_text(report.model_dump_json(), encoding="utf-8")


def _write_review(root: Path, job_id) -> None:
    finding = AiAuditFinding(
        finding_id="finding-high",
        state=FindingState.SUPPORTED_FINDING,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        risk_category="违约责任",
        severity=FindingSeverity.HIGH,
        title="synthetic high risk",
        reasoning_summary="synthetic",
        suggestion="review",
        issue_ids=[],
        canonical_object_ids=[],
        contract_evidence_ids=[],
        legal_evidence_ids=[],
        review_reasons=[],
    )
    comparison = ReviewComparisonReport(
        job_id=str(job_id),
        primary_context_fingerprint="p",
        secondary_context_fingerprint="s",
        finding_comparisons=[],
        omission_comparisons=[],
        overall_state=OverallComparisonState.MATERIAL_DISAGREEMENT,
        follow_up=AgentFollowUpDecision.FOLLOW_UP_REQUIRED,
        follow_up_reasons=["synthetic"],
    )
    report = ReviewReport(
        job_id=job_id,
        as_of="2026-08-17",
        final_state=Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED,
        primary_provider="fake",
        primary_model="fake-primary",
        secondary_provider="fake",
        secondary_model="fake-secondary",
        primary_external_call_occurred=False,
        secondary_external_call_occurred=False,
        primary_findings=[finding],
        secondary_reviews=[],
        possible_primary_omissions=[],
        comparison=comparison,
    )
    (root / "jobs" / str(job_id) / "review-report.json").write_text(report.model_dump_json(), encoding="utf-8")


def test_batch_persists_jobs_and_recent_pointer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    first = create_batch()
    second = create_batch()
    job_id = uuid4()
    _write_document(tmp_path, job_id, "合同A.pdf")

    register_batch_job(second.batch_id, job_id)
    register_batch_job(second.batch_id, job_id)

    summary = summarize_latest_batch()
    assert summary is not None
    assert summary.batch_id == second.batch_id
    assert summary.total_jobs == 1
    assert summary.jobs[0].filename == "合同A.pdf"
    assert first.batch_id != second.batch_id
    serialized = (tmp_path / "batches" / f"{second.batch_id}.json").read_text(encoding="utf-8")
    assert "合同A" not in serialized


def test_empty_new_batch_does_not_hide_last_useful_batch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    useful = create_batch()
    job_id = uuid4()
    _write_document(tmp_path, job_id, "useful.pdf")
    register_batch_job(useful.batch_id, job_id)

    empty = create_batch()
    assert empty.job_ids == []

    recent = summarize_latest_batch()
    assert recent is not None
    assert recent.batch_id == useful.batch_id
    assert recent.total_jobs == 1


def test_batch_result_prioritizes_human_review_and_high_risk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    batch = create_batch()
    safe_job = uuid4()
    risky_job = uuid4()
    for job_id, filename in ((safe_job, "B合同.pdf"), (risky_job, "A合同.pdf")):
        _write_document(tmp_path, job_id, filename)
        _write_pipeline(tmp_path, job_id, PipelineStatus.COMPLETE, 100)
        register_batch_job(batch.batch_id, job_id)

    _write_review(tmp_path, risky_job)
    _write_review(tmp_path, safe_job)
    safe_report_path = tmp_path / "jobs" / str(safe_job) / "review-report.json"
    safe_payload = ReviewReport.model_validate_json(safe_report_path.read_text(encoding="utf-8"))
    safe_payload.final_state = Stage9cWorkflowState.DUAL_MODEL_AGREEMENT
    safe_payload.primary_findings = []
    safe_payload.comparison.overall_state = OverallComparisonState.AGREEMENT
    safe_payload.comparison.follow_up = AgentFollowUpDecision.NOT_REQUIRED
    safe_report_path.write_text(safe_payload.model_dump_json(), encoding="utf-8")

    summary = summarize_batch(batch.batch_id)
    assert summary.complete_jobs == 2
    assert summary.human_review_required_jobs == 1
    assert summary.jobs[0].job_id == risky_job
    assert summary.jobs[0].finding_counts.high == 1
    assert summary.jobs[0].material_disagreement is True
    assert summary.jobs[0].human_review_required is True
    assert summary.jobs[1].needs_attention is False


def test_batch_exposes_waiting_and_failed_without_affecting_other_jobs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    batch = create_batch()
    waiting_job = uuid4()
    failed_job = uuid4()
    for job_id, filename in ((waiting_job, "waiting.pdf"), (failed_job, "failed.pdf")):
        _write_document(tmp_path, job_id, filename)
        register_batch_job(batch.batch_id, job_id)
    _write_pipeline(tmp_path, waiting_job, PipelineStatus.WAITING_CONFIGURATION, 55, failure_code="DEEPSEEK_NOT_CONFIGURED")
    _write_pipeline(tmp_path, failed_job, PipelineStatus.FAILED, 45, failure_code="STRUCTURE_FAILED")

    summary = summarize_batch(batch.batch_id)
    states = {item.job_id: item.state for item in summary.jobs}
    assert states[waiting_job] == BatchJobState.WAITING
    assert states[failed_job] == BatchJobState.FAILED
    assert summary.waiting_jobs == 1
    assert summary.failed_jobs == 1


def test_batch_summary_does_not_create_phantom_job_directory_for_bad_manifest_entry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    batch = create_batch()
    missing_job = uuid4()
    manifest_path = tmp_path / "batches" / f"{batch.batch_id}.json"
    payload = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    payload["job_ids"] = [str(missing_job)]
    manifest_path.write_text(__import__("json").dumps(payload), encoding="utf-8")

    summary = summarize_batch(batch.batch_id)
    assert summary.jobs[0].state == BatchJobState.INVALID
    assert not (tmp_path / "jobs" / str(missing_job)).exists()


def test_provider_configuration_cors_allows_put_and_delete() -> None:
    response = client.options(
        "/api/config/providers",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
