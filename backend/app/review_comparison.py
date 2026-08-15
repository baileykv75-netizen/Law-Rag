from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from .ai_audit_models import AiAuditFinding, AiAuditReport, FindingSeverity, FindingState
from .review_comparison_models import (
    AgentFollowUpDecision,
    EvidenceSetComparison,
    EvidenceSetComparisonState,
    FindingComparison,
    OmissionComparison,
    OverallComparisonState,
    ReviewComparisonReport,
    RiskComparisonState,
    SeverityComparison,
    SeverityComparisonState,
)
from .secondary_review_models import (
    SecondaryAssessment,
    SecondaryFindingReview,
    SecondaryReviewReport,
)


class ReviewComparisonError(RuntimeError):
    pass


_SEVERITY_RANK = {
    FindingSeverity.INFO: 0,
    FindingSeverity.LOW: 1,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.HIGH: 3,
    FindingSeverity.CRITICAL: 4,
}


def _stable_id(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def compare_evidence_sets(primary_ids: Iterable[str], secondary_ids: Iterable[str]) -> EvidenceSetComparison:
    primary = set(primary_ids)
    secondary = set(secondary_ids)
    shared = primary & secondary
    primary_only = primary - secondary
    secondary_only = secondary - primary

    if not primary and not secondary:
        state = EvidenceSetComparisonState.BOTH_EMPTY
    elif primary == secondary:
        state = EvidenceSetComparisonState.AGREE
    elif shared:
        state = EvidenceSetComparisonState.PARTIAL_OVERLAP
    elif primary and secondary:
        state = EvidenceSetComparisonState.DISJOINT
    elif primary:
        state = EvidenceSetComparisonState.PRIMARY_ONLY
    else:
        state = EvidenceSetComparisonState.SECONDARY_ONLY

    return EvidenceSetComparison(
        state=state,
        shared=sorted(shared),
        primary_only=sorted(primary_only),
        secondary_only=sorted(secondary_only),
    )


def compare_severity(primary: FindingSeverity, secondary: FindingSeverity) -> SeverityComparison:
    distance = abs(_SEVERITY_RANK[primary] - _SEVERITY_RANK[secondary])
    if distance == 0:
        state = SeverityComparisonState.AGREE
    elif distance == 1:
        state = SeverityComparisonState.MINOR_DISAGREEMENT
    else:
        state = SeverityComparisonState.MATERIAL_DISAGREEMENT
    return SeverityComparison(
        primary=primary,
        secondary=secondary,
        distance=distance,
        state=state,
    )


def compare_risk_state(primary: FindingState, secondary: SecondaryAssessment) -> RiskComparisonState:
    exact_pairs = {
        (FindingState.SUPPORTED_FINDING, SecondaryAssessment.SUPPORTED): RiskComparisonState.AGREE_SUPPORTED,
        (FindingState.NO_FINDING, SecondaryAssessment.NOT_SUPPORTED): RiskComparisonState.AGREE_NO_FINDING,
        (FindingState.REVIEW_REQUIRED, SecondaryAssessment.REVIEW_REQUIRED): RiskComparisonState.AGREE_REVIEW_REQUIRED,
        (
            FindingState.INSUFFICIENT_EVIDENCE,
            SecondaryAssessment.INSUFFICIENT_EVIDENCE,
        ): RiskComparisonState.AGREE_INSUFFICIENT_EVIDENCE,
    }
    exact = exact_pairs.get((primary, secondary))
    if exact is not None:
        return exact

    if (
        primary == FindingState.SUPPORTED_FINDING
        and secondary == SecondaryAssessment.NOT_SUPPORTED
    ) or (
        primary == FindingState.NO_FINDING
        and secondary == SecondaryAssessment.SUPPORTED
    ):
        return RiskComparisonState.DISAGREE_RISK_EXISTS

    uncertain_secondary = secondary in {
        SecondaryAssessment.REVIEW_REQUIRED,
        SecondaryAssessment.INSUFFICIENT_EVIDENCE,
    }
    uncertain_primary = primary in {
        FindingState.REVIEW_REQUIRED,
        FindingState.INSUFFICIENT_EVIDENCE,
    }
    if uncertain_secondary != uncertain_primary:
        return RiskComparisonState.DISAGREE_EVIDENCE_SUFFICIENCY

    return RiskComparisonState.STATE_DIFFERENCE


def _finding_final_state(
    primary: AiAuditFinding,
    secondary: SecondaryFindingReview,
    risk_state: RiskComparisonState,
    severity: SeverityComparison,
    contract_evidence: EvidenceSetComparison,
    legal_basis: EvidenceSetComparison,
) -> tuple[OverallComparisonState, list[str], AgentFollowUpDecision]:
    reasons: list[str] = []

    if risk_state == RiskComparisonState.DISAGREE_RISK_EXISTS:
        reasons.append("RISK_EXISTENCE_CONFLICT")
    if severity.state == SeverityComparisonState.MATERIAL_DISAGREEMENT:
        reasons.append("SEVERITY_DISTANCE_GTE_2")

    primary_affirms_risk = primary.state == FindingState.SUPPORTED_FINDING
    secondary_affirms_risk = secondary.assessment == SecondaryAssessment.SUPPORTED
    both_affirm_risk = primary_affirms_risk and secondary_affirms_risk

    if both_affirm_risk and legal_basis.state == EvidenceSetComparisonState.DISJOINT:
        reasons.append("LEGAL_BASIS_DISJOINT")
    if both_affirm_risk and contract_evidence.state == EvidenceSetComparisonState.DISJOINT:
        reasons.append("CONTRACT_EVIDENCE_DISJOINT")

    if reasons:
        return (
            OverallComparisonState.MATERIAL_DISAGREEMENT,
            reasons,
            AgentFollowUpDecision.FOLLOW_UP_REQUIRED,
        )

    if risk_state in {
        RiskComparisonState.DISAGREE_EVIDENCE_SUFFICIENCY,
        RiskComparisonState.STATE_DIFFERENCE,
    }:
        return (
            OverallComparisonState.REQUIRES_MORE_EVIDENCE,
            [risk_state.value],
            AgentFollowUpDecision.FOLLOW_UP_REQUIRED,
        )

    if risk_state in {
        RiskComparisonState.AGREE_REVIEW_REQUIRED,
        RiskComparisonState.AGREE_INSUFFICIENT_EVIDENCE,
    }:
        return (
            OverallComparisonState.AGREEMENT_WITH_REVIEW,
            [risk_state.value],
            AgentFollowUpDecision.FOLLOW_UP_REQUIRED,
        )

    if severity.state == SeverityComparisonState.MINOR_DISAGREEMENT:
        return (
            OverallComparisonState.MINOR_DISAGREEMENT,
            ["SEVERITY_DISTANCE_1"],
            AgentFollowUpDecision.NOT_REQUIRED,
        )

    # Evidence-set differences do not automatically become material when the
    # two models already agree on no finding/review/insufficient evidence. For
    # supported findings, partial overlap is recorded for human inspection but
    # does not by itself invoke the Agent.
    return OverallComparisonState.AGREEMENT, [], AgentFollowUpDecision.NOT_REQUIRED


def compare_finding(primary: AiAuditFinding, secondary: SecondaryFindingReview) -> FindingComparison:
    if primary.finding_id != secondary.primary_finding_id:
        raise ReviewComparisonError(
            f"Finding alignment mismatch: {primary.finding_id} != {secondary.primary_finding_id}"
        )

    risk_state = compare_risk_state(primary.state, secondary.assessment)
    severity = compare_severity(primary.severity, secondary.severity)
    contract_evidence = compare_evidence_sets(
        primary.contract_evidence_ids,
        secondary.contract_evidence_ids,
    )
    legal_basis = compare_evidence_sets(
        primary.legal_evidence_ids,
        secondary.legal_evidence_ids,
    )
    overall, reasons, follow_up = _finding_final_state(
        primary,
        secondary,
        risk_state,
        severity,
        contract_evidence,
        legal_basis,
    )
    comparison_id = _stable_id(
        "comparison",
        {
            "primary_finding_id": primary.finding_id,
            "risk_state": risk_state.value,
            "severity": severity.model_dump(mode="json"),
            "contract_evidence": contract_evidence.model_dump(mode="json"),
            "legal_basis": legal_basis.model_dump(mode="json"),
        },
    )
    return FindingComparison(
        comparison_id=comparison_id,
        primary_finding_id=primary.finding_id,
        risk_state=risk_state,
        severity=severity,
        contract_evidence=contract_evidence,
        legal_basis=legal_basis,
        overall_state=overall,
        material_reasons=reasons,
        follow_up=follow_up,
    )


def compare_review_reports(
    primary: AiAuditReport,
    secondary: SecondaryReviewReport,
) -> ReviewComparisonReport:
    if str(primary.job_id) != str(secondary.job_id):
        raise ReviewComparisonError("Primary and secondary reports belong to different jobs.")
    if primary.context_fingerprint != secondary.primary_context_fingerprint:
        raise ReviewComparisonError("Secondary report does not point to the supplied primary context fingerprint.")

    primary_by_id = {finding.finding_id: finding for finding in primary.findings}
    secondary_by_id = {review.primary_finding_id: review for review in secondary.finding_reviews}
    if set(primary_by_id) != set(secondary_by_id):
        missing = sorted(set(primary_by_id) - set(secondary_by_id))
        extra = sorted(set(secondary_by_id) - set(primary_by_id))
        raise ReviewComparisonError(
            f"Primary/secondary finding sets do not align; missing={missing}, extra={extra}."
        )

    comparisons = [
        compare_finding(primary_by_id[finding_id], secondary_by_id[finding_id])
        for finding_id in sorted(primary_by_id)
    ]
    omissions = [
        OmissionComparison(
            omission_id=item.omission_id,
            risk_category=item.risk_category,
            severity=item.severity,
            contract_evidence_ids=item.contract_evidence_ids,
            legal_evidence_ids=item.legal_evidence_ids,
        )
        for item in secondary.possible_omissions
    ]

    follow_up_reasons: list[str] = []
    for item in comparisons:
        if item.follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED:
            follow_up_reasons.extend(
                f"{item.primary_finding_id}:{reason}" for reason in item.material_reasons
            )
    for omission in omissions:
        follow_up_reasons.append(f"{omission.omission_id}:{omission.reason}")

    states = {item.overall_state for item in comparisons}
    if omissions or OverallComparisonState.MATERIAL_DISAGREEMENT in states:
        overall = OverallComparisonState.MATERIAL_DISAGREEMENT
    elif OverallComparisonState.REQUIRES_MORE_EVIDENCE in states:
        overall = OverallComparisonState.REQUIRES_MORE_EVIDENCE
    elif OverallComparisonState.AGREEMENT_WITH_REVIEW in states:
        overall = OverallComparisonState.AGREEMENT_WITH_REVIEW
    elif OverallComparisonState.MINOR_DISAGREEMENT in states:
        overall = OverallComparisonState.MINOR_DISAGREEMENT
    else:
        overall = OverallComparisonState.AGREEMENT

    follow_up = (
        AgentFollowUpDecision.FOLLOW_UP_REQUIRED
        if omissions or any(
            item.follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED
            for item in comparisons
        )
        else AgentFollowUpDecision.NOT_REQUIRED
    )

    return ReviewComparisonReport(
        job_id=str(primary.job_id),
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint=secondary.secondary_context_fingerprint,
        finding_comparisons=comparisons,
        omission_comparisons=omissions,
        overall_state=overall,
        follow_up=follow_up,
        follow_up_reasons=sorted(set(follow_up_reasons)),
    )
