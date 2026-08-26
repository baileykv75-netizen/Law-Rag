from __future__ import annotations

from pathlib import Path
from uuid import UUID

from .audit_plan_models import AuditPlanningCoverageState
from .audit_planner import load_audit_plan
from .human_review import HumanReviewError, load_human_review
from .human_review_models import HumanDecisionState
from .issue_legal_context import load_issue_legal_context
from .issue_primary_audit import load_issue_primary_audit
from .issue_review_report import load_issue_review_report
from .issue_secondary_review import load_issue_secondary_review
from .issue_workspace_models import (
    IssueWorkspaceCoverageSummary,
    IssueWorkspaceDetail,
    IssueWorkspacePresentationSummary,
    IssueWorkspaceQueueItem,
    IssueWorkspaceRiskSummary,
    IssueWorkspaceReviewSummary,
    IssueWorkspaceSummary,
)
from .ai_audit_models import FindingSeverity
from .issue_primary_audit_models import IssuePrimaryAuditState
from .issue_review_report_models import IssueReviewComparisonState
from .issue_secondary_review_models import SecondaryReviewDecisionStatus
from .storage import runtime_dir
from .workspace import load_workspace_summary
from .workspace_models import WorkspaceArtifactState, WorkspaceOverallState, WorkspaceStageSummary


class IssueWorkspaceError(RuntimeError):
    pass


_RESOLVED_HUMAN_STATES = {
    HumanDecisionState.CONFIRMED,
    HumanDecisionState.REJECTED,
    HumanDecisionState.ACCEPTED_RISK,
    HumanDecisionState.FALSE_POSITIVE,
    HumanDecisionState.MODIFIED,
    HumanDecisionState.NEEDS_LAWYER_REVIEW,
}

_SEVERITY_ORDER = {
    FindingSeverity.CRITICAL: 0,
    FindingSeverity.HIGH: 1,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.LOW: 3,
    FindingSeverity.INFO: 4,
}


def _risk_level(severity: FindingSeverity | None, *, pending: bool = False, critical: bool = False) -> str:
    if pending:
        return "待确认"
    if critical or severity == FindingSeverity.CRITICAL:
        return "重大风险"
    if severity == FindingSeverity.HIGH:
        return "高风险"
    if severity == FindingSeverity.MEDIUM:
        return "中风险"
    return "低风险"


def _signing_recommendation(overall_risk: str) -> str:
    if overall_risk == "重大风险":
        return "暂不建议签署，需先修改关键条款并由律师复核。"
    if overall_risk == "高风险":
        return "建议修改后签署，并确认高风险条款的责任边界。"
    if overall_risk == "中风险":
        return "可在补充确认和完善条款后推进签署。"
    if overall_risk == "待确认":
        return "存在未完成复审或证据不足事项，建议确认后再签署。"
    return "未发现优先级较高的风险，但仍建议结合交易背景复核。"


def _unfinished_signing_recommendation(overall: WorkspaceOverallState) -> str:
    if overall == WorkspaceOverallState.INVALID:
        return "审查产物异常，不能作为签署结论；请重新审查或清理后重新上传。"
    return "审查尚未完成，不能作为低风险或签署结论；请等待风险分析和报告生成完成。"


def _evidence_confidence(review: IssueWorkspaceReviewSummary, coverage: IssueWorkspaceCoverageSummary | None) -> str:
    if coverage is not None and not coverage.coverage_complete:
        return "待确认：合同文本覆盖不完整。"
    if review.secondary_pending_confirmation_count:
        return "待确认：部分争议复审可稍后补跑。"
    if review.insufficient_evidence_count:
        return "待确认：部分问题证据不足。"
    return "较充分：关键问题已完成证据审查。"


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


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


def _load_historical_optional(
    job_id: UUID,
    name: str,
    relaxed_loader,
    strict_loader,
    *,
    stage: str,
    label: str,
):
    path = _job_dir(job_id) / name
    if not path.exists():
        return (
            _stage(stage, label, WorkspaceArtifactState.MISSING, name, f"{name} is not present."),
            None,
            [],
        )
    try:
        value = relaxed_loader(job_id)
    except Exception as exc:
        return (
            _stage(
                stage,
                label,
                WorkspaceArtifactState.INVALID,
                name,
                f"{name} could not be loaded as a Stage 13 artifact: {type(exc).__name__}: {exc}",
            ),
            None,
            [],
        )

    stage_summary = _stage(
        stage,
        label,
        WorkspaceArtifactState.READY,
        name,
        f"Validated {name} is available locally.",
    )
    warnings: list[str] = []
    try:
        strict_loader(job_id)
    except Exception as exc:
        warning = (
            f"{name} is a historical audit artifact. Current dependencies changed after it was generated "
            f"({type(exc).__name__}: {exc}); display it as the report generated at that time and rerun audit "
            "before relying on it for a new signing decision."
        )
        warnings.append(warning)
        stage_summary.detail = (
            f"Loaded historical {name}; current legal corpus or upstream fingerprints changed after generation."
        )
    return stage_summary, value, warnings


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
    legal_stage, legal, legal_history_warnings = _load_historical_optional(
        job_id,
        "issue-legal-context.json",
        lambda current_job_id: load_issue_legal_context(current_job_id, validate_freshness=False),
        load_issue_legal_context,
        stage="13D",
        label="Issue-based Legal RAG",
    )
    primary_stage, primary, primary_history_warnings = _load_historical_optional(
        job_id,
        "issue-primary-audit.json",
        lambda current_job_id: load_issue_primary_audit(current_job_id, validate_freshness=False),
        load_issue_primary_audit,
        stage="13E",
        label="DeepSeek issue-by-issue primary audit",
    )
    secondary_stage, secondary, secondary_history_warnings = _load_historical_optional(
        job_id,
        "issue-secondary-review.json",
        lambda current_job_id: load_issue_secondary_review(current_job_id, validate_freshness=False),
        load_issue_secondary_review,
        stage="13F",
        label="Kimi finding and coverage review",
    )
    report_stage, report, report_history_warnings = _load_historical_optional(
        job_id,
        "issue-review-report.json",
        lambda current_job_id: load_issue_review_report(current_job_id, validate_freshness=False),
        load_issue_review_report,
        stage="13G",
        label="Deterministic issue comparison",
    )
    warnings.extend(legal_history_warnings)
    warnings.extend(primary_history_warnings)
    warnings.extend(secondary_history_warnings)
    warnings.extend(report_history_warnings)

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
    audit_chain_states = {item.state for item in stages}
    audit_chain_ready = all(
        item.state in {WorkspaceArtifactState.READY, WorkspaceArtifactState.NOT_REQUIRED}
        for item in stages
    )

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
        review.secondary_reviewed_count = sum(
            item.review_status == SecondaryReviewDecisionStatus.REVIEWED
            for item in secondary.results
        )
        review.secondary_skipped_clear_count = sum(
            item.review_status == SecondaryReviewDecisionStatus.SKIPPED_CLEAR
            for item in secondary.results
        )
        review.secondary_pending_confirmation_count = sum(
            item.review_status == SecondaryReviewDecisionStatus.PENDING_CONFIRMATION
            for item in secondary.results
        )
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

    human_view = None
    human_stage = _stage(
        "13G.6",
        "Issue human review",
        WorkspaceArtifactState.MISSING,
        "human-review.json",
        "Issue review report is not available yet; human review cannot be evaluated.",
    )
    if report is not None:
        try:
            human_view = load_human_review(job_id)
            review.human_review_available = True
            review.human_review_revision_count = len(
                [item for item in human_view.revisions if item.target_type.value == "issue"]
            )
            issue_latest = {
                key.removeprefix("issue:"): value
                for key, value in human_view.latest_by_target.items()
                if key.startswith("issue:")
            }
            stale_latest = sum(item.is_stale for item in issue_latest.values())
            required_ids = {
                item.issue_id for item in report.comparisons if item.requires_human_review
            }
            resolved_ids = {
                issue_id
                for issue_id, item in issue_latest.items()
                if issue_id in required_ids
                and not item.is_stale
                and item.state in _RESOLVED_HUMAN_STATES
            }
            review.human_review_resolved_required_count = len(resolved_ids)
            review.human_review_outstanding_required_count = len(required_ids - resolved_ids)
            review.human_review_stale_latest_count = stale_latest

            if plan is not None and not plan.coverage_complete:
                human_stage.detail = (
                    "Planning coverage is incomplete. Issue decisions cannot waive uncovered canonical objects; "
                    "the upstream coverage gap must be corrected or separately reviewed."
                )
                warnings.append(human_stage.detail)
            elif not required_ids:
                human_stage.state = WorkspaceArtifactState.NOT_REQUIRED
                human_stage.detail = "Deterministic comparison requires no mandatory Issue-level human review."
            elif not (required_ids - resolved_ids):
                human_stage.state = WorkspaceArtifactState.READY
                human_stage.detail = (
                    f"All {len(required_ids)} mandatory Issue review target(s) have a fresh CONFIRMED or REJECTED decision."
                )
            else:
                human_stage.detail = (
                    f"{len(required_ids - resolved_ids)}/{len(required_ids)} mandatory Issue review target(s) still need a fresh final human decision."
                )
            if stale_latest:
                warnings.append(
                    f"{stale_latest} latest Issue human decision(s) are stale against the current issue-review-report.json and must not close review."
                )
        except HumanReviewError as exc:
            message = str(exc)
            if message.startswith("Persisted human-review.json is invalid") or "job_id does not match" in message:
                human_stage.state = WorkspaceArtifactState.INVALID
                human_stage.detail = f"human-review.json could not be validated: {exc}"
                warnings.append(human_stage.detail)
            else:
                required_ids = {
                    item.issue_id for item in report.comparisons if item.requires_human_review
                }
                review.human_review_outstanding_required_count = len(required_ids)
                human_stage.detail = (
                    "This is a historical issue report; handling decisions can be added after rerunning audit "
                    "against the current legal corpus."
                )
                warnings.append(f"Issue handling decisions are unavailable for this historical report: {exc}")

    stages.append(human_stage)

    legal_by_id = {item.issue_id: item for item in legal.issues} if legal is not None else {}
    primary_by_id = {item.issue_id: item for item in primary.results} if primary is not None else {}
    secondary_by_id = {item.issue_id: item for item in secondary.results} if secondary is not None else {}
    comparison_by_id = {item.issue_id: item for item in report.comparisons} if report is not None else {}
    human_by_id = (
        {
            key.removeprefix("issue:"): value
            for key, value in human_view.latest_by_target.items()
            if key.startswith("issue:")
        }
        if human_view is not None
        else {}
    )

    queue: list[IssueWorkspaceQueueItem] = []
    if plan is not None:
        for issue in plan.issues:
            legal_item = legal_by_id.get(issue.issue_id)
            primary_item = primary_by_id.get(issue.issue_id)
            secondary_item = secondary_by_id.get(issue.issue_id)
            comparison = comparison_by_id.get(issue.issue_id)
            human_item = human_by_id.get(issue.issue_id)
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
                    secondary_review_status=secondary_item.review_status if secondary_item is not None else None,
                    coverage_assessment=secondary_item.coverage_assessment if secondary_item is not None else None,
                    comparison_state=comparison.overall_state if comparison is not None else None,
                    requires_human_review=comparison.requires_human_review if comparison is not None else False,
                    human_decision_state=human_item.state if human_item is not None else None,
                    human_decision_revision=human_item.revision if human_item is not None else None,
                    human_decision_stale=human_item.is_stale if human_item is not None else False,
                )
            )

    presentation = None
    if primary is not None:
        top_candidates: list[IssueWorkspaceRiskSummary] = []
        for issue in queue:
            primary_item = primary_by_id.get(issue.issue_id)
            if primary_item is None:
                continue
            comparison = comparison_by_id.get(issue.issue_id)
            pending_secondary = issue.secondary_review_status == SecondaryReviewDecisionStatus.PENDING_CONFIRMATION
            requires_decision = bool(comparison.requires_human_review if comparison is not None else pending_secondary)
            if (
                primary_item.state != IssuePrimaryAuditState.SUPPORTED_FINDING
                and not requires_decision
                and not pending_secondary
            ):
                continue
            level = _risk_level(
                primary_item.severity,
                pending=pending_secondary,
                critical=comparison is not None
                and comparison.overall_state
                in {IssueReviewComparisonState.MATERIAL_DISAGREEMENT, IssueReviewComparisonState.POSSIBLE_OMISSION},
            )
            top_candidates.append(
                IssueWorkspaceRiskSummary(
                    issue_id=issue.issue_id,
                    title=primary_item.title or issue.topic,
                    severity=primary_item.severity,
                    risk_level=level,
                    reason=primary_item.reasoning_summary,
                    suggested_action=primary_item.suggestion,
                    requires_decision=requires_decision,
                    secondary_review_status=issue.secondary_review_status or SecondaryReviewDecisionStatus.PENDING_CONFIRMATION,
                )
            )
        top_candidates.sort(
            key=lambda item: (
                0 if item.risk_level == "重大风险" else 1 if item.risk_level == "高风险" else 2 if item.risk_level == "待确认" else 3,
                _SEVERITY_ORDER[item.severity],
                item.title,
            )
        )
        top_risks = top_candidates[:5]
        if review.secondary_pending_confirmation_count:
            overall_risk = "待确认"
        elif any(item.risk_level == "重大风险" for item in top_candidates):
            overall_risk = "重大风险"
        elif any(item.risk_level == "高风险" for item in top_candidates):
            overall_risk = "高风险"
        elif any(item.risk_level == "中风险" for item in top_candidates):
            overall_risk = "中风险"
        else:
            overall_risk = "低风险"
        presentation = IssueWorkspacePresentationSummary(
            overall_risk=overall_risk,
            signing_recommendation=_signing_recommendation(overall_risk),
            evidence_confidence=_evidence_confidence(review, coverage),
            suggested_actions=_unique([item.suggested_action for item in top_risks if item.suggested_action])[:5],
            top_risks=top_risks,
            secondary_review_status_counts={
                "REVIEWED": review.secondary_reviewed_count,
                "SKIPPED_CLEAR": review.secondary_skipped_clear_count,
                "PENDING_CONFIRMATION": review.secondary_pending_confirmation_count,
            },
        )

    if WorkspaceArtifactState.INVALID in audit_chain_states or human_stage.state == WorkspaceArtifactState.INVALID:
        overall = WorkspaceOverallState.INVALID
    elif report is not None and base.source_available and audit_chain_ready:
        planning_gap = plan is not None and not plan.coverage_complete
        outstanding = review.human_review_outstanding_required_count > 0
        overall = (
            WorkspaceOverallState.HUMAN_REVIEW_REQUIRED
            if planning_gap or outstanding
            else WorkspaceOverallState.COMPLETE
        )
    else:
        overall = WorkspaceOverallState.INCOMPLETE

    if presentation is not None and overall in {WorkspaceOverallState.INCOMPLETE, WorkspaceOverallState.INVALID}:
        presentation = IssueWorkspacePresentationSummary(
            overall_risk="待确认",
            signing_recommendation=_unfinished_signing_recommendation(overall),
            evidence_confidence="待确认：审计链尚未完整生成，现有发现只能作为阶段性线索。",
            suggested_actions=["继续完成风险分析和报告生成后，再判断是否签署或修改。"],
            top_risks=presentation.top_risks,
            secondary_review_status_counts=presentation.secondary_review_status_counts,
        )

    return IssueWorkspaceSummary(
        job_id=job_id,
        overall_state=overall,
        source_available=base.source_available,
        document=base.document,
        stages=stages,
        coverage=coverage,
        review=review,
        presentation=presentation,
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
        legal = load_issue_legal_context(job_id, validate_freshness=False)
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
        primary = load_issue_primary_audit(job_id, validate_freshness=False)
        as_of = as_of or primary.as_of.isoformat()
        primary_item = next((item for item in primary.results if item.issue_id == issue_id), None)
        warnings.extend(primary.warnings)
    except FileNotFoundError:
        pass
    except Exception as exc:
        warnings.append(f"Primary issue audit artifact is unavailable or stale: {type(exc).__name__}: {exc}")

    try:
        secondary = load_issue_secondary_review(job_id, validate_freshness=False)
        secondary_item = next((item for item in secondary.results if item.issue_id == issue_id), None)
        warnings.extend(secondary.warnings)
    except FileNotFoundError:
        pass
    except Exception as exc:
        warnings.append(f"Secondary issue review artifact is unavailable or stale: {type(exc).__name__}: {exc}")

    try:
        report = load_issue_review_report(job_id, validate_freshness=False)
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
