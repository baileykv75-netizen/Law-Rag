from __future__ import annotations

import hashlib
import json

from .review_comparison_models import (
    AGENT_POLICY_VERSION,
    MAX_FOLLOW_UP_CYCLES,
    AgentActionRecord,
    AgentActionState,
    AgentFollowUpDecision,
    AgentFollowUpPlan,
    AgentPlanState,
    AgentToolName,
    EvidenceSetComparisonState,
    ReviewComparisonReport,
    RiskComparisonState,
)


def _stable_action_id(job_id: str, cycle: int, tool_name: AgentToolName, payload: dict) -> str:
    raw = json.dumps(
        {
            "job_id": job_id,
            "cycle": cycle,
            "tool_name": tool_name.value,
            "payload": payload,
            "policy_version": AGENT_POLICY_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"agent-action-{digest}"


def _action(
    *,
    job_id: str,
    cycle: int,
    tool_name: AgentToolName,
    reason: str,
    arguments: dict,
    input_evidence_ids: list[str],
) -> AgentActionRecord:
    normalized_arguments = json.loads(
        json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    payload = {
        "reason": reason,
        "arguments": normalized_arguments,
        "input_evidence_ids": sorted(set(input_evidence_ids)),
    }
    return AgentActionRecord(
        action_id=_stable_action_id(job_id, cycle, tool_name, payload),
        cycle=cycle,
        tool_name=tool_name,
        state=AgentActionState.REQUESTED,
        reason=reason,
        normalized_arguments=normalized_arguments,
        input_evidence_ids=sorted(set(input_evidence_ids)),
    )


def plan_follow_up(comparison: ReviewComparisonReport) -> AgentFollowUpPlan:
    if comparison.follow_up == AgentFollowUpDecision.NOT_REQUIRED:
        return AgentFollowUpPlan(
            job_id=comparison.job_id,
            comparison_engine_version=comparison.engine_version,
            state=AgentPlanState.NOT_REQUIRED,
            actions=[],
            reasons=[],
        )

    candidates: list[tuple[int, AgentToolName, str, dict, list[str]]] = []

    for item in comparison.finding_comparisons:
        if item.follow_up != AgentFollowUpDecision.FOLLOW_UP_REQUIRED:
            continue

        contract_ids = sorted(
            set(item.contract_evidence.shared)
            | set(item.contract_evidence.primary_only)
            | set(item.contract_evidence.secondary_only)
        )
        legal_ids = sorted(
            set(item.legal_basis.shared)
            | set(item.legal_basis.primary_only)
            | set(item.legal_basis.secondary_only)
        )

        if (
            item.risk_state
            in {
                RiskComparisonState.DISAGREE_RISK_EXISTS,
                RiskComparisonState.DISAGREE_EVIDENCE_SUFFICIENCY,
                RiskComparisonState.STATE_DIFFERENCE,
            }
            or item.contract_evidence.state == EvidenceSetComparisonState.DISJOINT
        ) and contract_ids:
            candidates.append(
                (
                    10,
                    AgentToolName.INSPECT_CONTRACT_EVIDENCE,
                    f"{item.primary_finding_id}:CONTRACT_EVIDENCE_FOLLOW_UP",
                    {"primary_finding_id": item.primary_finding_id},
                    contract_ids,
                )
            )

        if item.legal_basis.state == EvidenceSetComparisonState.DISJOINT and legal_ids:
            candidates.append(
                (
                    20,
                    AgentToolName.INSPECT_LEGAL_EVIDENCE,
                    f"{item.primary_finding_id}:LEGAL_BASIS_FOLLOW_UP",
                    {
                        "primary_finding_id": item.primary_finding_id,
                        "legal_evidence_ids": legal_ids,
                    },
                    legal_ids,
                )
            )

        # Deliberately do not guess a clause_id when the comparison only says
        # "more context is needed". get_clause_context is executable only when
        # a canonical clause_id is explicitly available from a later bounded
        # action request. Guessing from a finding ID would violate the evidence
        # boundary, so this case safely falls through to human review if no
        # other grounded action exists.

    for omission in comparison.omission_comparisons:
        if omission.contract_evidence_ids:
            candidates.append(
                (
                    5,
                    AgentToolName.INSPECT_CONTRACT_EVIDENCE,
                    f"{omission.omission_id}:POSSIBLE_PRIMARY_OMISSION",
                    {"omission_id": omission.omission_id},
                    omission.contract_evidence_ids,
                )
            )
        if omission.legal_evidence_ids:
            candidates.append(
                (
                    15,
                    AgentToolName.INSPECT_LEGAL_EVIDENCE,
                    f"{omission.omission_id}:OMISSION_LEGAL_BASIS",
                    {
                        "omission_id": omission.omission_id,
                        "legal_evidence_ids": omission.legal_evidence_ids,
                    },
                    omission.legal_evidence_ids,
                )
            )

    # Deduplicate semantically identical candidate actions before applying the
    # hard two-cycle budget. Lower priority number wins.
    deduped: dict[tuple[str, str], tuple[int, AgentToolName, str, dict, list[str]]] = {}
    for candidate in sorted(candidates, key=lambda row: (row[0], row[1].value, row[2])):
        _, tool_name, _, arguments, _ = candidate
        key = (
            tool_name.value,
            json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        deduped.setdefault(key, candidate)

    selected = list(deduped.values())[:MAX_FOLLOW_UP_CYCLES]
    if not selected:
        return AgentFollowUpPlan(
            job_id=comparison.job_id,
            comparison_engine_version=comparison.engine_version,
            state=AgentPlanState.HUMAN_REVIEW_REQUIRED,
            actions=[],
            reasons=comparison.follow_up_reasons or ["FOLLOW_UP_REQUIRED_BUT_NO_SAFE_ACTION_AVAILABLE"],
        )

    actions = [
        _action(
            job_id=comparison.job_id,
            cycle=index,
            tool_name=tool_name,
            reason=reason,
            arguments=arguments,
            input_evidence_ids=input_ids,
        )
        for index, (_, tool_name, reason, arguments, input_ids) in enumerate(selected, start=1)
    ]
    return AgentFollowUpPlan(
        job_id=comparison.job_id,
        comparison_engine_version=comparison.engine_version,
        state=AgentPlanState.ACTIONS_PLANNED,
        actions=actions,
        reasons=comparison.follow_up_reasons,
    )
