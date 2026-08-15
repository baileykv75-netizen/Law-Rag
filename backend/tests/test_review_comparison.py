from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.ai_audit_models import (
    AiAuditFinding,
    AiAuditReport,
    EvidenceSufficiency,
    FindingSeverity,
    FindingState,
)
from app.review_comparison import (
    compare_evidence_sets,
    compare_finding,
    compare_review_reports,
    compare_risk_state,
    compare_severity,
)
from app.review_comparison_models import (
    AgentFollowUpDecision,
    EvidenceSetComparisonState,
    OverallComparisonState,
    RiskComparisonState,
    SeverityComparisonState,
)
from app.secondary_review_models import (
    SecondaryAssessment,
    SecondaryFindingReview,
    SecondaryPossibleOmission,
    SecondaryReviewReport,
)


def _primary_finding(
    *,
    finding_id: str = "finding-001",
    state: FindingState = FindingState.SUPPORTED_FINDING,
    severity: FindingSeverity = FindingSeverity.HIGH,
    contract_ids: list[str] | None = None,
    legal_ids: list[str] | None = None,
) -> AiAuditFinding:
    return AiAuditFinding(
        finding_id=finding_id,
        state=state,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        risk_category="违约金",
        severity=severity,
        title="违约金风险",
        reasoning_summary="测试主审理由。",
        suggestion="测试建议。",
        issue_ids=["issue-001"],
        canonical_object_ids=["clause-001"],
        contract_evidence_ids=contract_ids if contract_ids is not None else ["E-1", "E-2"],
        legal_evidence_ids=legal_ids if legal_ids is not None else ["L-585"],
        review_reasons=[],
    )


def _secondary_review(
    *,
    finding_id: str = "finding-001",
    assessment: SecondaryAssessment = SecondaryAssessment.SUPPORTED,
    severity: FindingSeverity = FindingSeverity.HIGH,
    contract_ids: list[str] | None = None,
    legal_ids: list[str] | None = None,
) -> SecondaryFindingReview:
    return SecondaryFindingReview(
        review_id="review-001",
        primary_finding_id=finding_id,
        assessment=assessment,
        severity=severity,
        reasoning_summary="测试二审理由。",
        suggestion="测试建议。",
        contract_evidence_ids=contract_ids if contract_ids is not None else ["E-1", "E-2"],
        legal_evidence_ids=legal_ids if legal_ids is not None else ["L-585"],
        disagreement_categories=[],
        review_reasons=[],
    )


def _primary_report(findings: list[AiAuditFinding]) -> AiAuditReport:
    return AiAuditReport(
        job_id=uuid4(),
        as_of=date(2026, 8, 15),
        provider="deepseek",
        model="deepseek-v4-pro",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        context_fingerprint="context-fp",
        raw_response_hash="a" * 64,
        findings=findings,
        warnings=[],
        supplied_legal_evidence_ids=sorted({item for f in findings for item in f.legal_evidence_ids}),
        supplied_contract_evidence_ids=sorted({item for f in findings for item in f.contract_evidence_ids}),
    )


def _secondary_report(primary: AiAuditReport, reviews: list[SecondaryFindingReview], omissions=None) -> SecondaryReviewReport:
    return SecondaryReviewReport(
        job_id=primary.job_id,
        as_of=primary.as_of,
        primary_provider=primary.provider,
        primary_model=primary.model,
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint="secondary-context-fp",
        provider="kimi",
        model="kimi-k3",
        raw_response_hash="b" * 64,
        finding_reviews=reviews,
        possible_omissions=omissions or [],
        warnings=[],
        supplied_contract_evidence_ids=primary.supplied_contract_evidence_ids,
        supplied_legal_evidence_ids=primary.supplied_legal_evidence_ids,
    )


def test_risk_state_truth_table_has_material_risk_conflict() -> None:
    assert compare_risk_state(
        FindingState.SUPPORTED_FINDING,
        SecondaryAssessment.SUPPORTED,
    ) == RiskComparisonState.AGREE_SUPPORTED
    assert compare_risk_state(
        FindingState.SUPPORTED_FINDING,
        SecondaryAssessment.NOT_SUPPORTED,
    ) == RiskComparisonState.DISAGREE_RISK_EXISTS
    assert compare_risk_state(
        FindingState.SUPPORTED_FINDING,
        SecondaryAssessment.REVIEW_REQUIRED,
    ) == RiskComparisonState.DISAGREE_EVIDENCE_SUFFICIENCY


def test_severity_distance_is_ordinal_and_deterministic() -> None:
    minor = compare_severity(FindingSeverity.HIGH, FindingSeverity.MEDIUM)
    material = compare_severity(FindingSeverity.CRITICAL, FindingSeverity.LOW)

    assert minor.distance == 1
    assert minor.state == SeverityComparisonState.MINOR_DISAGREEMENT
    assert material.distance == 3
    assert material.state == SeverityComparisonState.MATERIAL_DISAGREEMENT


def test_evidence_set_comparison_preserves_shared_and_side_only_ids() -> None:
    result = compare_evidence_sets(["E-1", "E-2"], ["E-2", "E-3"])

    assert result.state == EvidenceSetComparisonState.PARTIAL_OVERLAP
    assert result.shared == ["E-2"]
    assert result.primary_only == ["E-1"]
    assert result.secondary_only == ["E-3"]


def test_one_step_severity_difference_is_minor_and_does_not_trigger_agent() -> None:
    result = compare_finding(
        _primary_finding(severity=FindingSeverity.HIGH),
        _secondary_review(severity=FindingSeverity.MEDIUM),
    )

    assert result.risk_state == RiskComparisonState.AGREE_SUPPORTED
    assert result.overall_state == OverallComparisonState.MINOR_DISAGREEMENT
    assert result.follow_up == AgentFollowUpDecision.NOT_REQUIRED


def test_risk_existence_conflict_is_material_and_triggers_follow_up() -> None:
    result = compare_finding(
        _primary_finding(state=FindingState.SUPPORTED_FINDING),
        _secondary_review(assessment=SecondaryAssessment.NOT_SUPPORTED),
    )

    assert result.overall_state == OverallComparisonState.MATERIAL_DISAGREEMENT
    assert result.follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED
    assert "RISK_EXISTENCE_CONFLICT" in result.material_reasons


def test_supported_findings_with_disjoint_legal_basis_are_material() -> None:
    result = compare_finding(
        _primary_finding(legal_ids=["L-585"]),
        _secondary_review(legal_ids=["L-497"]),
    )

    assert result.legal_basis.state == EvidenceSetComparisonState.DISJOINT
    assert result.overall_state == OverallComparisonState.MATERIAL_DISAGREEMENT
    assert "LEGAL_BASIS_DISJOINT" in result.material_reasons


def test_partial_legal_overlap_is_recorded_without_unnecessary_agent_call() -> None:
    result = compare_finding(
        _primary_finding(legal_ids=["L-585", "L-577"]),
        _secondary_review(legal_ids=["L-585"]),
    )

    assert result.legal_basis.state == EvidenceSetComparisonState.PARTIAL_OVERLAP
    assert result.overall_state == OverallComparisonState.AGREEMENT
    assert result.follow_up == AgentFollowUpDecision.NOT_REQUIRED


def test_evidence_sufficiency_difference_requests_follow_up() -> None:
    result = compare_finding(
        _primary_finding(state=FindingState.SUPPORTED_FINDING),
        _secondary_review(assessment=SecondaryAssessment.INSUFFICIENT_EVIDENCE),
    )

    assert result.overall_state == OverallComparisonState.REQUIRES_MORE_EVIDENCE
    assert result.follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED


def test_possible_primary_omission_forces_material_follow_up() -> None:
    primary = _primary_report([_primary_finding()])
    secondary = _secondary_report(
        primary,
        [_secondary_review()],
        omissions=[
            SecondaryPossibleOmission(
                omission_id="omission-001",
                risk_category="格式条款",
                severity=FindingSeverity.HIGH,
                title="可能漏审格式条款",
                reasoning_summary="存在已提供证据支持的潜在漏审项。",
                suggestion="进一步复核。",
                canonical_object_ids=["clause-002"],
                contract_evidence_ids=["E-3"],
                legal_evidence_ids=["L-496"],
                review_reasons=[],
            )
        ],
    )

    report = compare_review_reports(primary, secondary)

    assert report.overall_state == OverallComparisonState.MATERIAL_DISAGREEMENT
    assert report.follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED
    assert report.omission_comparisons[0].omission_id == "omission-001"
    assert report.max_follow_up_cycles == 2


def test_report_ignores_secondary_self_declared_disagreement_categories() -> None:
    primary = _primary_report([_primary_finding()])
    secondary_review = _secondary_review()
    secondary_review.disagreement_categories = []
    secondary = _secondary_report(primary, [secondary_review])

    report = compare_review_reports(primary, secondary)

    assert report.overall_state == OverallComparisonState.AGREEMENT
    assert report.follow_up == AgentFollowUpDecision.NOT_REQUIRED
