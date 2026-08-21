from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.audit_planner_provider import FakeAuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import (
    CanonicalContract,
    Clause,
    ExtractionConfidence,
    ExtractionProvenance,
    SourceSpan,
)
from app.issue_primary_audit_provider import FakeIssuePrimaryProvider
from app.issue_review_report import load_issue_review_report
from app.issue_secondary_review_provider import FakeIssueSecondaryReviewProvider
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.main import app
from app.models import SourceMethod
from app.pipeline import _mark_done, _mark_running
from app.pipeline_control import get_pipeline_control
from app.pipeline_models import PipelineReport, PipelineStage
from app.storage import (
    job_ai_audit_path,
    job_audit_plan_path,
    job_contract_path,
    job_issue_legal_context_path,
    job_issue_primary_audit_path,
    job_issue_review_report_path,
    job_issue_secondary_review_path,
    job_review_report_path,
    job_secondary_review_path,
    legal_db_path,
    legal_retrieval_index_path,
)

client = TestClient(app)


def _contract() -> CanonicalContract:
    job_id = uuid4()
    provenance = ExtractionProvenance(
        extractor_id="stage13g-pipeline-fixture",
        confidence=ExtractionConfidence.HIGH,
    )
    text = (
        "本条为甲方预先拟定条款。乙方逾期履行的，应按合同总金额的50%支付违约金；"
        "甲方对该责任限制条款负有提示说明义务。"
    )
    quote = f"第八条 违约责任\n{text}"
    span = SourceSpan(
        page_number=2,
        evidence_ids=["evidence-stage13g-pipeline-clause-8"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )
    return CanonicalContract(
        job_id=job_id,
        filename="stage13g-pipeline-fixture.pdf",
        source_fingerprint="stage13g-pipeline-source",
        evidence_unit_count=1,
        clauses=[
            Clause(
                clause_id="clause-008",
                heading_token="第八条",
                heading_text="违约责任",
                body_text=text,
                level=1,
                page_start=2,
                page_end=2,
                source_spans=[span],
                provenance=provenance,
            )
        ],
    )


def _forbid_network(monkeypatch) -> None:
    class ForbiddenHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Stage 13G production pipeline regression attempted outbound HTTP.")

    monkeypatch.setattr(httpx, "Client", ForbiddenHttpClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenHttpClient)


def _complete_stage(stage: PipelineStage):
    def runner(report: PipelineReport) -> None:
        _mark_running(report, stage, f"fixture running {stage.value}")
        _mark_done(report, stage, detail=f"fixture done {stage.value}", reused=True)

    return runner


def _prepare_runtime(tmp_path: Path, monkeypatch) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_ISSUE_SECONDARY", "1")
    _forbid_network(monkeypatch)

    contract = _contract()
    job_id = contract.job_id
    job_dir = tmp_path / "jobs" / str(job_id)
    upload_dir = tmp_path / "uploads" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "document.json").write_text("{}", encoding="utf-8")
    (job_dir / "evidence.json").write_text("[]", encoding="utf-8")
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\n")

    job_contract_path(job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(job_id)

    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(
        repo_root / "legal_data" / "seed" / "manifest.json",
        legal_db_path(),
        rebuild=True,
    )
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())

    import app.pipeline as pipeline

    # Ingestion/OCR/structure/rules already have focused tests; this regression
    # starts from valid local artifacts so it can exercise the migrated Stage 13 tail.
    monkeypatch.setattr(pipeline, "_run_ocr_stage", _complete_stage(PipelineStage.OCR))
    monkeypatch.setattr(pipeline, "_run_structure_stage", _complete_stage(PipelineStage.STRUCTURE))
    monkeypatch.setattr(pipeline, "_run_rules_stage", _complete_stage(PipelineStage.RULES))
    monkeypatch.setattr(pipeline, "planner_provider_from_name", lambda _: FakeAuditPlannerProvider())
    monkeypatch.setattr(pipeline, "issue_primary_provider_from_name", lambda _: FakeIssuePrimaryProvider())
    monkeypatch.setattr(
        pipeline,
        "issue_secondary_provider_from_name",
        lambda _: FakeIssueSecondaryReviewProvider(),
    )
    return contract


def _wait(job_id, terminal: set[str], timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/documents/{job_id}/pipeline")
        if response.status_code == 200 and response.json()["status"] in terminal:
            return response.json()
        time.sleep(0.02)
    raise AssertionError("Stage 13G production pipeline did not reach the expected state")


def test_new_production_pipeline_runs_authoritative_stage13_chain_without_legacy_reports(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _prepare_runtime(tmp_path, monkeypatch)
    job_id = contract.job_id

    started = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={
            "as_of": "2026-08-18",
            "use_semantic": False,
            "provider_mode": "AUTO_CONTINUE",
        },
    )
    assert started.status_code == 202, started.text

    completed = _wait(job_id, {"COMPLETE"})
    assert completed["progress_percent"] == 100
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
    assert all(item["state"] in {"COMPLETE", "SKIPPED"} for item in completed["stages"])

    assert job_audit_plan_path(job_id).exists()
    assert job_issue_legal_context_path(job_id).exists()
    assert job_issue_primary_audit_path(job_id).exists()
    assert job_issue_secondary_review_path(job_id).exists()
    assert job_issue_review_report_path(job_id).exists()

    # The new production mainline must not recreate Stage 8/9 authoritative artifacts.
    assert not job_ai_audit_path(job_id).exists()
    assert not job_secondary_review_path(job_id).exists()
    assert not job_review_report_path(job_id).exists()

    report = load_issue_review_report(job_id)
    assert report.total_issue_count == report.compared_issue_count
    assert report.issue_coverage_complete is True

    control = get_pipeline_control(job_id)
    assert control.active_provider is None
    assert control.cancel_requested is False


def test_require_approval_pauses_before_first_planner_outbound_and_resumes_same_new_chain(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _prepare_runtime(tmp_path, monkeypatch)
    job_id = contract.job_id

    started = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={
            "as_of": "2026-08-18",
            "use_semantic": False,
            "provider_mode": "REQUIRE_APPROVAL",
        },
    )
    assert started.status_code == 202, started.text

    paused = _wait(job_id, {"PAUSED_BEFORE_PROVIDER"})
    assert paused["current_stage"] == "AUDIT_PLAN"
    assert paused["progress_percent"] == 48
    assert paused["failure_code"] == "PROVIDER_APPROVAL_REQUIRED"
    assert not job_audit_plan_path(job_id).exists()
    assert get_pipeline_control(job_id).active_provider is None

    approved = client.post(f"/api/documents/{job_id}/pipeline/approve-provider")
    assert approved.status_code == 202, approved.text
    completed = _wait(job_id, {"COMPLETE"})
    assert completed["current_stage"] == "COMPLETE"
    assert job_issue_review_report_path(job_id).exists()


def test_unfinished_legacy_pipeline_is_preserved_and_not_silently_migrated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contract = _prepare_runtime(tmp_path, monkeypatch)
    job_id = contract.job_id

    import app.pipeline as pipeline
    from app.pipeline_models import PipelineStageRecord, PipelineStageState, PipelineStatus

    now = pipeline._now()
    legacy = PipelineReport(
        schema_version="1.2.0",
        engine_version="stage13a-1.0.0",
        job_id=job_id,
        status=PipelineStatus.FAILED,
        current_stage=PipelineStage.PRIMARY_AUDIT,
        progress_percent=55,
        as_of=date(2026, 8, 18),
        use_semantic=False,
        started_at=now,
        updated_at=now,
        failure_code="legacy-fixture",
        failure_detail="legacy fixture",
        stages=[
            PipelineStageRecord(
                stage=PipelineStage.PRIMARY_AUDIT,
                state=PipelineStageState.FAILED,
                label="检索法律依据并进行主审",
                progress_percent=75,
            )
        ],
    )
    pipeline._persist(legacy)

    response = client.post(f"/api/documents/{job_id}/pipeline/retry")
    assert response.status_code == 409
    assert "legacy RC2 pipeline" in response.json()["detail"]

    preserved = client.get(f"/api/documents/{job_id}/pipeline")
    assert preserved.status_code == 200
    assert preserved.json()["current_stage"] == "PRIMARY_AUDIT"
    assert preserved.json()["failure_code"] == "legacy-fixture"
