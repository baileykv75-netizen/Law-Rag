from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .ai_audit_models import ProviderAuditResult, ProviderUsage
from .audit_planner import AuditPlannerError, load_audit_plan
from .issue_primary_audit import (
    IssuePrimaryAuditError,
    IssuePrimaryAuditStaleError,
    build_issue_primary_contexts,
    load_issue_primary_audit,
)
from .issue_primary_audit_models import IssuePrimaryAuditResult, IssuePrimaryAuditStatus
from .issue_secondary_review_models import (
    IssueSecondaryProviderCall,
    IssueSecondaryReviewArtifact,
    IssueSecondaryReviewResult,
    IssueSecondaryReviewStatus,
    ModelIssueSecondaryDraft,
    SecondaryCoverageAssessment,
    SecondaryIssueAssessment,
    SecondaryReviewDecisionStatus,
)
from .issue_secondary_review_provider import (
    IssueSecondaryReviewProvider,
    IssueSecondaryReviewProviderError,
    issue_secondary_provider_from_name,
)
from .pipeline_control import (
    PipelineCancellationRequested,
    ProviderBoundaryPaused,
    begin_provider_call,
    ensure_pipeline_control,
    finish_provider_call,
)
from .pipeline_control_models import ProviderExecutionMode
from .safe_persistence import atomic_write_text
from .storage import job_issue_secondary_review_path

MAX_SECONDARY_ISSUE_REQUESTS = 256
MAX_SECONDARY_CONTEXT_CHARS = 120_000
_SENSITIVE_SECONDARY_KEYWORDS = (
    "担保",
    "保证",
    "违约",
    "解除",
    "赔偿",
    "个人信息",
    "数据",
    "竞业",
    "保密",
    "知识产权",
    "许可",
    "付款",
    "租金",
    "工程",
)


class IssueSecondaryReviewError(RuntimeError):
    pass


class IssueSecondaryReviewValidationError(IssueSecondaryReviewError):
    pass


class IssueSecondaryReviewStaleError(IssueSecondaryReviewError):
    pass


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fingerprint_payload(payload: object) -> object:
    if isinstance(payload, dict):
        return {
            key: _fingerprint_payload(value)
            for key, value in payload.items()
            if key != "review_status"
        }
    if isinstance(payload, list):
        return [_fingerprint_payload(item) for item in payload]
    return payload


def _unique(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _secondary_context_char_count(context, primary: IssuePrimaryAuditResult) -> int:
    payload = {
        "issue_context": context.model_dump(mode="json"),
        "primary_result": primary.model_dump(mode="json"),
    }
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _no_contract_result(context, primary: IssuePrimaryAuditResult) -> IssueSecondaryReviewResult:
    return IssueSecondaryReviewResult(
        issue_id=context.issue_id,
        topic=context.topic,
        primary_state=primary.state.value,
        assessment=SecondaryIssueAssessment.REVIEW_REQUIRED,
        coverage_assessment=SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE,
        severity=primary.severity,
        reasoning_summary="该 AuditPlan Issue 没有可验证的目标合同证据。Law-Rag 未让 Kimi 对空白合同上下文形成二审结论。",
        suggestion="人工定位相关条款，或修复结构化/规划后重新运行该 Issue。",
        contract_evidence_ids=[],
        legal_evidence_ids=[],
        review_reasons=["NO_RELEVANT_CONTRACT_EVIDENCE_FOR_SECONDARY_REVIEW"],
        context_fingerprint=context.context_fingerprint,
    )


def _budget_result(context, primary: IssuePrimaryAuditResult) -> IssueSecondaryReviewResult:
    contract_ids = _unique(eid for item in context.target_items for eid in item.evidence_ids)
    return IssueSecondaryReviewResult(
        issue_id=context.issue_id,
        topic=context.topic,
        primary_state=primary.state.value,
        assessment=SecondaryIssueAssessment.REVIEW_REQUIRED,
        coverage_assessment=SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE,
        severity=primary.severity,
        reasoning_summary=(
            f"该 Issue 的完整 Kimi 复核上下文超过 {MAX_SECONDARY_CONTEXT_CHARS} 字符的应用级安全预算。"
            "Law-Rag 没有截断合同、法律证据或主审结果，也没有发送残缺上下文。"
        ),
        suggestion="人工复核该 Issue；若真实样本中频繁出现，应增加二审 Issue 内部分层，而不是静默删减证据。",
        contract_evidence_ids=contract_ids,
        legal_evidence_ids=[],
        review_reasons=["SECONDARY_CONTEXT_BUDGET_EXCEEDED"],
        context_fingerprint=context.context_fingerprint,
    )


def _needs_kimi_review(context, primary: IssuePrimaryAuditResult) -> bool:
    if primary.state.value in {"REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"}:
        return True
    if primary.evidence_sufficiency.value != "SUFFICIENT":
        return True
    if primary.review_reasons:
        return True
    if primary.legal_conclusion and context.legal_support_state.value != "EVIDENCE_FOUND":
        return True
    topic_blob = f"{context.topic} {primary.risk_category} {primary.title}"
    if primary.severity.value in {"HIGH", "CRITICAL"} and any(keyword in topic_blob for keyword in _SENSITIVE_SECONDARY_KEYWORDS):
        return True
    return False


def _skipped_clear_result(context, primary: IssuePrimaryAuditResult) -> IssueSecondaryReviewResult:
    return IssueSecondaryReviewResult(
        issue_id=context.issue_id,
        topic=context.topic,
        primary_state=primary.state.value,
        review_status=SecondaryReviewDecisionStatus.SKIPPED_CLEAR,
        assessment=SecondaryIssueAssessment.SUPPORTED,
        coverage_assessment=SecondaryCoverageAssessment.COVERED,
        severity=primary.severity,
        reasoning_summary="主审结论已有充分合同证据和法律证据支持，未触发争议复审条件。",
        suggestion=primary.suggestion,
        contract_evidence_ids=_unique(primary.contract_evidence_ids),
        legal_evidence_ids=_unique(primary.legal_evidence_ids),
        review_reasons=["SECONDARY_REVIEW_SKIPPED_CLEAR"],
        context_fingerprint=context.context_fingerprint,
    )


def _pending_confirmation_result(
    context,
    primary: IssuePrimaryAuditResult,
    *,
    reason_code: str,
    detail: str,
) -> IssueSecondaryReviewResult:
    return IssueSecondaryReviewResult(
        issue_id=context.issue_id,
        topic=context.topic,
        primary_state=primary.state.value,
        review_status=SecondaryReviewDecisionStatus.PENDING_CONFIRMATION,
        assessment=SecondaryIssueAssessment.REVIEW_REQUIRED,
        coverage_assessment=SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE,
        severity=primary.severity,
        reasoning_summary=f"Kimi 争议复审未完成：{detail}",
        suggestion="先基于主审结果和本地法律依据查看报告；网络或额度恢复后，可仅重新提交二审。",
        contract_evidence_ids=_unique(primary.contract_evidence_ids),
        legal_evidence_ids=_unique(primary.legal_evidence_ids),
        review_reasons=_unique(["SECONDARY_REVIEW_PENDING_CONFIRMATION", reason_code]),
        context_fingerprint=context.context_fingerprint,
    )


def _normalize_secondary_model_raw(raw):
    if not isinstance(raw, dict):
        return raw
    normalized = dict(raw)
    if normalized.get("coverage_assessment") == "PARTIALLY_COVERED":
        normalized["coverage_assessment"] = SecondaryCoverageAssessment.COVERED_BUT_QUESTIONABLE.value
    return normalized


def validate_issue_secondary_output(content: str, context, primary: IssuePrimaryAuditResult) -> IssueSecondaryReviewResult:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise IssueSecondaryReviewValidationError(f"Kimi issue review did not return valid JSON: {exc}") from exc
    try:
        draft = ModelIssueSecondaryDraft.model_validate(_normalize_secondary_model_raw(raw))
    except ValidationError as exc:
        raise IssueSecondaryReviewValidationError(f"Kimi issue review JSON does not match Stage 13F schema: {exc}") from exc
    if draft.issue_id != context.issue_id:
        raise IssueSecondaryReviewValidationError("Kimi returned an issue_id different from the supplied AuditPlan issue.")
    object_contract_evidence = {eid for item in [*context.target_items, *context.related_items] for eid in item.evidence_ids}
    global_fact_evidence = {eid for fact in context.global_facts for eid in fact.evidence_ids}
    allowed_contract = {*object_contract_evidence, *global_fact_evidence}
    allowed_legal = {item.legal_evidence_id for item in context.legal_evidence}
    unknown_contract = set(draft.contract_evidence_ids) - allowed_contract
    unknown_legal = set(draft.legal_evidence_ids) - allowed_legal
    if unknown_contract:
        raise IssueSecondaryReviewValidationError(f"Kimi cited unsupplied contract Evidence IDs: {sorted(unknown_contract)}")
    if unknown_legal:
        raise IssueSecondaryReviewValidationError(f"Kimi cited unsupplied Legal Evidence IDs: {sorted(unknown_legal)}")

    if draft.assessment in {SecondaryIssueAssessment.SUPPORTED, SecondaryIssueAssessment.PARTIALLY_SUPPORTED}:
        if not draft.contract_evidence_ids:
            raise IssueSecondaryReviewValidationError("Supporting a primary issue result requires supplied contract Evidence.")
        if primary.legal_conclusion and not draft.legal_evidence_ids:
            raise IssueSecondaryReviewValidationError("Supporting a primary legal conclusion requires supplied Legal Evidence.")

    if draft.coverage_assessment == SecondaryCoverageAssessment.POSSIBLE_OMISSION:
        if not draft.contract_evidence_ids or not draft.omission_title or not draft.omission_reasoning:
            raise IssueSecondaryReviewValidationError("POSSIBLE_OMISSION requires supplied contract Evidence plus omission title/reasoning.")

    if primary.state.value == "NO_MATERIAL_RISK_FOUND" and draft.assessment == SecondaryIssueAssessment.SUPPORTED:
        if not draft.contract_evidence_ids or not draft.legal_evidence_ids:
            raise IssueSecondaryReviewValidationError("Confirming NO_MATERIAL_RISK_FOUND requires supplied contract and Legal Evidence.")
        if context.legal_support_state.value != "EVIDENCE_FOUND":
            raise IssueSecondaryReviewValidationError("Kimi cannot confidently confirm NO_MATERIAL_RISK_FOUND when legal support is incomplete or uncertain.")

    if not context.target_items and draft.coverage_assessment in {
        SecondaryCoverageAssessment.COVERED,
        SecondaryCoverageAssessment.COVERED_BUT_QUESTIONABLE,
    }:
        coverage = SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE
        review_reasons = _unique([*draft.review_reasons, "NO_TARGET_CONTRACT_EVIDENCE"])
    elif context.legal_support_state.value in {"NO_MATCH_IN_LOCAL_CORPUS", "VERSION_REVIEW_REQUIRED"} and draft.coverage_assessment == SecondaryCoverageAssessment.COVERED:
        review_reasons = _unique([*draft.review_reasons, "LEGAL_EVIDENCE_LIMITS_COVERAGE_CONFIDENCE"])
        coverage = SecondaryCoverageAssessment.INSUFFICIENT_EVIDENCE
    else:
        review_reasons = _unique(draft.review_reasons)
        coverage = draft.coverage_assessment
    if set(draft.contract_evidence_ids).intersection(global_fact_evidence - object_contract_evidence):
        review_reasons = _unique([*review_reasons, "GLOBAL_FACT_CONTRACT_EVIDENCE_ACCEPTED"])

    return IssueSecondaryReviewResult(
        issue_id=context.issue_id,
        topic=context.topic,
        primary_state=primary.state.value,
        review_status=SecondaryReviewDecisionStatus.REVIEWED,
        assessment=draft.assessment,
        coverage_assessment=coverage,
        severity=draft.severity,
        reasoning_summary=draft.reasoning_summary,
        suggestion=draft.suggestion,
        contract_evidence_ids=_unique(draft.contract_evidence_ids),
        legal_evidence_ids=_unique(draft.legal_evidence_ids),
        review_reasons=review_reasons,
        omission_title=draft.omission_title,
        omission_reasoning=draft.omission_reasoning,
        context_fingerprint=context.context_fingerprint,
    )


def _sum_usage(calls: list[IssueSecondaryProviderCall]) -> ProviderUsage:
    def total(field: str) -> int | None:
        values = [getattr(call.usage, field) for call in calls if getattr(call.usage, field) is not None]
        return sum(values) if values else None
    return ProviderUsage(prompt_tokens=total("prompt_tokens"), completion_tokens=total("completion_tokens"), total_tokens=total("total_tokens"))


def _payload(*, job_id: UUID, status: IssueSecondaryReviewStatus, provider: str, model: str, plan_fingerprint: str, legal_fingerprint: str, primary_fingerprint: str, total_issue_count: int, results: list[IssueSecondaryReviewResult], calls: list[IssueSecondaryProviderCall], warnings: list[str]) -> dict:
    return {
        "schema_version": "1.0.0",
        "engine_version": "stage13f-1.0.0",
        "job_id": str(job_id),
        "status": status.value,
        "provider": provider,
        "model": model,
        "audit_plan_fingerprint": plan_fingerprint,
        "issue_legal_context_fingerprint": legal_fingerprint,
        "issue_primary_audit_fingerprint": primary_fingerprint,
        "total_issue_count": total_issue_count,
        "completed_issue_count": len(results),
        "results": [item.model_dump(mode="json") for item in results],
        "provider_calls": [item.model_dump(mode="json") for item in calls],
        "provider_usage": _sum_usage(calls).model_dump(mode="json"),
        "warnings": _unique(warnings),
    }


def _persist(payload: dict) -> IssueSecondaryReviewArtifact:
    artifact = IssueSecondaryReviewArtifact(
        **payload,
        artifact_fingerprint=_fingerprint(_fingerprint_payload(payload)),
    )
    atomic_write_text(Path(job_issue_secondary_review_path(artifact.job_id)), artifact.model_dump_json(indent=2))
    return artifact


def _load_checkpoint(job_id: UUID) -> IssueSecondaryReviewArtifact | None:
    path = job_issue_secondary_review_path(job_id)
    if not path.exists():
        return None
    try:
        return IssueSecondaryReviewArtifact.model_validate_json(path.read_bytes())
    except ValidationError:
        return None


def run_issue_secondary_review(
    job_id: UUID,
    *,
    provider_name: str = "kimi",
    provider_override: IssueSecondaryReviewProvider | None = None,
    allow_provider_unavailable: bool = False,
    retry_pending: bool = False,
) -> IssueSecondaryReviewArtifact:
    try:
        plan = load_audit_plan(job_id)
        primary = load_issue_primary_audit(job_id)
        contexts = build_issue_primary_contexts(job_id)
    except (FileNotFoundError, AuditPlannerError, IssuePrimaryAuditError, IssuePrimaryAuditStaleError) as exc:
        raise IssueSecondaryReviewError("Fresh Stage 13B-13E artifacts are required before Stage 13F.") from exc
    if primary.status != IssuePrimaryAuditStatus.COMPLETE:
        raise IssueSecondaryReviewError("Stage 13E must be COMPLETE before Stage 13F begins.")
    if len(contexts) > MAX_SECONDARY_ISSUE_REQUESTS:
        raise IssueSecondaryReviewError(f"Audit Plan contains {len(contexts)} issues, above the Stage 13F bounded limit of {MAX_SECONDARY_ISSUE_REQUESTS}.")
    primary_by_id = {item.issue_id: item for item in primary.results}
    context_by_id = {item.issue_id: item for item in contexts}
    plan_ids = [item.issue_id for item in plan.issues]
    if len(plan_ids) != len(set(plan_ids)):
        raise IssueSecondaryReviewStaleError("AuditPlan contains duplicate issue IDs.")
    if len(primary.results) != len(primary_by_id) or len(contexts) != len(context_by_id):
        raise IssueSecondaryReviewStaleError("Stage 13E results or Stage 13F contexts contain duplicate issue IDs.")
    if set(primary_by_id) != set(plan_ids) or set(context_by_id) != set(plan_ids):
        raise IssueSecondaryReviewStaleError("AuditPlan, Stage 13E results and Stage 13F contexts do not contain the same issue set.")
    ensure_pipeline_control(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)
    provider: IssueSecondaryReviewProvider | None = None
    health_detail = "Kimi 二审服务暂不可用。"
    try:
        provider = provider_override or issue_secondary_provider_from_name(provider_name)
        health = provider.health()
        health_detail = health.detail
    except IssueSecondaryReviewProviderError as exc:
        if not allow_provider_unavailable:
            raise IssueSecondaryReviewError(str(exc)) from exc
        health_detail = str(exc)
    if provider is not None and not health.configured:
        if allow_provider_unavailable:
            health_detail = health.detail
            provider = None
        else:
            raise IssueSecondaryReviewError(health.detail)
    if provider is None and not allow_provider_unavailable:
        raise IssueSecondaryReviewError(health.detail)

    checkpoint = _load_checkpoint(job_id)
    reusable: dict[str, IssueSecondaryReviewResult] = {}
    reusable_calls: dict[str, IssueSecondaryProviderCall] = {}
    artifact_provider = provider.provider_name if provider is not None else provider_name
    artifact_model = provider.model_name if provider is not None else "unavailable"
    if checkpoint and checkpoint.provider == artifact_provider and checkpoint.model == artifact_model and checkpoint.issue_primary_audit_fingerprint == primary.artifact_fingerprint:
        reusable = {item.issue_id: item for item in checkpoint.results}
        reusable_calls = {item.issue_id: item for item in checkpoint.provider_calls}

    results: list[IssueSecondaryReviewResult] = []
    calls: list[IssueSecondaryProviderCall] = []
    warnings: list[str] = []
    for index, issue_id in enumerate(plan_ids):
        context = context_by_id[issue_id]
        primary_result = primary_by_id[issue_id]
        old = reusable.get(issue_id)
        if old is not None and old.context_fingerprint == context.context_fingerprint:
            if retry_pending and old.review_status == SecondaryReviewDecisionStatus.PENDING_CONFIRMATION:
                pass
            else:
                results.append(old)
                if issue_id in reusable_calls:
                    calls.append(reusable_calls[issue_id])
                continue
        if not _needs_kimi_review(context, primary_result):
            results.append(_skipped_clear_result(context, primary_result))
            _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
            continue
        if provider is None:
            results.append(_pending_confirmation_result(context, primary_result, reason_code="KIMI_PROVIDER_UNAVAILABLE", detail=health_detail))
            warnings.append(f"Issue {issue_id} secondary review deferred: {health_detail}")
            _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
            continue
        if not context.target_items:
            results.append(_no_contract_result(context, primary_result))
            _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
            continue
        context_chars = _secondary_context_char_count(context, primary_result)
        if context_chars > MAX_SECONDARY_CONTEXT_CHARS:
            results.append(_budget_result(context, primary_result))
            warnings.append(f"Issue {issue_id} secondary context size {context_chars} exceeded {MAX_SECONDARY_CONTEXT_CHARS}; no truncated Kimi request was sent.")
            _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
            continue
        try:
            begin_provider_call(job_id, provider.provider_name)
            try:
                provider_result: ProviderAuditResult = provider.generate(context, primary_result)
            finally:
                finish_provider_call(job_id, provider.provider_name)
            result = validate_issue_secondary_output(provider_result.content, context, primary_result)
        except (PipelineCancellationRequested, ProviderBoundaryPaused):
            _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.INTERRUPTED, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=[*warnings, "Stage 13F interrupted by persisted provider/cancel control; completed issue reviews were checkpointed."]))
            raise
        except (IssueSecondaryReviewProviderError, IssueSecondaryReviewValidationError) as exc:
            reason_code = str(getattr(exc, "code", type(exc).__name__))
            warnings.append(f"Issue {issue_id} secondary review deferred: {exc}")
            results.append(_pending_confirmation_result(context, primary_result, reason_code=reason_code, detail=str(exc)))
            if bool(getattr(exc, "recoverable", False)):
                for remaining_issue_id in plan_ids[index + 1 :]:
                    remaining_context = context_by_id[remaining_issue_id]
                    remaining_primary = primary_by_id[remaining_issue_id]
                    old_remaining = reusable.get(remaining_issue_id)
                    if old_remaining is not None and old_remaining.context_fingerprint == remaining_context.context_fingerprint:
                        results.append(old_remaining)
                        if remaining_issue_id in reusable_calls:
                            calls.append(reusable_calls[remaining_issue_id])
                    elif _needs_kimi_review(remaining_context, remaining_primary):
                        results.append(
                            _pending_confirmation_result(
                                remaining_context,
                                remaining_primary,
                                reason_code=reason_code,
                                detail="Kimi 争议复审已因外部服务状态延后，剩余争议项未继续发送。",
                            )
                        )
                    else:
                        results.append(_skipped_clear_result(remaining_context, remaining_primary))
                _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
                break
            _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
            continue
        results.append(result)
        calls.append(IssueSecondaryProviderCall(issue_id=issue_id, provider=provider_result.provider, model=provider_result.model, request_id=provider_result.request_id, finish_reason=provider_result.finish_reason, raw_response_hash=provider_result.raw_response_hash, usage=provider_result.usage))
        _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.IN_PROGRESS, provider=artifact_provider, model=artifact_model, plan_fingerprint=context.audit_plan_fingerprint, legal_fingerprint=context.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))
    if len(results) != len(plan_ids) or {item.issue_id for item in results} != set(plan_ids):
        raise IssueSecondaryReviewValidationError("Stage 13F completed without exactly one Kimi review result for every AuditPlan issue.")
    template = contexts[0]
    return _persist(_payload(job_id=job_id, status=IssueSecondaryReviewStatus.COMPLETE, provider=artifact_provider, model=artifact_model, plan_fingerprint=template.audit_plan_fingerprint, legal_fingerprint=template.issue_legal_context_fingerprint, primary_fingerprint=primary.artifact_fingerprint, total_issue_count=len(plan_ids), results=results, calls=calls, warnings=warnings))


def load_issue_secondary_review(job_id: UUID, *, validate_freshness: bool = True) -> IssueSecondaryReviewArtifact:
    path = job_issue_secondary_review_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Stage 13F issue-secondary-review.json does not exist for job {job_id}.")
    try:
        artifact = IssueSecondaryReviewArtifact.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise IssueSecondaryReviewValidationError("Persisted Stage 13F artifact is malformed.") from exc
    if artifact.job_id != job_id:
        raise IssueSecondaryReviewValidationError("Persisted Stage 13F artifact belongs to a different job.")
    payload = artifact.model_dump(mode="json", exclude={"artifact_fingerprint"})
    if artifact.artifact_fingerprint != _fingerprint(_fingerprint_payload(payload)):
        raise IssueSecondaryReviewValidationError("Persisted Stage 13F artifact fingerprint is invalid.")
    if validate_freshness:
        try:
            primary = load_issue_primary_audit(job_id)
        except (FileNotFoundError, IssuePrimaryAuditError, IssuePrimaryAuditStaleError) as exc:
            raise IssueSecondaryReviewStaleError("Stage 13F is stale because Stage 13E is missing or stale.") from exc
        if artifact.issue_primary_audit_fingerprint != primary.artifact_fingerprint:
            raise IssueSecondaryReviewStaleError("Stage 13F is stale because issue-primary-audit.json changed.")
    return artifact
