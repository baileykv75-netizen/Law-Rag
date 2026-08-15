from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_policy import plan_follow_up
from app.ai_audit_models import FindingSeverity
from app.review_comparison_models import (
    AgentActionRecord,
    AgentActionState,
    AgentFollowUpDecision,
    AgentPlanState,
    AgentToolName,
    EvidenceSetComparison,
    EvidenceSetComparisonState,
    FindingComparison,
    OverallComparisonState,
    ReviewComparisonReport,
    RiskComparisonState,
    SeverityComparison,
    SeverityComparisonState,
)


def _comparison(
    *,
    risk_state: RiskComparisonState = RiskComparisonState.AGREE_SUPPORTED,
    overall: OverallComparisonState = OverallComparisonState.AGREEMENT,
    follow_up: AgentFollowUpDecision = AgentFollowUpDecision.NOT_REQUIRED,
    contract_state: EvidenceSetComparisonState = EvidenceSetComparisonState.AGREE,
    legal_state: EvidenceSetComparisonState = EvidenceSetComparisonState.AGREE,
    material_reasons: list[str] | None = None,
) -> FindingComparison:
    return FindingComparison(
        comparison_id="comparison-001",
        primary_finding_id="finding-001",
        risk_state=risk_state,
        severity=SeverityComparison(
            primary=FindingSeverity.HIGH,
            secondary=FindingSeverity.HIGH,
            distance=0,
            state=SeverityComparisonState.AGREE,
        ),
        contract_evidence=EvidenceSetComparison(
            state=contract_state,
            shared=["E-1"] if contract_state == EvidenceSetComparisonState.AGREE else [],
            primary_only=["E-1"] if contract_state == EvidenceSetComparisonState.DISJOINT else [],
            secondary_only=["E-2"] if contract_state == EvidenceSetComparisonState.DISJOINT else [],
        ),
        legal_basis=EvidenceSetComparison(
            state=legal_state,
            shared=["L-1"] if legal_state == EvidenceSetComparisonState.AGREE else [],
            primary_only=["L-1"] if legal_state == EvidenceSetComparisonState.DISJOINT else [],
            secondary_only=["L-2"] if legal_state == EvidenceSetComparisonState.DISJOINT else [],
        ),
        overall_state=overall,
        material_reasons=material_reasons or [],
        follow_up=follow_up,
    )


def _report(items: list[FindingComparison], *, follow_up: AgentFollowUpDecision) -> ReviewComparisonReport:
    return ReviewComparisonReport(
        job_id="job-001",
        primary_context_fingerprint="primary-fp",
        secondary_context_fingerprint="secondary-fp",
        finding_comparisons=items,
        omission_comparisons=[],
        overall_state=(
            OverallComparisonState.MATERIAL_DISAGREEMENT
            if follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED
            else OverallComparisonState.AGREEMENT
        ),
        follow_up=follow_up,
        follow_up_reasons=["finding-001:RISK_EXISTENCE_CONFLICT"] if follow_up == AgentFollowUpDecision.FOLLOW_UP_REQUIRED else [],
    )


def test_agreement_creates_no_agent_actions() -> None:
    plan = plan_follow_up(_report([_comparison()], follow_up=AgentFollowUpDecision.NOT_REQUIRED))

    assert plan.state == AgentPlanState.NOT_REQUIRED
    assert plan.actions == []


def test_risk_conflict_plans_contract_evidence_inspection() -> None:
    item = _comparison(
        risk_state=RiskComparisonState.DISAGREE_RISK_EXISTS,
        overall=OverallComparisonState.MATERIAL_DISAGREEMENT,
        follow_up=AgentFollowUpDecision.FOLLOW_UP_REQUIRED,
        material_reasons=["RISK_EXISTENCE_CONFLICT"],
    )
    plan = plan_follow_up(_report([item], follow_up=AgentFollowUpDecision.FOLLOW_UP_REQUIRED))

    assert plan.state == AgentPlanState.ACTIONS_PLANNED
    assert plan.actions[0].tool_name == AgentToolName.INSPECT_CONTRACT_EVIDENCE
    assert plan.actions[0].input_evidence_ids == ["E-1"]
    assert plan.actions[0].state == AgentActionState.REQUESTED


def test_disjoint_contract_and_legal_evidence_still_respects_two_cycle_budget() -> None:
    item = _comparison(
        risk_state=RiskComparisonState.DISAGREE_RISK_EXISTS,
        overall=OverallComparisonState.MATERIAL_DISAGREEMENT,
        follow_up=AgentFollowUpDecision.FOLLOW_UP_REQUIRED,
        contract_state=EvidenceSetComparisonState.DISJOINT,
        legal_state=EvidenceSetComparisonState.DISJOINT,
        material_reasons=["RISK_EXISTENCE_CONFLICT", "LEGAL_BASIS_DISJOINT", "CONTRACT_EVIDENCE_DISJOINT"],
    )
    plan = plan_follow_up(_report([item], follow_up=AgentFollowUpDecision.FOLLOW_UP_REQUIRED))

    assert len(plan.actions) == 2
    assert [action.cycle for action in plan.actions] == [1, 2]
    assert {action.tool_name for action in plan.actions} == {
        AgentToolName.INSPECT_CONTRACT_EVIDENCE,
        AgentToolName.INSPECT_LEGAL_EVIDENCE,
    }


def test_action_schema_rejects_forbidden_tool_and_third_cycle() -> None:
    common = dict(
        action_id="agent-action-x",
        state=AgentActionState.REQUESTED,
        reason="test",
    )
    with pytest.raises(ValidationError):
        AgentActionRecord(cycle=1, tool_name="run_shell", **common)
    with pytest.raises(ValidationError):
        AgentActionRecord(cycle=3, tool_name=AgentToolName.INSPECT_CONTRACT_EVIDENCE, **common)
