from __future__ import annotations

from .ai_audit_models import FindingSeverity
from .audit_plan_models import AuditPlanIssue
from .issue_primary_audit_models import (
    IssueEvidenceSufficiency,
    IssuePrimaryAuditResult,
    IssuePrimaryAuditState,
)
from .issue_review_report_models import (
    IssueEvidenceAlignment,
    IssueEvidenceAlignmentState,
    IssueReviewComparison,
    IssueReviewComparisonState,
)
from .issue_secondary_review_models import (
    IssueSecondaryReviewResult,
    SecondaryCoverageAssessment,
    SecondaryIssueAssessment,
    SecondaryReviewDecisionStatus,
)


_SEVERITY_RANK = {
    FindingSeverity.INFO: 0,
    FindingSeverity.LOW: 1,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.HIGH: 3,
    FindingSeverity.CRITICAL: 4,
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _evidence_alignment(primary_ids: list[str], secondary_ids: list[str]) -> IssueEvidenceAlignment:
    primary = set(primary_ids)
    secondary = set(secondary_ids)
    shared = sorted(primary & secondary)
    primary_only = sorted(primary - secondary)
    secondary_only = sorted(secondary - primary)

    if not primary and not secondary:
        state = IssueEvidenceAlignmentState.BOTH_EMPTY
    elif primary == secondary:
        state = IssueEvidenceAlignmentState.AGREE
    elif primary and secondary and shared:
        state = IssueEvidenceAlignmentState.PARTIAL_OVERLAP
    elif primary and secondary:
        state = IssueEvidenceAlignmentState.DISJOINT
    elif primary:
        state = IssueEvidenceAlignmentState.PRIMARY_ONLY
    else:
        state = IssueEvidenceAlignmentState.SECONDARY_ONLY

    return IssueEvidenceAlignment(
        state=state,
        shared=shared,
        primary_only=primary_only,
        secondary_only=secondary_only,
    )


def compare_issue(
    plan_issue: AuditPlanIssue,
    primary: IssuePrimaryAuditResult,
    secondary: IssueSecondaryReviewResult,
) -> IssueReviewComparison:
    if primary.issue_id != plan_issue.issue_id or secondary.issue_id != plan_issue.issue_id:
        raise ValueError("Issue comparison inputs do not share the same AuditPlan issue_id.")
    if secondary.primary_state != primary.state.value:
        raise ValueError("Secondary review primary_state does not match the authoritative Stage 13E result.")
    if primary.topic != plan_issue.topic or secondary.topic != plan_issue.topic:
        raise ValueError("Issue comparison inputs do not preserve the AuditPlan topic.")

    severity_distance = abs(_SEVERITY_RANK[primary.severity] - _SEVERITY_RANK[secondary.severity])
    contract_evidence = _evidence_alignment(primary.contract_evidence_ids, secondary.contract_evidence_ids)
    legal_evidence = _evidence_alignment(primary.legal_evidence_ids, secondary.legal_evidence_ids)
    reasons: list[str] = []

    if secondary.review_status == SecondaryReviewDecisionStatus.PENDING_CONFIRMATION:
        overall = IssueReviewComparisonState.REVIEW_REQUIRED
        reasons.append("SECONDARY_REVIEW_PENDING_CONFIRMATION")
    elif secondary.coverage_assessment == SecondaryCoverageAssessment.POSSIBLE_OMISSION:
        overall = IssueReviewComparisonState.POSSIBLE_OMISSION
        reasons.append("SECONDARY_POSSIBLE_OMISSION")
    elif (
        primary.state == IssuePrimaryAuditState.INSUFFICIENT_EVIDENCE
        or secondary.assessment == SecondaryIssueAssessment.INSUFFICIENT_EVIDENCE
        or secondary.coverage_assessment == SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE
    ):
        overall = IssueReviewComparisonState.INSUFFICIENT_EVIDENCE
        reasons.append("ISSUE_EVIDENCE_INSUFFICIENT")
    elif secondary.assessment == SecondaryIssueAssessment.DISAGREED:
        overall = IssueReviewComparisonState.MATERIAL_DISAGREEMENT
        reasons.append("SECONDARY_DISAGREED_WITH_PRIMARY")
    elif (
        primary.state == IssuePrimaryAuditState.REVIEW_REQUIRED
        or secondary.assessment == SecondaryIssueAssessment.REVIEW_REQUIRED
    ):
        overall = IssueReviewComparisonState.REVIEW_REQUIRED
        reasons.append("MODEL_REVIEW_REQUIRED")
    elif severity_distance >= 2:
        overall = IssueReviewComparisonState.MATERIAL_DISAGREEMENT
        reasons.append("SEVERITY_DISTANCE_MATERIAL")
    elif (
        secondary.assessment == SecondaryIssueAssessment.PARTIALLY_SUPPORTED
        or secondary.coverage_assessment == SecondaryCoverageAssessment.COVERED_BUT_QUESTIONABLE
        or severity_distance == 1
    ):
        overall = IssueReviewComparisonState.CONSISTENT_WITH_REVIEW
        if secondary.assessment == SecondaryIssueAssessment.PARTIALLY_SUPPORTED:
            reasons.append("SECONDARY_PARTIALLY_SUPPORTED")
        if secondary.coverage_assessment == SecondaryCoverageAssessment.COVERED_BUT_QUESTIONABLE:
            reasons.append("SECONDARY_COVERAGE_QUESTIONABLE")
        if severity_distance == 1:
            reasons.append("SEVERITY_DISTANCE_MINOR")
    else:
        overall = IssueReviewComparisonState.CONSISTENT
        reasons.append("PRIMARY_SECONDARY_CONSISTENT")

    if overall == IssueReviewComparisonState.CONSISTENT:
        if primary.evidence_sufficiency != IssueEvidenceSufficiency.SUFFICIENT:
            overall = IssueReviewComparisonState.CONSISTENT_WITH_REVIEW
            reasons.append(f"PRIMARY_EVIDENCE_{primary.evidence_sufficiency.value}")
        if contract_evidence.state == IssueEvidenceAlignmentState.DISJOINT:
            overall = IssueReviewComparisonState.CONSISTENT_WITH_REVIEW
            reasons.append("CONTRACT_EVIDENCE_DISJOINT")
        if legal_evidence.state == IssueEvidenceAlignmentState.DISJOINT:
            overall = IssueReviewComparisonState.CONSISTENT_WITH_REVIEW
            reasons.append("LEGAL_EVIDENCE_DISJOINT")
        material_secondary_reasons = [
            reason
            for reason in secondary.review_reasons
            if reason not in {"SECONDARY_REVIEW_SKIPPED_CLEAR"}
        ]
        if primary.review_reasons or material_secondary_reasons:
            overall = IssueReviewComparisonState.CONSISTENT_WITH_REVIEW
            reasons.append("UPSTREAM_REVIEW_REASON_PRESENT")

    reasons.extend(primary.review_reasons)
    reasons.extend(secondary.review_reasons)
    possible_omission = secondary.coverage_assessment == SecondaryCoverageAssessment.POSSIBLE_OMISSION

    return IssueReviewComparison(
        issue_id=plan_issue.issue_id,
        topic=plan_issue.topic,
        plan_priority=plan_issue.priority,
        primary_state=primary.state,
        primary_evidence_sufficiency=primary.evidence_sufficiency,
        legal_support_state=primary.legal_support_state,
        primary_legal_conclusion=primary.legal_conclusion,
        secondary_assessment=secondary.assessment,
        coverage_assessment=secondary.coverage_assessment,
        primary_severity=primary.severity,
        secondary_severity=secondary.severity,
        severity_distance=severity_distance,
        contract_evidence=contract_evidence,
        legal_evidence=legal_evidence,
        overall_state=overall,
        requires_human_review=overall != IssueReviewComparisonState.CONSISTENT,
        reasons=_unique(reasons),
        omission_title=secondary.omission_title if possible_omission else None,
        omission_reasoning=secondary.omission_reasoning if possible_omission else None,
    )
