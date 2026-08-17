from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.ai_audit_models import ProviderAuditResult, ProviderHealth
import app.issue_primary_audit as primary
from app.audit_plan_models import AuditPlanSource, ReviewPriority
from app.issue_legal_context_models import IssueLegalSupportState
from app.issue_primary_audit_models import (
    IssueContextRelation,
    IssuePrimaryAuditContext,
    IssuePrimaryAuditState,
    IssuePrimaryAuditStatus,
    IssuePrimaryContractItem,
    IssueTargetSelectionMethod,
)
from app.issue_primary_audit_provider import IssuePrimaryAuditProvider


class MustNotRunProvider(IssuePrimaryAuditProvider):
    provider_name = "budget-fixture"
    model_name = "budget-fixture-v1"

    def __init__(self) -> None:
        self.calls = 0

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, configured=True, model=self.model_name, detail="fixture")

    def generate(self, context: IssuePrimaryAuditContext) -> ProviderAuditResult:
        self.calls += 1
        raise AssertionError("Oversized issue context must not cross the provider boundary.")


def test_oversized_issue_is_terminal_review_required_without_truncation_or_provider_call(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    context = IssuePrimaryAuditContext(
        job_id=job_id,
        issue_id="issue-oversized",
        topic="超大单项审查",
        priority=ReviewPriority.HIGH_ATTENTION,
        sources=[AuditPlanSource.LLM_DYNAMIC],
        why_review=["fixture"],
        questions=["完整证据是否能够在不截断的情况下发送？"],
        as_of=date(2026, 8, 17),
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        audit_plan_fingerprint="plan-fp",
        issue_legal_context_fingerprint="legal-context-fp",
        legal_support_state=IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS,
        target_selection_method=IssueTargetSelectionMethod.EXPLICIT_PLAN,
        target_items=[
            IssuePrimaryContractItem(
                canonical_object_id="clause-large",
                object_type="CLAUSE",
                relation=IssueContextRelation.TARGET,
                text="完整合同证据" * 100,
                evidence_ids=["contract-evidence-large"],
            )
        ],
        context_fingerprint="context-fp",
    )
    monkeypatch.setattr(primary, "build_issue_primary_contexts", lambda _: [context])
    monkeypatch.setattr(primary, "MAX_ISSUE_CONTEXT_CHARS", 100)
    provider = MustNotRunProvider()

    artifact = primary.run_issue_primary_audit(job_id, provider_override=provider)

    assert artifact.status == IssuePrimaryAuditStatus.COMPLETE
    assert artifact.completed_issue_count == 1
    assert provider.calls == 0
    assert artifact.provider_calls == []
    result = artifact.results[0]
    assert result.issue_id == "issue-oversized"
    assert result.state == IssuePrimaryAuditState.REVIEW_REQUIRED
    assert result.legal_conclusion is False
    assert "ISSUE_CONTEXT_BUDGET_EXCEEDED" in result.review_reasons
    assert result.contract_evidence_ids == ["contract-evidence-large"]
