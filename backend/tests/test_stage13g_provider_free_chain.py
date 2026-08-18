from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.audit_plan_models import AuditPlanningCoverageState
from app.audit_planner import load_audit_plan, run_audit_planner
from app.audit_planner_provider import FakeAuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.issue_legal_context import build_issue_legal_context
from app.issue_primary_audit import run_issue_primary_audit
from app.issue_primary_audit_models import IssuePrimaryAuditState
from app.issue_review_report import IssueReviewReportStaleError, build_issue_review_report, load_issue_review_report
from app.issue_review_report_models import IssueReviewFinalState
from app.issue_secondary_review import run_issue_secondary_review
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.main import app
from app.models import DocumentKind, DocumentRoute, PageEvidence, PageRoute, SourceMethod
from app.pipeline_control import set_provider_mode
from app.pipeline_control_models import ProviderExecutionMode
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
        extractor_id="stage13g-provider-free-fixture",
        confidence=ExtractionConfidence.HIGH,
    )
    text = (
        "本条为甲方预先拟定条款。乙方逾期履行的，应按合同总金额的50%支付违约金；"
        "甲方对该责任限制条款负有提示说明义务。"
    )
    quote = f"第八条 违约责任\n{text}"
    span = SourceSpan(
        page_number=2,
        evidence_ids=["evidence-stage13g-clause-8"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )
    return CanonicalContract(
        job_id=job_id,
        filename="stage13g-provider-free-fixture.pdf",
        source_fingerprint="stage13g-provider-free-source",
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
            raise AssertionError("Stage 13G provider-free regression attempted outbound HTTP.")

    monkeypatch.setattr(httpx, "Client", ForbiddenHttpClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenHttpClient)


def _seed_workspace_source(tmp_path: Path, contract: CanonicalContract) -> None:
    job_dir = tmp_path / "jobs" / str(contract.job_id)
    upload_dir = tmp_path / "uploads" / str(contract.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    quote = contract.clauses[0].source_spans[0].quote
    page = PageEvidence(
        evidence_id="evidence-stage13g-clause-8",
        page_number=2,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text=quote,
        character_count=len(quote),
        non_whitespace_count=len("".join(quote.split())),
        meaningful_ratio=1.0,
        suspicious_character_count=0,
        route=PageRoute.NATIVE_TEXT_USABLE,
        route_reason="provider-free workspace fixture",
        source_locator="source.pdf#page=2",
    )
    document = {
        "job_id": str(contract.job_id),
        "filename": contract.filename,
        "media_type": "application/pdf",
        "document_kind": DocumentKind.PDF.value,
        "page_count": 2,
        "route": DocumentRoute.NATIVE_TEXT.value,
        "native_text_pages": 2,
        "ocr_required_pages": 0,
        "status": "inspected",
    }
    (job_dir / "document.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "evidence.json").write_text(
        json.dumps([page.model_dump(mode="json")], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\n% stage13g workspace fixture\n")


def _prepare_runtime(tmp_path: Path, monkeypatch) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_ISSUE_SECONDARY", "1")
    _forbid_network(monkeypatch)

    contract = _contract()
    _seed_workspace_source(tmp_path, contract)
    job_contract_path(contract.job_id).write_text(
        contract.model_dump_json(indent=2),
        encoding="utf-8",
    )
    run_audit_rules(contract.job_id)

    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(
        repo_root / "legal_data" / "seed" / "manifest.json",
        legal_db_path(),
        rebuild=True,
    )
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    return contract


def _run_provider_free_chain(tmp_path: Path, monkeypatch):
    contract = _prepare_runtime(tmp_path, monkeypatch)
    job_id = contract.job_id

    plan = run_audit_planner(job_id, provider=FakeAuditPlannerProvider())
    legal_context = build_issue_legal_context(
        job_id,
        as_of=date(2026, 8, 18),
        use_semantic=False,
    )
    primary = run_issue_primary_audit(job_id, provider_name="fake")
    secondary = run_issue_secondary_review(job_id, provider_name="fake")
    report = build_issue_review_report(job_id)

    return contract, plan, legal_context, primary, secondary, report


def test_stage13g_provider_free_chain_is_complete_and_one_to_one(tmp_path: Path, monkeypatch) -> None:
    contract, plan, legal_context, primary, secondary, report = _run_provider_free_chain(
        tmp_path,
        monkeypatch,
    )
    job_id = contract.job_id

    plan_ids = [item.issue_id for item in plan.issues]
    legal_ids = [item.issue_id for item in legal_context.issues]
    primary_ids = [item.issue_id for item in primary.results]
    secondary_ids = [item.issue_id for item in secondary.results]
    comparison_ids = [item.issue_id for item in report.comparisons]

    assert plan.coverage_complete is True
    assert len(plan.coverage) == 1
    assert len({item.canonical_object_id for item in plan.coverage}) == len(plan.coverage)
    assert all(
        item.state
        in {
            AuditPlanningCoverageState.REVIEWED_WITH_ISSUE,
            AuditPlanningCoverageState.REVIEWED_NO_SPECIFIC_ISSUE,
        }
        for item in plan.coverage
    )
    assert len(plan_ids) == len(set(plan_ids))
    assert plan_ids == legal_ids == primary_ids == secondary_ids == comparison_ids
    assert report.issue_coverage_complete is True
    assert report.total_issue_count == len(plan_ids)
    assert report.compared_issue_count == len(plan_ids)
    assert report.summary.total_issue_count == len(plan_ids)

    assert plan.provider == "fake"
    assert primary.provider == "fake"
    assert secondary.provider == "fake"
    assert report.primary_provider == "fake"
    assert report.secondary_provider == "fake"

    assert any(package.legal_evidence for package in legal_context.issues)
    assert any(
        result.state == IssuePrimaryAuditState.SUPPORTED_FINDING
        and result.contract_evidence_ids
        and result.legal_evidence_ids
        for result in primary.results
    )
    assert report.final_state == IssueReviewFinalState.HUMAN_REVIEW_REQUIRED
    assert report.summary.human_review_required_count > 0

    assert job_audit_plan_path(job_id).exists()
    assert job_issue_legal_context_path(job_id).exists()
    assert job_issue_primary_audit_path(job_id).exists()
    assert job_issue_secondary_review_path(job_id).exists()
    assert job_issue_review_report_path(job_id).exists()

    assert not job_ai_audit_path(job_id).exists()
    assert not job_secondary_review_path(job_id).exists()
    assert not job_review_report_path(job_id).exists()

    persisted = load_issue_review_report(job_id)
    assert persisted.artifact_fingerprint == report.artifact_fingerprint


def test_stage13g_provider_free_workspace_reads_issue_chain_without_provider_work(tmp_path: Path, monkeypatch) -> None:
    contract, plan, legal_context, primary, secondary, report = _run_provider_free_chain(tmp_path, monkeypatch)
    job_id = contract.job_id

    summary_response = client.get(f"/api/documents/{job_id}/workspace")
    assert summary_response.status_code == 200, summary_response.text
    summary = summary_response.json()
    assert summary["architecture"] == "ISSUE_V1"
    assert summary["overall_state"] == "HUMAN_REVIEW_REQUIRED"
    assert summary["coverage"]["coverage_complete"] is True
    assert summary["coverage"]["canonical_object_count"] == len(plan.coverage)
    assert summary["coverage"]["issue_count"] == len(plan.issues)
    assert summary["review"]["primary_completed_issue_count"] == primary.completed_issue_count
    assert summary["review"]["secondary_completed_issue_count"] == secondary.completed_issue_count
    assert summary["review"]["compared_issue_count"] == report.compared_issue_count
    assert len(summary["issues"]) == len(plan.issues)
    assert [item["issue_id"] for item in summary["issues"]] == [item.issue_id for item in plan.issues]

    stage_map = {item["stage"]: item for item in summary["stages"]}
    assert stage_map["13B/C"]["state"] == "READY"
    assert stage_map["13D"]["state"] == "READY"
    assert stage_map["13E"]["state"] == "READY"
    assert stage_map["13F"]["state"] == "READY"
    assert stage_map["13G"]["state"] == "READY"

    issue_id = plan.issues[0].issue_id
    detail_response = client.get(f"/api/documents/{job_id}/workspace/issues/{issue_id}")
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["issue_id"] == issue_id
    assert detail["plan_issue"]["issue_id"] == issue_id
    assert detail["primary"]["issue_id"] == issue_id
    assert detail["secondary"]["issue_id"] == issue_id
    assert detail["comparison"]["issue_id"] == issue_id
    assert detail["legal_support_state"] == legal_context.issues[0].support_state.value


def test_stage13g_provider_free_report_becomes_stale_when_plan_changes(tmp_path: Path, monkeypatch) -> None:
    contract, _, _, _, _, report = _run_provider_free_chain(tmp_path, monkeypatch)
    job_id = contract.job_id

    plan = load_audit_plan(job_id)
    plan.contract_type_reasoning = "changed after the complete provider-free chain"
    job_audit_plan_path(job_id).write_text(
        plan.model_dump_json(indent=2),
        encoding="utf-8",
    )

    with pytest.raises(IssueReviewReportStaleError):
        load_issue_review_report(job_id)

    historical = load_issue_review_report(job_id, validate_freshness=False)
    assert historical.artifact_fingerprint == report.artifact_fingerprint
