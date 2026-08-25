from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.ai_audit_models import ProviderAuditResult, ProviderHealth
from app.audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanPlanningMode,
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ReviewPriority,
)
from app.audit_rules import run_audit_rules
from app.contract_models import (
    CanonicalContract,
    Clause,
    ExtractionConfidence,
    ExtractionProvenance,
    SourceSpan,
)
from app.issue_legal_context import build_issue_legal_context
from app.issue_primary_audit import (
    IssuePrimaryAuditValidationError,
    build_issue_primary_contexts,
    load_issue_primary_audit,
    run_issue_primary_audit,
    validate_issue_model_output,
)
from app.issue_primary_audit_models import (
    IssuePrimaryGlobalFact,
    IssuePrimaryAuditState,
    IssuePrimaryAuditStatus,
    ModelIssuePrimaryAuditDraft,
)
from app.issue_primary_audit_provider import IssuePrimaryAuditProvider, IssuePrimaryAuditProviderError
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.main import app
from app.models import SourceMethod
from app.pipeline_control import (
    PipelineCancellationRequested,
    clear_pipeline_cancel,
    ensure_pipeline_control,
    request_pipeline_cancel,
)
from app.pipeline_control_models import ProviderExecutionMode
from app.storage import job_audit_plan_path, job_contract_path

client = TestClient(app)


def _seed_legal(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    legal_db = tmp_path / "legal" / "legal.db"
    index_db = tmp_path / "legal" / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True)
    build_retrieval_index(legal_db, index_db)


def _span(page: int, evidence_id: str, quote: str) -> SourceSpan:
    return SourceSpan(
        page_number=page,
        evidence_ids=[evidence_id],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )


def _prepare(tmp_path: Path, monkeypatch, *, include_no_hit: bool = False):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")
    _seed_legal(tmp_path)
    job_id = uuid4()
    provenance = ExtractionProvenance(
        extractor_id="stage13e-test",
        confidence=ExtractionConfidence.HIGH,
    )
    contract = CanonicalContract(
        job_id=job_id,
        filename="stage13e-fixture.pdf",
        source_fingerprint="stage13e-source-fp",
        evidence_unit_count=2,
        clauses=[
            Clause(
                clause_id="clause-001",
                heading_token="第一条",
                heading_text="价款与支付",
                body_text="合同价款为100万元，甲方在验收后十日内支付。",
                level=1,
                page_start=1,
                page_end=1,
                source_spans=[_span(1, "contract-evidence-001", "第一条 价款与支付 合同价款为100万元，甲方在验收后十日内支付。")],
                provenance=provenance,
            ),
            Clause(
                clause_id="clause-002",
                heading_token="第二条",
                heading_text="违约责任",
                body_text="乙方逾期交付的，每日按合同总价5%支付违约金。",
                level=1,
                page_start=1,
                page_end=1,
                source_spans=[_span(1, "contract-evidence-002", "第二条 违约责任 乙方逾期交付的，每日按合同总价5%支付违约金。")],
                provenance=provenance,
            ),
        ],
    )
    job_contract_path(job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    rules = run_audit_rules(job_id)

    issues = [
        AuditPlanIssue(
            issue_id="issue-payment",
            topic="价款与结算",
            priority=ReviewPriority.IMPORTANT,
            sources=[AuditPlanSource.BASELINE],
            why_review=["baseline coverage fixture"],
            contract_object_ids=[],
            contract_evidence_ids=[],
            questions=["付款触发条件和期限是否明确？"],
            retrieval_queries=["合同 价款 支付 履行"],
        ),
        AuditPlanIssue(
            issue_id="issue-penalty",
            topic="违约责任",
            priority=ReviewPriority.HIGH_ATTENTION,
            sources=[AuditPlanSource.LLM_DYNAMIC],
            why_review=["5% per day may require review"],
            contract_object_ids=["clause-002"],
            contract_evidence_ids=["contract-evidence-002"],
            questions=["违约金安排是否需要调整？"],
            retrieval_queries=["民法典第五百八十五条 违约金"],
        ),
    ]
    if include_no_hit:
        issues.append(
            AuditPlanIssue(
                issue_id="issue-no-hit",
                topic="特殊商业安排",
                priority=ReviewPriority.NORMAL,
                sources=[AuditPlanSource.LLM_DYNAMIC],
                contract_object_ids=["clause-001"],
                contract_evidence_ids=["contract-evidence-001"],
                questions=["该特殊安排是否存在合同层面风险？"],
                retrieval_queries=["火星殖民量子银河专属法律规则"],
            )
        )
    plan = AuditPlan(
        job_id=job_id,
        contract_type=ContractType.PURCHASE,
        contract_type_confidence=ContractTypeConfidence.MEDIUM,
        contract_type_reasoning="fixture",
        provider="fixture",
        model="fixture",
        contract_source_fingerprint=contract.source_fingerprint,
        contract_content_fingerprint=rules.contract_content_fingerprint,
        planner_input_fingerprint="fixture-input",
        planner_response_hash="fixture-response",
        planning_mode=AuditPlanPlanningMode.DIRECT,
        coverage_complete=True,
        issues=issues,
    )
    job_audit_plan_path(job_id).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    legal_context = build_issue_legal_context(job_id, as_of=date(2026, 8, 15), use_semantic=False)
    ensure_pipeline_control(job_id, ProviderExecutionMode.AUTO_CONTINUE)
    return job_id, plan, legal_context


def test_every_planned_issue_gets_one_terminal_result_and_baseline_fallback_selects_contract_text(tmp_path: Path, monkeypatch) -> None:
    job_id, plan, _ = _prepare(tmp_path, monkeypatch)
    contexts = build_issue_primary_contexts(job_id)
    payment = next(item for item in contexts if item.issue_id == "issue-payment")
    assert payment.target_selection_method.value == "DETERMINISTIC_CONTRACT_RETRIEVAL"
    assert any(item.canonical_object_id == "clause-001" for item in payment.target_items)

    artifact = run_issue_primary_audit(job_id, provider_name="fake")
    assert artifact.status == IssuePrimaryAuditStatus.COMPLETE
    assert artifact.total_issue_count == len(plan.issues)
    assert artifact.completed_issue_count == len(plan.issues)
    assert {result.issue_id for result in artifact.results} == {issue.issue_id for issue in plan.issues}
    assert len(artifact.provider_calls) == len(plan.issues)


def test_model_cannot_invent_contract_or_legal_evidence_ids(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch)
    context = next(item for item in build_issue_primary_contexts(job_id) if item.issue_id == "issue-penalty")
    legal_id = context.legal_evidence[0].legal_evidence_id
    draft = ModelIssuePrimaryAuditDraft(
        state=IssuePrimaryAuditState.SUPPORTED_FINDING,
        legal_conclusion=True,
        risk_category="违约责任",
        severity="HIGH",
        title="fixture",
        reasoning_summary="fixture",
        suggestion="fixture",
        canonical_object_ids=["clause-invented"],
        contract_evidence_ids=["contract-evidence-invented"],
        legal_evidence_ids=[legal_id + "-invented"],
    )
    with pytest.raises(IssuePrimaryAuditValidationError, match="unsupplied canonical object"):
        validate_issue_model_output(draft.model_dump_json(), context)


def test_primary_model_fact_id_in_canonical_objects_is_coerced_to_evidence(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch)
    context = next(item for item in build_issue_primary_contexts(job_id) if item.issue_id == "issue-penalty")
    context = context.model_copy(
        update={
            "global_facts": [
                IssuePrimaryGlobalFact(
                    fact_id="title-001",
                    fact_type="TITLE",
                    label="contract_title",
                    value="设备采购框架协议",
                    evidence_ids=["contract-evidence-001"],
                )
            ]
        }
    )
    legal_id = context.legal_evidence[0].legal_evidence_id
    draft = ModelIssuePrimaryAuditDraft(
        state=IssuePrimaryAuditState.SUPPORTED_FINDING,
        legal_conclusion=True,
        risk_category="合同标题相关风险",
        severity="LOW",
        title="标题事实被降级为证据",
        reasoning_summary="fixture",
        suggestion="fixture",
        canonical_object_ids=["title-001"],
        contract_evidence_ids=[],
        legal_evidence_ids=[legal_id],
    )

    result = validate_issue_model_output(draft.model_dump_json(), context)

    assert result.canonical_object_ids == []
    assert result.contract_evidence_ids == ["contract-evidence-001"]
    assert "CANONICAL_OBJECT_FACT_ID_COERCED_TO_EVIDENCE" in result.review_reasons


def test_no_material_risk_without_required_evidence_is_downgraded_to_review(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch, include_no_hit=True)
    context = next(item for item in build_issue_primary_contexts(job_id) if item.issue_id == "issue-no-hit")
    assert context.legal_support_state.value == "NO_MATCH_IN_LOCAL_CORPUS"
    target = context.target_items[0]
    draft = ModelIssuePrimaryAuditDraft(
        state=IssuePrimaryAuditState.NO_MATERIAL_RISK_FOUND,
        legal_conclusion=False,
        risk_category=context.topic,
        severity="INFO",
        title="未发现风险",
        reasoning_summary="fixture",
        suggestion="fixture",
        canonical_object_ids=[target.canonical_object_id],
        contract_evidence_ids=target.evidence_ids[:1],
        legal_evidence_ids=[],
    )
    result = validate_issue_model_output(draft.model_dump_json(), context)
    assert result.state == IssuePrimaryAuditState.REVIEW_REQUIRED
    assert result.legal_conclusion is False
    assert "NO_MATERIAL_RISK_MISSING_REQUIRED_EVIDENCE" in result.review_reasons


def test_contract_only_supported_finding_is_allowed_without_false_legal_claim(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch, include_no_hit=True)
    context = next(item for item in build_issue_primary_contexts(job_id) if item.issue_id == "issue-no-hit")
    target = context.target_items[0]
    draft = ModelIssuePrimaryAuditDraft(
        state=IssuePrimaryAuditState.SUPPORTED_FINDING,
        legal_conclusion=False,
        risk_category="合同表述风险",
        severity="MEDIUM",
        title="付款安排需要澄清",
        reasoning_summary="仅依据合同文字指出表述或商业风险，不主张具体法律结论。",
        suggestion="明确触发条件和期限。",
        canonical_object_ids=[target.canonical_object_id],
        contract_evidence_ids=target.evidence_ids[:1],
        legal_evidence_ids=[],
    )
    result = validate_issue_model_output(draft.model_dump_json(), context)
    assert result.state == IssuePrimaryAuditState.SUPPORTED_FINDING
    assert result.legal_conclusion is False
    assert result.legal_evidence_ids == []
    assert result.evidence_sufficiency.value == "INSUFFICIENT_LEGAL_CORPUS"


class CancelAfterFirstProvider(IssuePrimaryAuditProvider):
    provider_name = "test-cancel"
    model_name = "test-cancel-v1"

    def __init__(self, job_id):
        self.job_id = job_id
        self.calls = 0

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, configured=True, model=self.model_name, detail="fixture")

    def generate(self, context) -> ProviderAuditResult:
        self.calls += 1
        target = context.target_items[0]
        legal = context.legal_evidence[0] if context.legal_evidence else None
        draft = ModelIssuePrimaryAuditDraft(
            state=IssuePrimaryAuditState.SUPPORTED_FINDING if legal else IssuePrimaryAuditState.INSUFFICIENT_EVIDENCE,
            legal_conclusion=bool(legal),
            risk_category=context.topic,
            severity="MEDIUM" if legal else "INFO",
            title="fixture",
            reasoning_summary="fixture",
            suggestion="fixture",
            canonical_object_ids=[target.canonical_object_id],
            contract_evidence_ids=target.evidence_ids[:1],
            legal_evidence_ids=[legal.legal_evidence_id] if legal else [],
        )
        if self.calls == 1:
            request_pipeline_cancel(self.job_id)
        content = draft.model_dump_json()
        return ProviderAuditResult(provider=self.provider_name, model=self.model_name, content=content, raw_response_hash=f"hash-{self.calls}")


class ResumeSameProvider(IssuePrimaryAuditProvider):
    provider_name = "test-cancel"
    model_name = "test-cancel-v1"

    def __init__(self):
        self.calls = 0

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, configured=True, model=self.model_name, detail="fixture")

    def generate(self, context) -> ProviderAuditResult:
        self.calls += 1
        target = context.target_items[0]
        legal = context.legal_evidence[0] if context.legal_evidence else None
        draft = ModelIssuePrimaryAuditDraft(
            state=IssuePrimaryAuditState.SUPPORTED_FINDING if legal else IssuePrimaryAuditState.INSUFFICIENT_EVIDENCE,
            legal_conclusion=bool(legal),
            risk_category=context.topic,
            severity="MEDIUM" if legal else "INFO",
            title="resume fixture",
            reasoning_summary="resume fixture",
            suggestion="resume fixture",
            canonical_object_ids=[target.canonical_object_id],
            contract_evidence_ids=target.evidence_ids[:1],
            legal_evidence_ids=[legal.legal_evidence_id] if legal else [],
        )
        content = draft.model_dump_json()
        return ProviderAuditResult(
            provider=self.provider_name,
            model=self.model_name,
            content=content,
            raw_response_hash=f"resume-hash-{self.calls}",
        )


class TruncateFirstProvider(ResumeSameProvider):
    provider_name = "test-truncated"
    model_name = "test-truncated-v1"

    def generate(self, context) -> ProviderAuditResult:
        self.calls += 1
        if self.calls == 1:
            raise IssuePrimaryAuditProviderError(
                "fixture truncated",
                code="DEEPSEEK_PRIMARY_OUTPUT_TRUNCATED",
                recoverable=True,
            )
        target = context.target_items[0]
        legal = context.legal_evidence[0] if context.legal_evidence else None
        draft = ModelIssuePrimaryAuditDraft(
            state=IssuePrimaryAuditState.SUPPORTED_FINDING if legal else IssuePrimaryAuditState.INSUFFICIENT_EVIDENCE,
            legal_conclusion=bool(legal),
            risk_category=context.topic,
            severity="MEDIUM" if legal else "INFO",
            title="post-truncation fixture",
            reasoning_summary="post-truncation fixture",
            suggestion="post-truncation fixture",
            canonical_object_ids=[target.canonical_object_id],
            contract_evidence_ids=target.evidence_ids[:1],
            legal_evidence_ids=[legal.legal_evidence_id] if legal else [],
        )
        content = draft.model_dump_json()
        return ProviderAuditResult(
            provider=self.provider_name,
            model=self.model_name,
            content=content,
            raw_response_hash=f"post-truncation-hash-{self.calls}",
        )


def test_cancellation_between_issues_checkpoints_completed_work_without_false_complete(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch)
    provider = CancelAfterFirstProvider(job_id)
    with pytest.raises(PipelineCancellationRequested):
        run_issue_primary_audit(job_id, provider_override=provider)

    artifact = load_issue_primary_audit(job_id, validate_freshness=False)
    assert artifact.status == IssuePrimaryAuditStatus.INTERRUPTED
    assert artifact.completed_issue_count == 1
    assert artifact.total_issue_count == 2
    assert len(artifact.results) == 1
    assert len(artifact.provider_calls) == 1
    assert provider.calls == 1


def test_resume_reuses_completed_issue_and_calls_provider_only_for_remaining_issue(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch)
    first = CancelAfterFirstProvider(job_id)
    with pytest.raises(PipelineCancellationRequested):
        run_issue_primary_audit(job_id, provider_override=first)
    assert first.calls == 1

    clear_pipeline_cancel(job_id)
    resumed_provider = ResumeSameProvider()
    artifact = run_issue_primary_audit(job_id, provider_override=resumed_provider)

    assert artifact.status == IssuePrimaryAuditStatus.COMPLETE
    assert artifact.completed_issue_count == 2
    assert len(artifact.results) == 2
    assert len(artifact.provider_calls) == 2
    assert resumed_provider.calls == 1
    assert artifact.provider_calls[0].raw_response_hash == "hash-1"
    assert artifact.provider_calls[1].raw_response_hash == "resume-hash-1"


def test_truncated_primary_provider_output_records_review_required_and_continues(tmp_path: Path, monkeypatch) -> None:
    job_id, _, _ = _prepare(tmp_path, monkeypatch)
    provider = TruncateFirstProvider()

    artifact = run_issue_primary_audit(job_id, provider_override=provider)

    assert artifact.status == IssuePrimaryAuditStatus.COMPLETE
    assert artifact.completed_issue_count == 2
    assert provider.calls == 2
    assert len(artifact.provider_calls) == 1
    truncated = artifact.results[0]
    assert truncated.state == IssuePrimaryAuditState.REVIEW_REQUIRED
    assert truncated.legal_conclusion is False
    assert truncated.legal_evidence_ids == []
    assert "PRIMARY_PROVIDER_OUTPUT_TRUNCATED" in truncated.review_reasons
    assert artifact.provider_calls[0].raw_response_hash == "post-truncation-hash-2"


def test_stage13d_and_stage13e_routes_are_reachable_from_main_app(tmp_path: Path, monkeypatch) -> None:
    _prepare(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/documents/{job_id}/issue-legal-context" in paths
    assert "/api/documents/{job_id}/issue-primary-audit" in paths
