from __future__ import annotations

from uuid import uuid4

import pytest

from app.ai_audit_models import FindingSeverity, ProviderAuditResult, ProviderHealth
from app.audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ReviewPriority,
)
from app.issue_legal_context_models import IssueLegalSupportState
from app.issue_primary_audit_models import (
    IssueContextRelation,
    IssueEvidenceSufficiency,
    IssuePrimaryAuditArtifact,
    IssuePrimaryAuditContext,
    IssuePrimaryAuditResult,
    IssuePrimaryAuditState,
    IssuePrimaryAuditStatus,
    IssuePrimaryContractItem,
)
from app.issue_secondary_review import (
    IssueSecondaryReviewValidationError,
    load_issue_secondary_review,
    run_issue_secondary_review,
    validate_issue_secondary_output,
)
from app.issue_secondary_review_models import (
    ModelIssueSecondaryDraft,
    SecondaryCoverageAssessment,
    SecondaryIssueAssessment,
)
from app.issue_secondary_review_provider import IssueSecondaryReviewProvider
from app.pipeline_control import PipelineCancellationRequested, clear_pipeline_cancel, request_pipeline_cancel


class FixtureSecondaryProvider(IssueSecondaryReviewProvider):
    provider_name = "fixture-kimi"
    model_name = "fixture-kimi-v1"

    def __init__(self, *, cancel_after: int | None = None) -> None:
        self.calls: list[str] = []
        self.cancel_after = cancel_after

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, configured=True, model=self.model_name, detail="fixture")

    def generate(self, context, primary) -> ProviderAuditResult:
        self.calls.append(context.issue_id)
        draft = ModelIssueSecondaryDraft(
            issue_id=context.issue_id,
            assessment=SecondaryIssueAssessment.SUPPORTED,
            coverage_assessment=SecondaryCoverageAssessment.COVERED,
            severity=primary.severity,
            reasoning_summary="fixture independent review",
            suggestion="fixture suggestion",
            contract_evidence_ids=primary.contract_evidence_ids,
            legal_evidence_ids=primary.legal_evidence_ids,
        )
        content = draft.model_dump_json()
        if self.cancel_after is not None and len(self.calls) == self.cancel_after:
            request_pipeline_cancel(context.job_id)
        return ProviderAuditResult(provider=self.provider_name, model=self.model_name, content=content, raw_response_hash=f"hash-{context.issue_id}")


def _context(job_id, issue_id: str, *, legal_state: IssueLegalSupportState = IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS, text: str = "合同条款正文") -> IssuePrimaryAuditContext:
    return IssuePrimaryAuditContext(
        job_id=job_id,
        issue_id=issue_id,
        topic=f"topic-{issue_id}",
        priority=ReviewPriority.IMPORTANT,
        sources=[AuditPlanSource.BASELINE],
        why_review=["fixture"],
        questions=["是否充分审查？"],
        as_of="2026-08-18",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        audit_plan_fingerprint="plan-fp",
        issue_legal_context_fingerprint="legal-fp",
        legal_support_state=legal_state,
        target_selection_method="EXPLICIT_PLAN",
        target_items=[
            IssuePrimaryContractItem(
                canonical_object_id=f"clause-{issue_id}",
                object_type="CLAUSE",
                relation=IssueContextRelation.TARGET,
                text=text,
                evidence_ids=[f"evidence-{issue_id}"],
            )
        ],
        context_fingerprint=f"context-{issue_id}",
    )


def _primary_result(context: IssuePrimaryAuditContext) -> IssuePrimaryAuditResult:
    return IssuePrimaryAuditResult(
        issue_id=context.issue_id,
        topic=context.topic,
        state=IssuePrimaryAuditState.SUPPORTED_FINDING,
        evidence_sufficiency=IssueEvidenceSufficiency.INSUFFICIENT_LEGAL_CORPUS,
        legal_support_state=context.legal_support_state,
        legal_conclusion=False,
        risk_category=context.topic,
        severity=FindingSeverity.MEDIUM,
        title="fixture primary",
        reasoning_summary="fixture primary reasoning",
        suggestion="fixture primary suggestion",
        canonical_object_ids=[context.target_items[0].canonical_object_id],
        contract_evidence_ids=context.target_items[0].evidence_ids,
        legal_evidence_ids=[],
        context_fingerprint=context.context_fingerprint,
    )


def _patch_upstream(monkeypatch, tmp_path, count: int = 2, *, huge: bool = False):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    contexts = [
        _context(job_id, f"issue-{index}", text=("超长合同证据" * 30000 if huge and index == 1 else f"合同条款{index}"))
        for index in range(1, count + 1)
    ]
    plan = AuditPlan(
        job_id=job_id,
        contract_type=ContractType.UNKNOWN,
        contract_type_confidence=ContractTypeConfidence.LOW,
        contract_type_reasoning="fixture",
        provider="fixture",
        model="fixture",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        planner_input_fingerprint="planner-input",
        planner_response_hash="planner-output",
        coverage_complete=True,
        issues=[
            AuditPlanIssue(
                issue_id=context.issue_id,
                topic=context.topic,
                priority=ReviewPriority.IMPORTANT,
                sources=[AuditPlanSource.BASELINE],
                questions=context.questions,
                retrieval_queries=["fixture legal query"],
            )
            for context in contexts
        ],
    )
    primary_results = [_primary_result(context) for context in contexts]
    primary = IssuePrimaryAuditArtifact(
        job_id=job_id,
        status=IssuePrimaryAuditStatus.COMPLETE,
        as_of="2026-08-18",
        provider="deepseek",
        model="deepseek-v4-pro",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        audit_plan_fingerprint="plan-fp",
        issue_legal_context_fingerprint="legal-fp",
        total_issue_count=count,
        completed_issue_count=count,
        results=primary_results,
        artifact_fingerprint="primary-artifact-fp",
    )
    import app.issue_secondary_review as module
    monkeypatch.setattr(module, "load_audit_plan", lambda _job_id: plan)
    monkeypatch.setattr(module, "load_issue_primary_audit", lambda _job_id: primary)
    monkeypatch.setattr(module, "build_issue_primary_contexts", lambda _job_id: contexts)
    return job_id, plan, primary, contexts


def test_stage13f_reviews_every_planned_issue_once(tmp_path, monkeypatch) -> None:
    job_id, plan, _, _ = _patch_upstream(monkeypatch, tmp_path, count=3)
    provider = FixtureSecondaryProvider()
    artifact = run_issue_secondary_review(job_id, provider_override=provider)
    assert artifact.status.value == "COMPLETE"
    assert artifact.completed_issue_count == len(plan.issues)
    assert {item.issue_id for item in artifact.results} == {item.issue_id for item in plan.issues}
    assert provider.calls == [item.issue_id for item in plan.issues]
    assert all(item.coverage_assessment == SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE for item in artifact.results)


def test_stage13f_rejects_invented_contract_evidence() -> None:
    job_id = uuid4()
    context = _context(job_id, "issue-1")
    primary = _primary_result(context)
    draft = ModelIssueSecondaryDraft(
        issue_id=context.issue_id,
        assessment=SecondaryIssueAssessment.DISAGREED,
        coverage_assessment=SecondaryCoverageAssessment.POSSIBLE_OMISSION,
        severity=FindingSeverity.HIGH,
        reasoning_summary="fixture",
        suggestion="fixture",
        contract_evidence_ids=["invented-evidence"],
        omission_title="遗漏",
        omission_reasoning="fixture",
    )
    with pytest.raises(IssueSecondaryReviewValidationError, match="unsupplied contract Evidence"):
        validate_issue_secondary_output(draft.model_dump_json(), context, primary)


def test_stage13f_checkpoint_resume_does_not_repeat_completed_issue(tmp_path, monkeypatch) -> None:
    job_id, _, _, _ = _patch_upstream(monkeypatch, tmp_path, count=3)
    first = FixtureSecondaryProvider(cancel_after=1)
    with pytest.raises(PipelineCancellationRequested):
        run_issue_secondary_review(job_id, provider_override=first)
    checkpoint = load_issue_secondary_review(job_id, validate_freshness=False)
    assert checkpoint.status.value == "INTERRUPTED"
    assert checkpoint.completed_issue_count == 1
    clear_pipeline_cancel(job_id)
    second = FixtureSecondaryProvider()
    artifact = run_issue_secondary_review(job_id, provider_override=second)
    assert artifact.status.value == "COMPLETE"
    assert second.calls == ["issue-2", "issue-3"]


def test_stage13f_oversized_context_is_not_sent_to_kimi(tmp_path, monkeypatch) -> None:
    job_id, _, _, _ = _patch_upstream(monkeypatch, tmp_path, count=1, huge=True)
    provider = FixtureSecondaryProvider()
    artifact = run_issue_secondary_review(job_id, provider_override=provider)
    assert artifact.status.value == "COMPLETE"
    assert provider.calls == []
    result = artifact.results[0]
    assert result.assessment == SecondaryIssueAssessment.REVIEW_REQUIRED
    assert result.coverage_assessment == SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE
    assert "SECONDARY_CONTEXT_BUDGET_EXCEEDED" in result.review_reasons
