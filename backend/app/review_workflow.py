from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from .agent_policy import plan_follow_up
from .agent_tools import execute_agent_action
from .ai_audit import AiAuditValidationError, load_ai_audit_report
from .review_comparison import ReviewComparisonError, compare_review_reports
from .review_comparison_models import (
    AgentActionRecord,
    AgentActionState,
    AgentPlanState,
    OverallComparisonState,
    ReviewComparisonReport,
)
from .secondary_review import SecondaryReviewValidationError, load_secondary_review_report

STAGE9C_WORKFLOW_SCHEMA_VERSION = "1.0.0"
STAGE9C_WORKFLOW_ENGINE_VERSION = "stage9c-workflow-1.0.0"


class Stage9cWorkflowState(str, Enum):
    DUAL_MODEL_AGREEMENT = "DUAL_MODEL_AGREEMENT"
    MINOR_DISAGREEMENT = "MINOR_DISAGREEMENT"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class Stage9cWorkflowResult(BaseModel):
    schema_version: str = STAGE9C_WORKFLOW_SCHEMA_VERSION
    engine_version: str = STAGE9C_WORKFLOW_ENGINE_VERSION
    job_id: UUID
    state: Stage9cWorkflowState
    comparison: ReviewComparisonReport
    plan_state: AgentPlanState
    executed_actions: list[AgentActionRecord] = Field(default_factory=list)
    evidence_gathered: bool = False
    final_reasons: list[str] = Field(default_factory=list)


class Stage9cWorkflowError(RuntimeError):
    pass


def _finalize_without_actions(job_id: UUID, comparison: ReviewComparisonReport) -> Stage9cWorkflowResult:
    if comparison.overall_state == OverallComparisonState.AGREEMENT:
        state = Stage9cWorkflowState.DUAL_MODEL_AGREEMENT
    elif comparison.overall_state == OverallComparisonState.MINOR_DISAGREEMENT:
        state = Stage9cWorkflowState.MINOR_DISAGREEMENT
    else:
        # This branch should normally have a follow-up plan, but fail closed if
        # comparison semantics change in a future version.
        state = Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED
    return Stage9cWorkflowResult(
        job_id=job_id,
        state=state,
        comparison=comparison,
        plan_state=AgentPlanState.NOT_REQUIRED,
        executed_actions=[],
        evidence_gathered=False,
        final_reasons=comparison.follow_up_reasons,
    )


def run_stage9c_workflow(job_id: UUID) -> Stage9cWorkflowResult:
    """Run deterministic comparison and bounded local evidence follow-up.

    Stage 9C deliberately does not call a third model and does not reinterpret
    the two validated model conclusions after tools run. Tool output is extra
    evidence for the later review report/human reviewer. Therefore any material
    disagreement or evidence-sufficiency dispute that required follow-up remains
    HUMAN_REVIEW_REQUIRED after the bounded local actions complete.
    """

    try:
        primary = load_ai_audit_report(job_id)
        secondary = load_secondary_review_report(job_id)
        comparison = compare_review_reports(primary, secondary)
    except (FileNotFoundError, AiAuditValidationError, SecondaryReviewValidationError, ReviewComparisonError) as exc:
        raise Stage9cWorkflowError(str(exc)) from exc

    plan = plan_follow_up(comparison)
    if plan.state == AgentPlanState.NOT_REQUIRED:
        return _finalize_without_actions(job_id, comparison)

    if plan.state == AgentPlanState.HUMAN_REVIEW_REQUIRED:
        return Stage9cWorkflowResult(
            job_id=job_id,
            state=Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED,
            comparison=comparison,
            plan_state=plan.state,
            executed_actions=[],
            evidence_gathered=False,
            final_reasons=sorted(set([*comparison.follow_up_reasons, *plan.reasons])),
        )

    executed: list[AgentActionRecord] = []
    for action in plan.actions:
        # The plan schema already enforces cycle <= 2 and tool allowlist. The
        # executor performs a second fail-closed check for every action.
        executed.append(execute_agent_action(job_id, action, as_of=primary.as_of))

    evidence_gathered = any(
        action.state == AgentActionState.COMPLETED and bool(action.output_evidence_ids)
        for action in executed
    )
    failed_or_unavailable = [
        action.action_id
        for action in executed
        if action.state in {
            AgentActionState.REJECTED,
            AgentActionState.UNAVAILABLE,
            AgentActionState.FAILED,
        }
    ]
    reasons = list(comparison.follow_up_reasons)
    if evidence_gathered:
        reasons.append("BOUNDED_LOCAL_EVIDENCE_GATHERED_FOR_HUMAN_REVIEW")
    if failed_or_unavailable:
        reasons.append("FOLLOW_UP_ACTIONS_NOT_COMPLETED:" + ",".join(sorted(failed_or_unavailable)))
    reasons.append("NO_AUTOMATIC_THIRD_MODEL_ARBITRATION")

    return Stage9cWorkflowResult(
        job_id=job_id,
        state=Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED,
        comparison=comparison,
        plan_state=plan.state,
        executed_actions=executed,
        evidence_gathered=evidence_gathered,
        final_reasons=sorted(set(reasons)),
    )
