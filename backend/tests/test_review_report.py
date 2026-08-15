from __future__ import annotations

from datetime import date
from uuid import uuid4

import app.review_report as review_report_module
from app.ai_audit_models import (
    AiAuditFinding,
    AiAuditReport,
    EvidenceSufficiency,
    FindingSeverity,
    FindingState,
)
from app.review_comparison_models import (
    AgentFollowUpDecision,
    OverallComparisonState,
    ReviewComparisonReport,
)
from app.review_report import build_review_report, load_review_report
from app.review_workflow import Stage9cWorkflowResult, Stage9cWorkflowState
from app.secondary_review_models import SecondaryReviewReport
from app.storage import job_review_report_path


def _reports():
    job_id = uuid4()
    finding = AiAuditFinding(
        finding_id="finding-001",
        state=FindingState.SUPPORTED_FINDING,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        risk_category="违约金",
        severity=FindingSeverity.MEDIUM,
        title="测试发现",
        reasoning_summary="测试理由。",
        suggestion="人工复核。",
        issue_ids=["issue-001"],
        canonical_object_ids=["clause-001"],
        contract_evidence_ids=["E-1"],
        legal_evidence_ids=["L-1"],
    )
    primary = AiAuditReport(
        job_id=job_id,
        as_of=date(2026, 8, 15),
        provider="deepseek",
        model="deepseek-v4-pro",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        context_fingerprint="context-fp",
        raw_response_hash="a" * 64,
        findings=[finding],
        supplied_contract_evidence_ids=["E-1"],
        supplied_legal_evidence_ids=["L-1"],
    )
    secondary = SecondaryReviewReport(
        job_id=job_id,
        as_of=primary.as_of,
        primary_provider=primary.provider,
        primary_model=primary.model,
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint="secondary-fp",
        provider="kimi",
        model="kimi-k3",
        raw_response_hash="b" * 64,
        finding_reviews=[],
        possible_omissions=[],
        supplied_contract_evidence_ids=["E-1"],
        supplied_legal_evidence_ids=["L-1"],
    )
    comparison = ReviewComparisonReport(
        job_id=str(job_id),
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint=secondary.secondary_context_fingerprint,
        finding_comparisons=[],
        omission_comparisons=[],
        overall_state=OverallComparisonState.AGREEMENT,
        follow_up=AgentFollowUpDecision.NOT_REQUIRED,
    )
    workflow = Stage9cWorkflowResult(
        job_id=job_id,
        state=Stage9cWorkflowState.DUAL_MODEL_AGREEMENT,
        comparison=comparison,
        plan_state="NOT_REQUIRED",
    )
    return primary, secondary, workflow


def test_review_report_is_persisted_and_loaded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    primary, secondary, workflow = _reports()
    monkeypatch.setattr(review_report_module, "load_ai_audit_report", lambda job_id: primary)
    monkeypatch.setattr(review_report_module, "load_secondary_review_report", lambda job_id: secondary)
    monkeypatch.setattr(review_report_module, "run_stage9c_workflow", lambda job_id: workflow)

    report = build_review_report(primary.job_id)
    loaded = load_review_report(primary.job_id)

    assert report.model_dump(mode="json") == loaded.model_dump(mode="json")
    assert job_review_report_path(primary.job_id).exists()
    assert report.primary_external_call_occurred is True
    assert report.secondary_external_call_occurred is True
    assert report.primary_provider == "deepseek"
    assert report.secondary_provider == "kimi"
    assert report.final_state == Stage9cWorkflowState.DUAL_MODEL_AGREEMENT
