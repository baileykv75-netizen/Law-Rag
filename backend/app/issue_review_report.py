from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .audit_planner import AuditPlannerError, load_audit_plan
from .issue_primary_audit import (
    IssuePrimaryAuditError,
    IssuePrimaryAuditStaleError,
    load_issue_primary_audit,
)
from .issue_primary_audit_models import IssuePrimaryAuditStatus
from .issue_review_comparison import compare_issue
from .issue_review_report_models import (
    IssueReviewComparisonState,
    IssueReviewFinalState,
    IssueReviewReport,
    IssueReviewSummary,
)
from .issue_secondary_review import (
    IssueSecondaryReviewError,
    IssueSecondaryReviewStaleError,
    load_issue_secondary_review,
)
from .issue_secondary_review_models import IssueSecondaryReviewStatus
from .safe_persistence import atomic_write_text
from .storage import job_issue_review_report_path


class IssueReviewReportError(RuntimeError):
    pass


class IssueReviewReportPrerequisiteError(IssueReviewReportError):
    pass


class IssueReviewReportValidationError(IssueReviewReportError):
    pass


class IssueReviewReportStaleError(IssueReviewReportError):
    pass


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique(values) -> list[str]:
    return list(dict.fromkeys(values))


def _validate_issue_sets(plan, primary, secondary) -> list[str]:
    plan_ids = [item.issue_id for item in plan.issues]
    primary_ids = [item.issue_id for item in primary.results]
    secondary_ids = [item.issue_id for item in secondary.results]

    if len(plan_ids) != len(set(plan_ids)):
        raise IssueReviewReportValidationError("AuditPlan contains duplicate issue IDs.")
    if len(primary_ids) != len(set(primary_ids)):
        raise IssueReviewReportValidationError("Stage 13E contains duplicate issue results.")
    if len(secondary_ids) != len(set(secondary_ids)):
        raise IssueReviewReportValidationError("Stage 13F contains duplicate issue results.")

    expected = set(plan_ids)
    if set(primary_ids) != expected or set(secondary_ids) != expected:
        raise IssueReviewReportValidationError(
            "AuditPlan, Stage 13E and Stage 13F must contain exactly the same issue set."
        )
    if primary.total_issue_count != len(plan_ids) or primary.completed_issue_count != len(plan_ids):
        raise IssueReviewReportValidationError("Stage 13E issue counts do not match the AuditPlan.")
    if secondary.total_issue_count != len(plan_ids) or secondary.completed_issue_count != len(plan_ids):
        raise IssueReviewReportValidationError("Stage 13F issue counts do not match the AuditPlan.")
    return plan_ids


def _summary(comparisons) -> IssueReviewSummary:
    counts = {state: 0 for state in IssueReviewComparisonState}
    for item in comparisons:
        counts[item.overall_state] += 1
    return IssueReviewSummary(
        total_issue_count=len(comparisons),
        consistent_count=counts[IssueReviewComparisonState.CONSISTENT],
        consistent_with_review_count=counts[IssueReviewComparisonState.CONSISTENT_WITH_REVIEW],
        material_disagreement_count=counts[IssueReviewComparisonState.MATERIAL_DISAGREEMENT],
        possible_omission_count=counts[IssueReviewComparisonState.POSSIBLE_OMISSION],
        insufficient_evidence_count=counts[IssueReviewComparisonState.INSUFFICIENT_EVIDENCE],
        review_required_count=counts[IssueReviewComparisonState.REVIEW_REQUIRED],
        human_review_required_count=sum(item.requires_human_review for item in comparisons),
    )


def _final_reasons(summary: IssueReviewSummary, *, planning_coverage_complete: bool) -> list[str]:
    reasons: list[str] = []
    if not planning_coverage_complete:
        reasons.append("PLANNING_COVERAGE_INCOMPLETE")
    if summary.possible_omission_count:
        reasons.append("POSSIBLE_OMISSION_PRESENT")
    if summary.material_disagreement_count:
        reasons.append("MATERIAL_DISAGREEMENT_PRESENT")
    if summary.insufficient_evidence_count:
        reasons.append("INSUFFICIENT_EVIDENCE_PRESENT")
    if summary.review_required_count:
        reasons.append("REVIEW_REQUIRED_PRESENT")
    if summary.consistent_with_review_count:
        reasons.append("CONSISTENT_WITH_REVIEW_PRESENT")
    return reasons


def _persist(report_payload: dict) -> IssueReviewReport:
    report = IssueReviewReport(
        **report_payload,
        artifact_fingerprint=_fingerprint(report_payload),
    )
    atomic_write_text(
        Path(job_issue_review_report_path(report.job_id)),
        report.model_dump_json(indent=2),
    )
    return report


def build_issue_review_report(job_id: UUID) -> IssueReviewReport:
    try:
        plan = load_audit_plan(job_id)
        primary = load_issue_primary_audit(job_id)
        secondary = load_issue_secondary_review(job_id)
    except FileNotFoundError:
        raise
    except (
        AuditPlannerError,
        IssuePrimaryAuditError,
        IssuePrimaryAuditStaleError,
        IssueSecondaryReviewError,
        IssueSecondaryReviewStaleError,
    ) as exc:
        raise IssueReviewReportPrerequisiteError(
            "Fresh Stage 13B-13F artifacts are required before deterministic issue comparison."
        ) from exc

    if primary.status != IssuePrimaryAuditStatus.COMPLETE:
        raise IssueReviewReportPrerequisiteError("Stage 13E must be COMPLETE before issue comparison.")
    if secondary.status != IssueSecondaryReviewStatus.COMPLETE:
        raise IssueReviewReportPrerequisiteError("Stage 13F must be COMPLETE before issue comparison.")
    if primary.audit_plan_fingerprint != secondary.audit_plan_fingerprint:
        raise IssueReviewReportValidationError(
            "Stage 13E and Stage 13F reference different AuditPlan fingerprints."
        )
    if primary.issue_legal_context_fingerprint != secondary.issue_legal_context_fingerprint:
        raise IssueReviewReportValidationError(
            "Stage 13E and Stage 13F reference different issue Legal RAG fingerprints."
        )
    if secondary.issue_primary_audit_fingerprint != primary.artifact_fingerprint:
        raise IssueReviewReportStaleError(
            "Stage 13F was produced from a different Stage 13E artifact."
        )

    plan_ids = _validate_issue_sets(plan, primary, secondary)
    primary_by_id = {item.issue_id: item for item in primary.results}
    secondary_by_id = {item.issue_id: item for item in secondary.results}

    comparisons = []
    for plan_issue in plan.issues:
        try:
            comparison = compare_issue(
                plan_issue,
                primary_by_id[plan_issue.issue_id],
                secondary_by_id[plan_issue.issue_id],
            )
        except ValueError as exc:
            raise IssueReviewReportValidationError(str(exc)) from exc
        comparisons.append(comparison)

    if len(comparisons) != len(plan_ids):
        raise IssueReviewReportValidationError(
            "Deterministic comparison did not produce exactly one result for every AuditPlan issue."
        )

    summary = _summary(comparisons)
    final_reasons = _final_reasons(
        summary,
        planning_coverage_complete=plan.coverage_complete,
    )
    final_state = (
        IssueReviewFinalState.HUMAN_REVIEW_REQUIRED
        if final_reasons
        else IssueReviewFinalState.NO_MANDATORY_REVIEW
    )
    payload = {
        "schema_version": "1.0.0",
        "engine_version": "stage13g-issue-comparison-1.0.0",
        "job_id": str(job_id),
        "status": "COMPLETE",
        "as_of": primary.as_of.isoformat(),
        "final_state": final_state.value,
        "primary_provider": primary.provider,
        "primary_model": primary.model,
        "secondary_provider": secondary.provider,
        "secondary_model": secondary.model,
        "audit_plan_fingerprint": primary.audit_plan_fingerprint,
        "issue_primary_audit_fingerprint": primary.artifact_fingerprint,
        "issue_secondary_review_fingerprint": secondary.artifact_fingerprint,
        "planning_coverage_complete": plan.coverage_complete,
        "issue_coverage_complete": True,
        "total_issue_count": len(plan_ids),
        "compared_issue_count": len(comparisons),
        "summary": summary.model_dump(mode="json"),
        "comparisons": [item.model_dump(mode="json") for item in comparisons],
        "final_reasons": final_reasons,
        "warnings": _unique([*plan.warnings, *primary.warnings, *secondary.warnings]),
    }
    return _persist(payload)


def load_issue_review_report(
    job_id: UUID,
    *,
    validate_freshness: bool = True,
) -> IssueReviewReport:
    path = job_issue_review_report_path(job_id)
    if not path.exists():
        raise FileNotFoundError(
            f"Stage 13G issue-review-report.json does not exist for job {job_id}."
        )
    try:
        report = IssueReviewReport.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise IssueReviewReportValidationError(
            "Persisted Stage 13G issue review report is malformed."
        ) from exc
    if report.job_id != job_id:
        raise IssueReviewReportValidationError(
            "Persisted Stage 13G issue review report belongs to a different job."
        )
    payload = report.model_dump(mode="json", exclude={"artifact_fingerprint"})
    if report.artifact_fingerprint != _fingerprint(payload):
        raise IssueReviewReportValidationError(
            "Persisted Stage 13G issue review report fingerprint is invalid."
        )

    if validate_freshness:
        try:
            primary = load_issue_primary_audit(job_id)
            secondary = load_issue_secondary_review(job_id)
        except FileNotFoundError as exc:
            raise IssueReviewReportStaleError(
                "Stage 13G report is stale because Stage 13E or Stage 13F is missing."
            ) from exc
        except (
            IssuePrimaryAuditError,
            IssuePrimaryAuditStaleError,
            IssueSecondaryReviewError,
            IssueSecondaryReviewStaleError,
        ) as exc:
            raise IssueReviewReportStaleError(
                "Stage 13G report is stale because an upstream issue artifact is stale or invalid."
            ) from exc

        if report.issue_primary_audit_fingerprint != primary.artifact_fingerprint:
            raise IssueReviewReportStaleError(
                "Stage 13G report is stale because issue-primary-audit.json changed."
            )
        if report.issue_secondary_review_fingerprint != secondary.artifact_fingerprint:
            raise IssueReviewReportStaleError(
                "Stage 13G report is stale because issue-secondary-review.json changed."
            )

    return report
