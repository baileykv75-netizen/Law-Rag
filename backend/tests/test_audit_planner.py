from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.audit_plan_models import (
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ModelAuditPlanDraft,
    ModelAuditPlanIssueDraft,
    PlannerProviderResult,
    ReviewPriority,
)
from app.audit_planner import (
    DIRECT_PLANNER_TEXT_CHAR_LIMIT,
    AuditPlannerSizeError,
    AuditPlannerValidationError,
    build_planner_input,
    merge_audit_plan,
    run_audit_planner,
)
from app.audit_planner_provider import AuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.models import SourceMethod
from app.pipeline_control import PipelineCancellationRequested, ProviderBoundaryPaused, request_pipeline_cancel, set_provider_mode
from app.pipeline_control_models import ProviderExecutionMode
from app.storage import job_audit_plan_path, job_contract_path


class StaticPlanner(AuditPlannerProvider):
    provider_name = "static"
    model_name = "static-planner-v1"

    def __init__(self, draft: ModelAuditPlanDraft) -> None:
        self.draft = draft
        self.calls = 0

    def generate(self, planner_input) -> PlannerProviderResult:
        self.calls += 1
        content = self.draft.model_dump_json()
        return PlannerProviderResult(
            provider=self.provider_name,
            model=self.model_name,
            content=content,
            raw_response_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )


def _contract(*, body: str | None = None) -> CanonicalContract:
    job_id = uuid4()
    provenance = ExtractionProvenance(extractor_id="planner-fixture", confidence=ExtractionConfidence.HIGH)
    text = body or "乙方逾期履行的，应按合同金额的50%支付违约金。双方另行协商数据接口和成果归属。"
    quote = f"第八条 违约责任\n{text}"
    span = SourceSpan(
        page_number=2,
        evidence_ids=["evidence-clause-8"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )
    return CanonicalContract(
        job_id=job_id,
        filename="planner-fixture.pdf",
        source_fingerprint="planner-source-fingerprint",
        evidence_unit_count=1,
        clauses=[
            Clause(
                clause_id="clause-008",
                heading_token="第八条",
                heading_text="违约责任",
                body_text=text,
                level=1,
                page_start=2,
                page_end=2,
                source_spans=[span],
                provenance=provenance,
            )
        ],
    )


def _prepare(tmp_path: Path, monkeypatch, *, body: str | None = None) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    contract = _contract(body=body)
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(contract.job_id)
    return contract


def _draft(
    *,
    contract_type: ContractType = ContractType.UNKNOWN,
    issues: list[ModelAuditPlanIssueDraft] | None = None,
) -> ModelAuditPlanDraft:
    return ModelAuditPlanDraft(
        contract_type=contract_type,
        contract_type_confidence=ContractTypeConfidence.LOW,
        contract_type_reasoning="fixture classification",
        issues=issues or [],
    )


def test_baseline_rule_hint_legacy_hint_and_dynamic_issue_all_survive(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)

    dynamic = ModelAuditPlanIssueDraft(
        client_issue_id="D-001",
        topic="数据与成果归属特别安排",
        priority=ReviewPriority.HIGH_ATTENTION,
        why_review="合同出现数据接口与成果归属安排，超出旧关键词主题范围。",
        contract_object_ids=["clause-008"],
        questions=["数据接口成果、使用权和后续利用边界是否明确？"],
        retrieval_queries=["合同 数据 成果归属 知识产权"],
    )
    plan = run_audit_planner(contract.job_id, provider=StaticPlanner(_draft(issues=[dynamic])))

    topics = {item.topic: item for item in plan.issues}
    assert "合同主体与授权" in topics  # baseline cannot be removed by the model
    assert "违约金" in topics  # legacy topic now contributes a deterministic hint
    assert "数据与成果归属特别安排" in topics  # dynamic issues are not capped by legacy topics
    assert any(item.topic.startswith("确定性异常：") for item in plan.issues)  # missing parties/profile survives
    assert AuditPlanSource.LLM_DYNAMIC in topics["数据与成果归属特别安排"].sources
    assert topics["数据与成果归属特别安排"].contract_evidence_ids == ["evidence-clause-8"]
    assert plan.contract_type == ContractType.UNKNOWN
    assert job_audit_plan_path(contract.job_id).exists()


@pytest.mark.parametrize("contract_type", [ContractType.UNKNOWN, ContractType.MIXED])
def test_unknown_and_mixed_contract_types_keep_general_baseline(tmp_path: Path, monkeypatch, contract_type: ContractType) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    planner_input = build_planner_input(contract.job_id)
    content = _draft(contract_type=contract_type).model_dump_json()
    result = PlannerProviderResult(
        provider="fixture",
        model="fixture",
        content=content,
        raw_response_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
    plan = merge_audit_plan(planner_input, _draft(contract_type=contract_type), result)
    assert "合同主体与授权" in {item.topic for item in plan.issues}
    assert any("GENERAL baseline" in warning for warning in plan.warnings)


def test_planner_rejects_unknown_canonical_object_id(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    bad = ModelAuditPlanIssueDraft(
        client_issue_id="BAD-ID",
        topic="动态问题",
        priority=ReviewPriority.IMPORTANT,
        why_review="fixture",
        contract_object_ids=["clause-invented"],
        questions=["是否需要审查？"],
        retrieval_queries=["合同 动态问题"],
    )
    with pytest.raises(AuditPlannerValidationError, match="unknown canonical object"):
        run_audit_planner(contract.job_id, provider=StaticPlanner(_draft(issues=[bad])))
    assert not job_audit_plan_path(contract.job_id).exists()


def test_duplicate_dynamic_topics_merge_predictably(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    planner_input = build_planner_input(contract.job_id)
    first = ModelAuditPlanIssueDraft(
        client_issue_id="D-1",
        topic="特殊数据安排",
        priority=ReviewPriority.NORMAL,
        why_review="reason one",
        contract_object_ids=["clause-008"],
        questions=["question one"],
        retrieval_queries=["query one"],
    )
    second = ModelAuditPlanIssueDraft(
        client_issue_id="D-2",
        topic=" 特殊数据安排 ",
        priority=ReviewPriority.HIGH_ATTENTION,
        why_review="reason two",
        contract_object_ids=["clause-008"],
        questions=["question two"],
        retrieval_queries=["query two"],
    )
    draft = _draft(issues=[first, second])
    content = draft.model_dump_json()
    plan = merge_audit_plan(
        planner_input,
        draft,
        PlannerProviderResult(
            provider="fixture",
            model="fixture",
            content=content,
            raw_response_hash=hashlib.sha256(content.encode()).hexdigest(),
        ),
    )
    merged = [item for item in plan.issues if item.topic == "特殊数据安排"]
    assert len(merged) == 1
    assert merged[0].priority == ReviewPriority.HIGH_ATTENTION
    assert merged[0].questions == ["question one", "question two"]
    assert merged[0].retrieval_queries == ["query one", "query two"]


def test_dynamic_issue_requires_retrieval_query(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    planner_input = build_planner_input(contract.job_id)
    issue = ModelAuditPlanIssueDraft(
        client_issue_id="NO-QUERY",
        topic="缺少查询",
        priority=ReviewPriority.NORMAL,
        why_review="fixture",
        contract_object_ids=[],
        questions=["是否需要审查？"],
        retrieval_queries=[],
    )
    draft = _draft(issues=[issue])
    content = draft.model_dump_json()
    with pytest.raises(AuditPlannerValidationError, match="no retrieval queries"):
        merge_audit_plan(
            planner_input,
            draft,
            PlannerProviderResult(
                provider="fixture",
                model="fixture",
                content=content,
                raw_response_hash=hashlib.sha256(content.encode()).hexdigest(),
            ),
        )


def test_direct_planner_never_silently_truncates_long_contract(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch, body="甲" * (DIRECT_PLANNER_TEXT_CHAR_LIMIT + 1))
    with pytest.raises(AuditPlannerSizeError) as captured:
        build_planner_input(contract.job_id)
    assert captured.value.total_text_chars > DIRECT_PLANNER_TEXT_CHAR_LIMIT
    assert captured.value.code == "HIERARCHICAL_PLANNING_REQUIRED"


def test_new_planner_call_defaults_to_provider_approval_boundary(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    provider = StaticPlanner(_draft())
    with pytest.raises(ProviderBoundaryPaused, match="明确确认"):
        run_audit_planner(contract.job_id, provider=provider)
    assert provider.calls == 0


def test_local_only_and_cancel_cannot_be_bypassed_by_planner(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    provider = StaticPlanner(_draft())
    set_provider_mode(contract.job_id, ProviderExecutionMode.LOCAL_ONLY)
    with pytest.raises(ProviderBoundaryPaused):
        run_audit_planner(contract.job_id, provider=provider)
    assert provider.calls == 0

    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)
    request_pipeline_cancel(contract.job_id)
    with pytest.raises(PipelineCancellationRequested):
        run_audit_planner(contract.job_id, provider=provider)
    assert provider.calls == 0
