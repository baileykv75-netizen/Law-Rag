from __future__ import annotations

from datetime import date
from uuid import uuid4

import app.review_workflow as workflow
from app.ai_audit_models import (
    AiAuditFinding,
    AiAuditReport,
    EvidenceSufficiency,
    FindingSeverity,
    FindingState,
)
from app.review_comparison_models import AgentActionState
from app.review_workflow import Stage9cWorkflowState, run_stage9c_workflow
from app.secondary_review_models import (
    SecondaryAssessment,
    SecondaryFindingReview,
    SecondaryReviewReport,
)


def _primary(
    *,
    state: FindingState = FindingState.SUPPORTED_FINDING,
    severity: FindingSeverity = FindingSeverity.HIGH,
    contract_ids: list[str] | None = None,
    legal_ids: list[str] | None = None,
) -> AiAuditReport:
    job_id = uuid4()
    finding = AiAuditFinding(
        finding_id="finding-001",
        state=state,
        evidence_sufficiency=(
            EvidenceSufficiency.SUFFICIENT
            if state == FindingState.SUPPORTED_FINDING
            else EvidenceSufficiency.SOURCE_UNCERTAIN
        ),
        risk_category="违约金",
        severity=severity,
        title="测试风险",
        reasoning_summary="主审理由。",
        suggestion="主审建议。",
        issue_ids=["issue-001"],
        canonical_object_ids=["clause-001"],
        contract_evidence_ids=contract_ids if contract_ids is not None else ["E-1"],
        legal_evidence_ids=legal_ids if legal_ids is not None else ["L-1"],
        review_reasons=[],
    )
    return AiAuditReport(
        job_id=job_id,
        as_of=date(2026, 8, 15),
        provider="deepseek",
        model="deepseek-v4-pro",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        context_fingerprint="context-fp",
        raw_response_hash="a" * 64,
        findings=[finding],
        supplied_contract_evidence_ids=finding.contract_evidence_ids,
        supplied_legal_evidence_ids=finding.legal_evidence_ids,
    )


def _secondary(
    primary: AiAuditReport,
    *,
    assessment: SecondaryAssessment = SecondaryAssessment.SUPPORTED,
    severity: FindingSeverity = FindingSeverity.HIGH,
    contract_ids: list[str] | None = None,
    legal_ids: list[str] | None = None,
) -> SecondaryReviewReport:
    finding = primary.findings[0]
    review = SecondaryFindingReview(
        review_id="review-001",
        primary_finding_id=finding.finding_id,
        assessment=assessment,
        severity=severity,
        reasoning_summary="二审理由。",
        suggestion="二审建议。",
        contract_evidence_ids=contract_ids if contract_ids is not None else finding.contract_evidence_ids,
        legal_evidence_ids=legal_ids if legal_ids is not None else finding.legal_evidence_ids,
        disagreement_categories=[],
        review_reasons=[],
    )
    return SecondaryReviewReport(
        job_id=primary.job_id,
        as_of=primary.as_of,
        primary_provider=primary.provider,
        primary_model=primary.model,
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint="secondary-fp",
        provider="kimi",
        model="kimi-k3",
        raw_response_hash="b" * 64,
        finding_reviews=[review],
        supplied_contract_evidence_ids=sorted(set(primary.supplied_contract_evidence_ids) | set(review.contract_evidence_ids)),
        supplied_legal_evidence_ids=sorted(set(primary.supplied_legal_evidence_ids) | set(review.legal_evidence_ids)),
    )


def _patch_reports(monkeypatch, primary: AiAuditReport, secondary: SecondaryReviewReport) -> None:
    monkeypatch.setattr(workflow, "load_ai_audit_report", lambda job_id: primary)
    monkeypatch.setattr(workflow, "load_secondary_review_report", lambda job_id: secondary)


def test_dual_model_agreement_finishes_without_agent(monkeypatch) -> None:
    primary = _primary()
    secondary = _secondary(primary)
    _patch_reports(monkeypatch, primary, secondary)

    result = run_stage9c_workflow(primary.job_id)

    assert result.state == Stage9cWorkflowState.DUAL_MODEL_AGREEMENT
    assert result.executed_actions == []
    assert result.evidence_gathered is False


def test_one_level_severity_difference_finishes_without_agent(monkeypatch) -> None:
    primary = _primary(severity=FindingSeverity.HIGH)
    secondary = _secondary(primary, severity=FindingSeverity.MEDIUM)
    _patch_reports(monkeypatch, primary, secondary)

    result = run_stage9c_workflow(primary.job_id)

    assert result.state == Stage9cWorkflowState.MINOR_DISAGREEMENT
    assert result.executed_actions == []


def test_material_disagreement_runs_bounded_local_action_then_requires_human(monkeypatch) -> None:
    primary = _primary()
    secondary = _secondary(primary, assessment=SecondaryAssessment.NOT_SUPPORTED)
    _patch_reports(monkeypatch, primary, secondary)

    calls = []

    def fake_execute(job_id, action, *, as_of):
        calls.append((job_id, action.tool_name.value, action.cycle, as_of))
        finished = action.model_copy(deep=True)
        finished.state = AgentActionState.COMPLETED
        finished.output_evidence_ids = list(action.input_evidence_ids)
        finished.result_payload = {"test": "evidence gathered"}
        return finished

    monkeypatch.setattr(workflow, "execute_agent_action", fake_execute)

    result = run_stage9c_workflow(primary.job_id)

    assert result.state == Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED
    assert len(calls) == 1
    assert calls[0][2] == 1
    assert result.evidence_gathered is True
    assert "NO_AUTOMATIC_THIRD_MODEL_ARBITRATION" in result.final_reasons


def test_evidence_uncertainty_without_grounded_evidence_target_fails_to_human_review(monkeypatch) -> None:
    primary = _primary(
        state=FindingState.INSUFFICIENT_EVIDENCE,
        contract_ids=[],
        legal_ids=[],
    )
    secondary = _secondary(
        primary,
        assessment=SecondaryAssessment.SUPPORTED,
        contract_ids=[],
        legal_ids=[],
    )
    _patch_reports(monkeypatch, primary, secondary)

    result = run_stage9c_workflow(primary.job_id)

    assert result.state == Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED
    assert result.executed_actions == []
    assert result.evidence_gathered is False
