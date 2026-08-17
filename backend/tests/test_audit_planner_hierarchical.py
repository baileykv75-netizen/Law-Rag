from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.audit_plan_models import (
    AuditPlanPassType,
    AuditPlanPlanningMode,
    AuditPlanningCoverageState,
    ContractType,
    ContractTypeConfidence,
    ModelAuditPlanDraft,
    ModelAuditPlanIssueDraft,
    PlannerProviderResult,
    ReviewPriority,
)
from app.audit_planner import DIRECT_PLANNER_TEXT_CHAR_LIMIT, AuditPlannerValidationError, run_audit_planner
from app.audit_planner_hierarchical import HierarchicalAuditPlannerError
from app.audit_planner_provider import AuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.models import SourceMethod
from app.pipeline_control import PipelineCancellationRequested, request_pipeline_cancel, set_provider_mode
from app.pipeline_control_models import ProviderExecutionMode
from app.storage import job_audit_plan_path, job_contract_path


class RecordingHierarchicalPlanner(AuditPlannerProvider):
    provider_name = "recording"
    model_name = "recording-hierarchical-v1"

    def __init__(self, *, cancel_after_first: bool = False, invent_id: bool = False) -> None:
        self.inputs = []
        self.cancel_after_first = cancel_after_first
        self.invent_id = invent_id

    def generate(self, planner_input) -> PlannerProviderResult:
        self.inputs.append(planner_input)
        global_mode = any(item.object_type.endswith("_INDEX_SUMMARY") for item in planner_input.contract_items)
        first = planner_input.contract_items[0] if planner_input.contract_items else None
        last = planner_input.contract_items[-1] if planner_input.contract_items else None
        issues = []
        if first is not None:
            object_ids = ["clause-invented"] if self.invent_id else [first.canonical_object_id]
            topic = "跨块履约协调" if global_mode else f"局部审查-{first.canonical_object_id}"
            if global_mode and last is not None and not self.invent_id:
                object_ids = list(dict.fromkeys([first.canonical_object_id, last.canonical_object_id]))
            issues.append(
                ModelAuditPlanIssueDraft(
                    client_issue_id=f"I-{len(self.inputs):03d}",
                    topic=topic,
                    priority=ReviewPriority.IMPORTANT,
                    why_review="fixture planning issue",
                    contract_object_ids=object_ids,
                    questions=["相关权利义务是否需要进一步审查？"],
                    retrieval_queries=["合同 权利义务 履约 审查"],
                )
            )
        draft = ModelAuditPlanDraft(
            contract_type=ContractType.SERVICE if global_mode else ContractType.UNKNOWN,
            contract_type_confidence=ContractTypeConfidence.MEDIUM if global_mode else ContractTypeConfidence.LOW,
            contract_type_reasoning="global synthesis" if global_mode else "local chunk",
            issues=issues,
        )
        content = draft.model_dump_json()
        result = PlannerProviderResult(
            provider=self.provider_name,
            model=self.model_name,
            content=content,
            raw_response_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
        if self.cancel_after_first and len(self.inputs) == 1:
            request_pipeline_cancel(planner_input.job_id)
        return result


def _prepare_contract(tmp_path: Path, monkeypatch, *, clause_count: int, body_chars: int) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    provenance = ExtractionProvenance(extractor_id="hierarchical-fixture", confidence=ExtractionConfidence.HIGH)
    clauses = []
    for index in range(1, clause_count + 1):
        body = f"本条为第{index}个完整规划对象。" + (chr(0x4E00 + (index % 100)) * body_chars)
        heading = f"第{index}条"
        title = f"测试条款{index}"
        quote = f"{heading} {title}\n{body}"
        span = SourceSpan(
            page_number=index,
            evidence_ids=[f"evidence-{index:04d}"],
            source_method=SourceMethod.NATIVE_PDF_TEXT,
            quote=quote,
            char_start=0,
            char_end=len(quote),
        )
        clauses.append(
            Clause(
                clause_id=f"clause-{index:04d}",
                heading_token=heading,
                heading_text=title,
                body_text=body,
                level=1,
                page_start=index,
                page_end=index,
                source_spans=[span],
                provenance=provenance,
            )
        )
    contract = CanonicalContract(
        job_id=uuid4(),
        filename="long-contract.pdf",
        source_fingerprint="long-contract-source",
        evidence_unit_count=clause_count,
        clauses=clauses,
    )
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(contract.job_id)
    return contract


def _canonical_text(clause: Clause) -> str:
    return "\n".join(part for part in (clause.heading_token, clause.heading_text, clause.body_text) if part).strip()


def test_long_contract_uses_hierarchical_planning_without_omitting_any_object(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare_contract(tmp_path, monkeypatch, clause_count=32, body_chars=2600)
    assert sum(len(_canonical_text(item)) for item in contract.clauses) > DIRECT_PLANNER_TEXT_CHAR_LIMIT
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    provider = RecordingHierarchicalPlanner()

    plan = run_audit_planner(contract.job_id, provider=provider)

    assert plan.planning_mode == AuditPlanPlanningMode.HIERARCHICAL
    assert plan.coverage_complete is True
    assert len(plan.coverage) == len(contract.clauses)
    assert plan.planner_passes[-1].pass_type == AuditPlanPassType.GLOBAL
    assert sum(item.pass_type == AuditPlanPassType.CHUNK for item in plan.planner_passes) >= 2
    assert len(provider.inputs) == len(plan.planner_passes)
    assert plan.contract_type == ContractType.SERVICE
    assert job_audit_plan_path(contract.job_id).exists()

    expected = {item.clause_id: _canonical_text(item) for item in contract.clauses}
    locally_seen: dict[str, str] = {}
    for planner_input in provider.inputs:
        if any(item.object_type.endswith("_INDEX_SUMMARY") for item in planner_input.contract_items):
            continue
        for item in planner_input.contract_items:
            assert item.canonical_object_id not in locally_seen
            locally_seen[item.canonical_object_id] = item.text
    assert locally_seen == expected

    coverage = {item.canonical_object_id: item for item in plan.coverage}
    assert set(coverage) == set(expected)
    assert all(item.chunk_ids for item in coverage.values())
    assert all(
        item.state in {
            AuditPlanningCoverageState.REVIEWED_WITH_ISSUE,
            AuditPlanningCoverageState.REVIEWED_NO_SPECIFIC_ISSUE,
        }
        for item in coverage.values()
    )
    assert any(item.state == AuditPlanningCoverageState.REVIEWED_NO_SPECIFIC_ISSUE for item in coverage.values())

    global_input = provider.inputs[-1]
    assert all(item.object_type.endswith("_INDEX_SUMMARY") for item in global_input.contract_items)
    assert {item.canonical_object_id for item in global_input.contract_items} == set(expected)
    assert any(fact.fact_type == "LOCAL_PLANNER_ISSUE" for fact in global_input.global_facts)


def test_short_contract_records_direct_coverage_with_one_pass(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare_contract(tmp_path, monkeypatch, clause_count=3, body_chars=300)
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    provider = RecordingHierarchicalPlanner()

    plan = run_audit_planner(contract.job_id, provider=provider)

    assert plan.planning_mode == AuditPlanPlanningMode.DIRECT
    assert plan.coverage_complete is True
    assert len(plan.planner_passes) == 1
    assert plan.planner_passes[0].pass_type == AuditPlanPassType.DIRECT
    assert len(plan.coverage) == 3
    assert len(provider.inputs) == 1


def test_cancel_after_first_chunk_blocks_every_later_planner_pass(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare_contract(tmp_path, monkeypatch, clause_count=30, body_chars=2600)
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    provider = RecordingHierarchicalPlanner(cancel_after_first=True)

    with pytest.raises(PipelineCancellationRequested):
        run_audit_planner(contract.job_id, provider=provider)

    assert len(provider.inputs) == 1
    assert not job_audit_plan_path(contract.job_id).exists()


def test_invalid_local_chunk_output_stops_before_global_and_is_not_persisted(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare_contract(tmp_path, monkeypatch, clause_count=30, body_chars=2600)
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    provider = RecordingHierarchicalPlanner(invent_id=True)

    with pytest.raises(AuditPlannerValidationError, match="unknown canonical object"):
        run_audit_planner(contract.job_id, provider=provider)

    assert len(provider.inputs) == 1
    assert not job_audit_plan_path(contract.job_id).exists()


def test_single_canonical_object_is_never_silently_split_or_truncated(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare_contract(
        tmp_path,
        monkeypatch,
        clause_count=1,
        body_chars=DIRECT_PLANNER_TEXT_CHAR_LIMIT + 100,
    )
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    provider = RecordingHierarchicalPlanner()

    with pytest.raises(HierarchicalAuditPlannerError, match="did not truncate"):
        run_audit_planner(contract.job_id, provider=provider)

    assert provider.inputs == []
    assert not job_audit_plan_path(contract.job_id).exists()
