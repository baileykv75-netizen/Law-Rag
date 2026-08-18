from __future__ import annotations

from uuid import uuid4

import pytest

from app.ai_audit_models import FindingSeverity
from app.audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ReviewPriority,
)
from app.issue_primary_audit_models import (
    IssueEvidenceSufficiency,
    IssuePrimaryAuditArtifact,
    IssuePrimaryAuditResult,
    IssuePrimaryAuditState,
    IssuePrimaryAuditStatus,
)
from app.issue_review_comparison import compare_issue
from app.issue_review_report import (
    IssueReviewReportStaleError,
    IssueReviewReportValidationError,
    build_issue_review_report,
    load_issue_review_report,
)
from app.issue_review_report_models import (
    IssueReviewComparisonState,
    IssueReviewFinalState,
)
from app.issue_secondary_review_models import (
    IssueSecondaryReviewArtifact,
    IssueSecondaryReviewResult,
    IssueSecondaryReviewStatus,
    SecondaryCoverageAssessment,
    SecondaryIssueAssessment,
)
from app.main import app


def _plan_issue(issue_id: str, topic: str | None = None) -> AuditPlanIssue:
    return AuditPlanIssue(
        issue_id=issue_id,
        topic=topic or f"topic-{issue_id}",
        priority=ReviewPriority.IMPORTANT,
        sources=[AuditPlanSource.BASELINE],
        why_review=["fixture"],
        questions=["是否存在风险？"],
        retrieval_queries=["fixture legal query"],
    )


def _primary_result(
    issue: AuditPlanIssue,
    *,
    state: IssuePrimaryAuditState = IssuePrimaryAuditState.SUPPORTED_FINDING,
    severity: FindingSeverity = FindingSeverity.MEDIUM,
) -> IssuePrimaryAuditResult:
    return IssuePrimaryAuditResult(
        issue_id=issue.issue_id,
        topic=issue.topic,
        state=state,
        evidence_sufficiency=IssueEvidenceSufficiency.SUFFICIENT,
        legal_support_state="EVIDENCE_FOUND",
        legal_conclusion=True,
        risk_category=issue.topic,
        severity=severity,
        title=f"primary-{issue.issue_id}",
        reasoning_summary="fixture primary reasoning",
        suggestion="fixture primary suggestion",
        canonical_object_ids=[f"clause-{issue.issue_id}"],
        contract_evidence_ids=[f"contract-{issue.issue_id}"],
        legal_evidence_ids=[f"legal-{issue.issue_id}"],
        review_reasons=[],
        context_fingerprint=f"context-{issue.issue_id}",
    )


def _secondary_result(
    issue: AuditPlanIssue,
    primary: IssuePrimaryAuditResult,
    *,
    assessment: SecondaryIssueAssessment = SecondaryIssueAssessment.SUPPORTED,
    coverage: SecondaryCoverageAssessment = SecondaryCoverageAssessment.COVERED,
    severity: FindingSeverity | None = None,
) -> IssueSecondaryReviewResult:
    return IssueSecondaryReviewResult(
        issue_id=issue.issue_id,
        topic=issue.topic,
        primary_state=primary.state.value,
        assessment=assessment,
        coverage_assessment=coverage,
        severity=severity or primary.severity,
        reasoning_summary="fixture secondary reasoning",
        suggestion="fixture secondary suggestion",
        contract_evidence_ids=primary.contract_evidence_ids,
        legal_evidence_ids=primary.legal_evidence_ids,
        review_reasons=[],
        omission_title="possible omission" if coverage == SecondaryCoverageAssessment.POSSIBLE_OMISSION else None,
        omission_reasoning="fixture omission reasoning" if coverage == SecondaryCoverageAssessment.POSSIBLE_OMISSION else None,
        context_fingerprint=primary.context_fingerprint,
    )


def _fixtures(count: int = 3):
    job_id = uuid4()
    issues = [_plan_issue(f"issue-{index}") for index in range(1, count + 1)]
    plan = AuditPlan(
        job_id=job_id,
        contract_type=ContractType.GENERAL,
        contract_type_confidence=ContractTypeConfidence.HIGH,
        contract_type_reasoning="fixture",
        provider="fixture-planner",
        model="fixture-planner-v1",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        planner_input_fingerprint="planner-input-fp",
        planner_response_hash="planner-output-fp",
        coverage_complete=True,
        issues=issues,
    )
    primary_results = [_primary_result(issue) for issue in issues]
    primary = IssuePrimaryAuditArtifact(
        job_id=job_id,
        status=IssuePrimaryAuditStatus.COMPLETE,
        as_of="2026-08-18",
        provider="deepseek",
        model="deepseek-v4-pro",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        audit_plan_fingerprint="plan-fp",
        issue_legal_context_fingerprint="legal-context-fp",
        total_issue_count=count,
        completed_issue_count=count,
        results=primary_results,
        artifact_fingerprint="primary-artifact-fp",
    )
    secondary_results = [
        _secondary_result(issue, primary_result)
        for issue, primary_result in zip(issues, primary_results, strict=True)
    ]
    secondary = IssueSecondaryReviewArtifact(
        job_id=job_id,
        status=IssueSecondaryReviewStatus.COMPLETE,
        provider="kimi",
        model="kimi-k3",
        audit_plan_fingerprint="plan-fp",
        issue_legal_context_fingerprint="legal-context-fp",
        issue_primary_audit_fingerprint=primary.artifact_fingerprint,
        total_issue_count=count,
        completed_issue_count=count,
        results=secondary_results,
        artifact_fingerprint="secondary-artifact-fp",
    )
    return job_id, plan, primary, secondary


def _patch_upstream(monkeypatch, tmp_path, count: int = 3):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id, plan, primary, secondary = _fixtures(count=count)
    import app.issue_review_report as module

    monkeypatch.setattr(module, "load_audit_plan", lambda _job_id: plan)
    monkeypatch.setattr(module, "load_issue_primary_audit", lambda _job_id: primary)
    monkeypatch.setattr(module, "load_issue_secondary_review", lambda _job_id: secondary)
    return job_id, plan, primary, secondary


def test_stage13g_issue_report_compares_every_planned_issue_once(tmp_path, monkeypatch) -> None:
    job_id, plan, _, _ = _patch_upstream(monkeypatch, tmp_path, count=3)

    report = build_issue_review_report(job_id)

    assert report.status == "COMPLETE"
    assert report.issue_coverage_complete is True
    assert report.compared_issue_count == len(plan.issues)
    assert [item.issue_id for item in report.comparisons] == [item.issue_id for item in plan.issues]
    assert report.summary.consistent_count == 3
    assert report.summary.human_review_required_count == 0
    assert report.final_state == IssueReviewFinalState.NO_MANDATORY_REVIEW


@pytest.mark.parametrize(
    ("primary_state", "secondary_assessment", "coverage", "secondary_severity", "expected"),
    [
        (
            IssuePrimaryAuditState.SUPPORTED_FINDING,
            SecondaryIssueAssessment.PARTIALLY_SUPPORTED,
            SecondaryCoverageAssessment.COVERED,
            FindingSeverity.MEDIUM,
            IssueReviewComparisonState.CONSISTENT_WITH_REVIEW,
        ),
        (
            IssuePrimaryAuditState.SUPPORTED_FINDING,
            SecondaryIssueAssessment.DISAGREED,
            SecondaryCoverageAssessment.COVERED,
            FindingSeverity.MEDIUM,
            IssueReviewComparisonState.MATERIAL_DISAGREEMENT,
        ),
        (
            IssuePrimaryAuditState.SUPPORTED_FINDING,
            SecondaryIssueAssessment.SUPPORTED,
            SecondaryCoverageAssessment.POSSIBLE_OMISSION,
            FindingSeverity.MEDIUM,
            IssueReviewComparisonState.POSSIBLE_OMISSION,
        ),
        (
            IssuePrimaryAuditState.INSUFFICIENT_EVIDENCE,
            SecondaryIssueAssessment.INSUFFICIENT_EVIDENCE,
            SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE,
            FindingSeverity.MEDIUM,
            IssueReviewComparisonState.INSUFFICIENT_EVIDENCE,
        ),
        (
            IssuePrimaryAuditState.REVIEW_REQUIRED,
            SecondaryIssueAssessment.REVIEW_REQUIRED,
            SecondaryCoverageAssessment.COVERED_BUT_QUESTIONABLE,
            FindingSeverity.MEDIUM,
            IssueReviewComparisonState.REVIEW_REQUIRED,
        ),
        (
            IssuePrimaryAuditState.SUPPORTED_FINDING,
            SecondaryIssueAssessment.SUPPORTED,
            SecondaryCoverageAssessment.COVERED,
            FindingSeverity.CRITICAL,
            IssueReviewComparisonState.MATERIAL_DISAGREEMENT,
        ),
    ],
)
def test_stage13g_deterministic_issue_state_mapping(
    primary_state,
    secondary_assessment,
    coverage,
    secondary_severity,
    expected,
) -> None:
    issue = _plan_issue("issue-1")
    primary = _primary_result(issue, state=primary_state, severity=FindingSeverity.MEDIUM)
    secondary = _secondary_result(
        issue,
        primary,
        assessment=secondary_assessment,
        coverage=coverage,
        severity=secondary_severity,
    )

    comparison = compare_issue(issue, primary, secondary)

    assert comparison.overall_state == expected
    assert comparison.requires_human_review is (expected != IssueReviewComparisonState.CONSISTENT)


def test_stage13g_upstream_evidence_limits_promote_consistent_result_to_review() -> None:
    issue = _plan_issue("issue-1")
    primary = _primary_result(issue)
    primary.evidence_sufficiency = IssueEvidenceSufficiency.PARTIAL_LEGAL_CORPUS
    primary.review_reasons = ["PARTIAL_LEGAL_CORPUS"]
    secondary = _secondary_result(issue, primary)

    comparison = compare_issue(issue, primary, secondary)

    assert comparison.overall_state == IssueReviewComparisonState.CONSISTENT_WITH_REVIEW
    assert comparison.requires_human_review is True
    assert "PARTIAL_LEGAL_CORPUS" in comparison.reasons


def test_stage13g_incomplete_planning_coverage_forces_human_review(tmp_path, monkeypatch) -> None:
    job_id, plan, _, _ = _patch_upstream(monkeypatch, tmp_path, count=1)
    plan.coverage_complete = False

    report = build_issue_review_report(job_id)

    assert report.planning_coverage_complete is False
    assert report.final_state == IssueReviewFinalState.HUMAN_REVIEW_REQUIRED
    assert "PLANNING_COVERAGE_INCOMPLETE" in report.final_reasons


def test_stage13g_rejects_duplicate_or_missing_issue_results(tmp_path, monkeypatch) -> None:
    job_id, _, primary, secondary = _patch_upstream(monkeypatch, tmp_path, count=2)
    primary.results = [primary.results[0], primary.results[0]]

    with pytest.raises(IssueReviewReportValidationError, match="duplicate"):
        build_issue_review_report(job_id)

    job_id, _, primary, secondary = _patch_upstream(monkeypatch, tmp_path, count=2)
    secondary.results = secondary.results[:1]
    secondary.completed_issue_count = 1

    with pytest.raises(IssueReviewReportValidationError, match="same issue set"):
        build_issue_review_report(job_id)


def test_stage13g_report_fingerprint_and_freshness(tmp_path, monkeypatch) -> None:
    job_id, _, primary, secondary = _patch_upstream(monkeypatch, tmp_path, count=1)
    report = build_issue_review_report(job_id)

    assert len(report.artifact_fingerprint) == 64
    loaded = load_issue_review_report(job_id, validate_freshness=False)
    assert loaded.artifact_fingerprint == report.artifact_fingerprint

    import app.issue_review_report as module

    changed_secondary = secondary.model_copy(
        update={"artifact_fingerprint": "secondary-artifact-fp-changed"}
    )
    monkeypatch.setattr(module, "load_issue_primary_audit", lambda _job_id: primary)
    monkeypatch.setattr(module, "load_issue_secondary_review", lambda _job_id: changed_secondary)

    with pytest.raises(IssueReviewReportStaleError, match="issue-secondary-review.json changed"):
        load_issue_review_report(job_id)


def test_stage13g_issue_review_report_api_route_is_mounted() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/documents/{job_id}/issue-review-report" in paths
