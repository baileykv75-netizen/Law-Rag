from __future__ import annotations

from pathlib import Path
from uuid import UUID

from .audit_plan_models import AuditPlanningCoverageState
from .audit_planner import load_audit_plan
from .issue_legal_context import load_issue_legal_context
from .issue_primary_audit import load_issue_primary_audit
from .issue_review_report import load_issue_review_report
from .issue_secondary_review import load_issue_secondary_review
from .issue_workspace_models import (
    IssueWorkspaceCoverageSummary,
    IssueWorkspaceDetail,
    IssueWorkspaceQueueItem,
    IssueWorkspaceReviewSummary,
    IssueWorkspaceSummary,
)
from .storage import runtime_dir
from .workspace import load_workspace_summary
from .workspace_models import WorkspaceArtifactState, WorkspaceOverallState, WorkspaceStageSummary


class IssueWorkspaceError(RuntimeError):
    pass


def _job_dir(job_id: UUID) -> Path:
    return runtime_dir() / "jobs" / str(job_id)


def _stage(
    stage: str,
    label: str,
    state: WorkspaceArtifactState,
    artifact: str,
    detail: str,
) -> WorkspaceStageSummary:
    return WorkspaceStageSummary(
        stage=stage,
        label=label,
        state=state,
        artifact=artifact,
        detail=detail,
    )


def _load_optional(job_id: UUID, name: str, loader, *, stage: str, label: str):
    path = _job_dir(job_id) / name
    if not path.exists():
        return _stage(stage, label, WorkspaceArtifactState.MISSING, name, f"{name} is not present."), None
    try:
        value = loader(job_id)
    except Exception as exc:
        return (
            _stage(
                stage,
                label,
                WorkspaceArtifactState.INVALID,
                name,
                f"{name} could not be validated as a fresh Stage 13 artifact: {type(exc).__name__}: {exc}",
            ),
            None,
        )
    return (
        _stage(stage, label, WorkspaceArtifactState.READY, name, f"Validated {name} is available locally."),
        value,
    )


def _base_workspace(job_id: UUID):
    """Reuse the proven Stage 2-7 reader but discard legacy Stage 8-10 semantics."""

    legacy = load_workspace_summary(job_id)
    base_stages = [item for item in legacy.stages if item.stage in {"2", "3", "4", "5", "6", "7"}]
    warnings = [
        warning
        for warning in legacy.warnings
        if not any(token in warning for token in ("Stage 8", "Stage 9", "Stage 10", "human-review"))
    ]
    return legacy, base_stages, warnings


def load_issue_workspace_summary(job_id: UUID) -> IssueWorkspaceSummary:
    base, stages, warnings = _base_workspace(job_id)

    plan_stage, plan = _load_optional(
        job_id,
        "audit-plan.json",
        load_audit_plan,
        stage="13B/C",
        label="Audit Planner and planning coverage",
    )
    legal_stage, legal = _load_optional(
        job_id,
        "issue-legal-context.json",
        load_issue_legal_context,
        stage="13D",
        label="Issue-based Legal RAG",
    )
    primary_stage, primary = _load_optional(
        job_id,
        "issue-primary-audit.json",
        load_issue_primary_audit,
        stage="13E",
        label="DeepSeek issue-by-issue primary audit",
    )
    secondary_stage, secondary = _load_optional(
        job_id,
        "issue-secondary-review.json",
        load_issue_secondary_review,
        stage="13F",
        label="Kimi finding and coverage review",
    )
    report_stage, report = _load_optional(
        job_id,
        "issue-review-report.json",
        load_issue_review_report,
        stage="13G",
        label="Deterministic issue comparison",
    )

    if plan is not None:
        plan_stage.detail = (
            f"{plan.planning_mode.value} planning produced {len(plan.issues)} issue(s); "
            f"coverage {'complete' if plan.coverage_complete else 'incomplete'} across {len(plan.coverage)} canonical object(s)."
        )
        warnings.extend(plan.warnings)
    if legal is not None:
        legal_stage.detail = (
            f"Issue Legal RAG contains {len(legal.issues)}/{legal.total_issue_count} issue package(s) "
            f"and {legal.total_query_count} retrieval query run(s)."
        )
        warnings.extend(legal.warnings)
    if primary is not None:
        primary_stage.detail = (
            f"DeepSeek checkpoint status {primary.status.value}; "
            f"{primary.completed_issue_count}/{primary.total_issue_count} issue(s) completed."
        )
        warnings.extend(primary.warnings)
    if secondary is not None:
        secondary_stage.detail = (
            f"Kimi checkpoint status {secondary.status.value}; "
            f"{secondary.completed_issue_count}/{secondary.total_issue_count} issue(s) completed."
        )
        warnings.extend(secondary.warnings)
    if report is not None:
        report_stage.detail = (
            f"Deterministically compared {report.compared_issue_count}/{report.total_issue_count} issue(s); "
            f"final state {report.final_state.value}."
        )
        warnings.extend(report.warnings)

    stages.extend([plan_stage, legal_stage, primary_stage, secondary_stage, report_stage])

    coverage = None
    if plan is not None:
        with_issue = sum(
            item.state == AuditPlanningCoverageState.REVIEWED_WITH_ISSUE
            for item in plan.coverage
        )
        no_specific_issue = sum(
            item.state == AuditPlanningCoverageState.REVIEWED_NO_SPECIFIC_ISSUE
            for item in plan.coverage
        )
        coverage = IssueWorkspaceCoverageSummary(
            planning_mode=plan.planning_mode,
            contract_type=plan.contract_type,
            coverage_complete=plan.coverage_complete,
            canonical_object_count=len(plan.coverage),
            reviewed_with_issue_count=with_issue,
            reviewed_no_specific_issue_count=no_specific_issue,
            issue_count=len(plan.issues),
        )
        if not plan.coverage_complete:
            warnings.append(
                "Audit planning coverage is incomplete. Absence of an Issue must not be presented as evidence that the uncovered contract text is safe."
            )

    review = IssueWorkspaceReviewSummary()
    if primary is not None:
        review.primary_available = True
        review.primary_provider = primary.provider
        review.primary_model = primary.model
        review.primary_completed_issue_count = primary.completed_issue_count
    if secondary is not None:
        review.secondary_available = True
        review.secondary_provider = secondary.provider
        review.secondary_model = secondary.model
        review.secondary_completed_issue_count = secondary.completed_issue_count
    if report is not None:
        review.comparison_available = True
        review.final_review_state = report.final_state
        review.compared_issue_count = report.compared_issue_count
        review.human_review_required_count = report.summary.human_review_required_count
        review.material_disagreement_count = report.summary.material_disagreement_count
        review.possible_omission_count = report.summary.possible_omission_count
        review.insufficient_evidence_count = report.summary.insufficient_evidence_count
        review.review_required_count = report.summary.review_required_count
        review.consistent_with_review_count = report.summary.consistent_with_review_count

    legal_by_id = {item.issue_id: item for item in legal.issues} if legal is not None else {}
    primary_by_id = {item.issue_id: item for item in primary.results} if primary is not None else {}
    secondary_by_id = {item.issue_id: item for item in secondary.results} if secondary is not None else {}
    comparison_by_id = {item.issue_id: item for item in report.comparisons} if report is not None else {}

    queue: list[IssueWorkspaceQueueItem] = []
    if plan is not None:
        for issue in plan.issues:
            legal_item = legal_by_id.get(issue.issue_id)
            primary_item = primary_by_id.get(issue.issue_id)
            secondary_item = secondary_by_id.get(issue.issue_id)
            comparison = comparison_by_id.get(issue.issue_id)
            queue.append(
                IssueWorkspaceQueueItem(
                    issue_id=issue.issue_id,
                    topic=issue.topic,
                    priority=issue.priority,
                    source_labels=[item.value for item in issue.sources],
                    contract_evidence_count=len(issue.contract_evidence_ids),
                    legal_evidence_count=len(legal_item.legal_evidence) if legal_item is not None else 0,
                    legal_support_state=legal_item.support_state if legal_item is not None else None,
                    primary_state=primary_item.state if primary_item is not None else None,
                    primary_severity=primary_item.severity if primary_item is not None else None,
                    secondary_assessment=secondary_item.assessment if secondary_item is not None else None,
                    coverage_assessment=secondary_item.coverage_assessment if secondary_item is not None else None,
                    comparison_state=comparison.overall_state if comparison is not None else None,
                    requires_human_review=comparison.requires_human_review if comparison is not None else False,
                )
            )

    states = {item.state for item in stages}
    if WorkspaceArtifactState.INVALID in states:
        overall = WorkspaceOverallState.INVALID
    elif report is not None and base.source_available:
        overall = (
            WorkspaceOverallState.HUMAN_REVIEW_REQUIRED
            if report.final_state.value == "HUMAN_REVIEW_REQUIRED"
            else WorkspaceOverallState.COMPLETE
        )
    else:
        overall = WorkspaceOverallState.INCOMPLETE

    return IssueWorkspaceSummary(
        job_id=job_id,
        overall_state=overall,
        source_available=base.source_available,
        document=base.document,
        stages=stages,
        coverage=coverage,
        review=review,
        issues=queue,
        source_uncertainty=base.source_uncertainty,
        warnings=sorted(set(warnings)),
    )


def load_issue_workspace_detail(job_id: UUID, issue_id: str) -> IssueWorkspaceDetail:
    try:
        plan = load_audit_plan(job_id)
    except Exception as exc:
        raise IssueWorkspaceError(f"A valid AuditPlan is required to inspect Issue {issue_id}: {exc}") from exc

    plan_issue = next((item for item in plan.issues if item.issue_id == issue_id), None)
    if plan_issue is None:
        raise FileNotFoundError(f"AuditPlan issue {issue_id} does not exist for job {job_id}.")

    warnings = list(plan.warnings)
    legal_item = None
    primary_item = None
    secondary_item = None
    comparison = None
    as_of: str | None = None

    try:
        legal = load_issue_legal_context(job_id)
        as_of = legal.as_of.isoformat()
        legal_item = next((item for item in legal.issues if item.issue_id == issue_id), None)
        warnings.extend(legal.warnings)
        if legal_item is not None:
            warnings.extend(legal_item.warnings)
    except FileNotFoundError:
        pass
    except Exception as exc:
        warnings.append(f"Issue Legal RAG artifact is unavailable or stale: {type(exc).__name__}: {exc}")

    try:
        primary = load_issue_primary_audit(job_id)
        as_of = as_of or primary.as_of.isoformat()
        primary_item = next((item for item in primary.results if item.issue_id == issue_id), None)
        warnings.extend(primary.warnings)
    except FileNotFoundError:
        pass
    except Exception as exc:
        warnings.append(f"Primary issue audit artifact is unavailable or stale: {type(exc).__name__}: {exc}")

    try:
        secondary = load_issue_secondary_review(job_id)
        secondary_item = next((item for item in secondary.results if item.issue_id == issue_id), None)
        warnings.extend(secondary.warnings)
    except FileNotFoundError:
        pass
    except Exception as exc:
        warnings.append(f"Secondary issue review artifact is unavailable or stale: {type(exc).__name__}: {exc}")

    try:
        report = load_issue_review_report(job_id)
        as_of = as_of or report.as_of
        comparison = next((item for item in report.comparisons if item.issue_id == issue_id), None)
        warnings.extend(report.warnings)
    except FileNotFoundError:
        pass
    except Exception as exc:
        warnings.append(f"Issue comparison artifact is unavailable or stale: {type(exc).__name__}: {exc}")

    return IssueWorkspaceDetail(
        job_id=job_id,
        issue_id=issue_id,
        as_of=as_of,
        plan_issue=plan_issue,
        legal_support_state=legal_item.support_state if legal_item is not None else None,
        legal_evidence=legal_item.legal_evidence if legal_item is not None else [],
        primary=primary_item,
        secondary=secondary_item,
        comparison=comparison,
        warnings=sorted(set(warnings)),
    )
