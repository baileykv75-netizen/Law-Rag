from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .ai_audit_models import EvidenceSufficiency, ProviderAuditResult, ProviderUsage
from .audit_planner import AuditPlannerError, load_audit_plan
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report
from .contract_models import CanonicalContract, SourceSpan
from .contract_structure import StructureProcessingError, load_contract_structure
from .issue_legal_context import (
    IssueLegalContextError,
    IssueLegalContextStaleError,
    load_issue_legal_context,
)
from .issue_legal_context_models import IssueLegalEvidencePackage, IssueLegalSupportState
from .issue_primary_audit_models import (
    IssueContextRelation,
    IssuePrimaryAuditArtifact,
    IssuePrimaryAuditContext,
    IssuePrimaryAuditResult,
    IssuePrimaryAuditState,
    IssuePrimaryAuditStatus,
    IssuePrimaryContractItem,
    IssuePrimaryGlobalFact,
    IssuePrimaryProviderCall,
    IssuePrimaryRuleHint,
    IssueTargetSelectionMethod,
    ModelIssuePrimaryAuditDraft,
)
from .issue_primary_audit_provider import (
    IssuePrimaryAuditProvider,
    IssuePrimaryAuditProviderError,
    issue_primary_provider_from_name,
)
from .models import SourceMethod
from .pipeline_control import (
    PipelineCancellationRequested,
    ProviderBoundaryPaused,
    begin_provider_call,
    ensure_pipeline_control,
    finish_provider_call,
)
from .pipeline_control_models import ProviderExecutionMode
from .safe_persistence import atomic_write_text
from .storage import job_issue_primary_audit_path

OCR_REVIEW_THRESHOLD = 0.85
MAX_PRIMARY_ISSUE_REQUESTS = 256
MAX_RELATED_ITEMS = 16
MAX_TARGET_FALLBACK_ITEMS = 8
MAX_GLOBAL_FACTS = 64
MAX_GLOBAL_FACT_CHARS = 12_000
NON_TEXT_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


class IssuePrimaryAuditError(RuntimeError):
    pass


class IssuePrimaryAuditConfigurationError(IssuePrimaryAuditError):
    pass


class IssuePrimaryAuditValidationError(IssuePrimaryAuditError):
    pass


class IssuePrimaryAuditStaleError(IssuePrimaryAuditError):
    pass


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique(values) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _evidence_ids(spans: list[SourceSpan]) -> list[str]:
    return _unique(eid for span in spans for eid in span.evidence_ids)


def _source_uncertain(spans: list[SourceSpan]) -> bool:
    for span in spans:
        if span.source_method == SourceMethod.OCR and (span.confidence is None or span.confidence < OCR_REVIEW_THRESHOLD):
            return True
    return False


def _clause_text(clause) -> str:
    return "\n".join(part for part in (clause.heading_token, clause.heading_text, clause.body_text) if part).strip()


def _contract_item_map(contract: CanonicalContract) -> dict[str, IssuePrimaryContractItem]:
    items: dict[str, IssuePrimaryContractItem] = {}
    for clause in contract.clauses:
        items[clause.clause_id] = IssuePrimaryContractItem(
            canonical_object_id=clause.clause_id,
            object_type="CLAUSE",
            relation=IssueContextRelation.TARGET,
            text=_clause_text(clause),
            evidence_ids=_evidence_ids(clause.source_spans),
            source_uncertain=_source_uncertain(clause.source_spans),
        )
    for block in contract.unnumbered_blocks:
        items[block.block_id] = IssuePrimaryContractItem(
            canonical_object_id=block.block_id,
            object_type="UNNUMBERED_BLOCK",
            relation=IssueContextRelation.TARGET,
            text=block.text,
            evidence_ids=_evidence_ids(block.source_spans),
            source_uncertain=_source_uncertain(block.source_spans),
        )
    return items


def _grams(value: str) -> set[str]:
    compact = NON_TEXT_RE.sub("", value.lower())
    if not compact:
        return set()
    if len(compact) <= 2:
        return {compact}
    return {compact[index : index + 3] for index in range(len(compact) - 2)}


def _fallback_target_ids(package: IssueLegalEvidencePackage, item_map: dict[str, IssuePrimaryContractItem]) -> list[str]:
    query = " ".join(
        [package.topic, *package.questions, *(run.query for run in package.retrieval_runs)]
    )
    query_grams = _grams(query)
    if not query_grams:
        return []
    scored: list[tuple[int, str]] = []
    for object_id, item in item_map.items():
        item_grams = _grams(item.text)
        score = len(query_grams.intersection(item_grams))
        if score > 0:
            scored.append((score, object_id))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [object_id for _, object_id in scored[:MAX_TARGET_FALLBACK_ITEMS]]


def _related_ids(
    contract: CanonicalContract,
    target_ids: list[str],
    item_map: dict[str, IssuePrimaryContractItem],
) -> list[str]:
    target_set = set(target_ids)
    related: list[str] = []
    clause_ids = [clause.clause_id for clause in contract.clauses]
    clause_by_id = {clause.clause_id: clause for clause in contract.clauses}
    position = {clause_id: index for index, clause_id in enumerate(clause_ids)}

    for target_id in target_ids:
        clause = clause_by_id.get(target_id)
        if clause is None:
            continue
        index = position[target_id]
        if index > 0:
            related.append(clause_ids[index - 1])
        if index + 1 < len(clause_ids):
            related.append(clause_ids[index + 1])
        if clause.parent_clause_id:
            related.append(clause.parent_clause_id)
        related.extend(child.clause_id for child in contract.clauses if child.parent_clause_id == target_id)

    target_evidence = {
        evidence_id
        for target_id in target_ids
        for evidence_id in item_map[target_id].evidence_ids
        if target_id in item_map
    }
    for reference in contract.references:
        source_evidence = set(_evidence_ids(reference.source_spans))
        if source_evidence.intersection(target_evidence) and reference.resolved_target_id:
            related.append(reference.resolved_target_id)

    return [item for item in _unique(related) if item not in target_set and item in item_map][:MAX_RELATED_ITEMS]


def _all_global_facts(contract: CanonicalContract) -> list[IssuePrimaryGlobalFact]:
    facts: list[IssuePrimaryGlobalFact] = []
    for item in contract.title_candidates:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.candidate_id, fact_type="TITLE", label="contract_title", value=item.text, evidence_ids=_evidence_ids(item.source_spans)))
    for item in contract.parties:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.mention_id, fact_type="PARTY", label=item.role_label, value=item.normalized_name or item.raw_name or "<unresolved>", evidence_ids=_evidence_ids(item.source_spans)))
    for item in contract.dates:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.mention_id, fact_type="DATE", label=item.field_label or "date", value=item.iso_date or item.raw_text, evidence_ids=_evidence_ids(item.source_spans)))
    for item in contract.money_mentions:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.mention_id, fact_type="MONEY", label=item.currency or item.unit or "amount", value=item.numeric_value or item.raw_text, evidence_ids=_evidence_ids(item.source_spans)))
    for item in contract.percentages:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.mention_id, fact_type="PERCENTAGE", label="percentage", value=item.numeric_value or item.raw_text, evidence_ids=_evidence_ids(item.source_spans)))
    for item in contract.identifiers:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.mention_id, fact_type="IDENTIFIER", label=item.label, value=item.raw_value, evidence_ids=_evidence_ids(item.source_spans)))
    for item in contract.references:
        facts.append(IssuePrimaryGlobalFact(fact_id=item.reference_id, fact_type="REFERENCE", label=item.reference_type.value, value=item.raw_text, evidence_ids=_evidence_ids(item.source_spans)))
    return facts


def _select_global_facts(contract: CanonicalContract, issue_evidence_ids: set[str]) -> list[IssuePrimaryGlobalFact]:
    all_facts = _all_global_facts(contract)
    identity = [fact for fact in all_facts if fact.fact_type in {"TITLE", "PARTY"}]
    local = [fact for fact in all_facts if fact not in identity and issue_evidence_ids.intersection(fact.evidence_ids)]
    remaining = [fact for fact in all_facts if fact not in identity and fact not in local]
    selected: list[IssuePrimaryGlobalFact] = []
    char_count = 0
    for fact in [*identity, *local, *remaining]:
        cost = len(fact.label) + len(fact.value)
        if len(selected) >= MAX_GLOBAL_FACTS or char_count + cost > MAX_GLOBAL_FACT_CHARS:
            break
        selected.append(fact)
        char_count += cost
    return selected


def _rule_hints(job_id: UUID, rule_result_ids: list[str]) -> list[IssuePrimaryRuleHint]:
    if not rule_result_ids:
        return []
    try:
        report = load_audit_rule_report(job_id)
    except (FileNotFoundError, AuditRuleProcessingError) as exc:
        raise IssuePrimaryAuditStaleError("Stage 5 audit-rules.json is missing or invalid for the planned issue.") from exc
    by_id = {result.result_id: result for result in report.results}
    missing = set(rule_result_ids) - set(by_id)
    if missing:
        raise IssuePrimaryAuditStaleError(f"Audit Plan references missing deterministic rule results: {sorted(missing)}")
    return [
        IssuePrimaryRuleHint(
            result_id=result.result_id,
            rule_id=result.rule_id,
            state=result.state.value,
            reason_code=result.reason_code,
            explanation=result.explanation,
            canonical_object_ids=result.canonical_object_ids,
            evidence_ids=result.evidence_ids,
        )
        for result_id in rule_result_ids
        for result in [by_id[result_id]]
    ]


def build_issue_primary_contexts(job_id: UUID) -> list[IssuePrimaryAuditContext]:
    try:
        legal_context = load_issue_legal_context(job_id)
        plan = load_audit_plan(job_id)
        contract = load_contract_structure(job_id)
    except (FileNotFoundError, IssueLegalContextError, IssueLegalContextStaleError, AuditPlannerError, StructureProcessingError) as exc:
        raise IssuePrimaryAuditError("Fresh audit-plan.json, contract.json and issue-legal-context.json are required before Stage 13E.") from exc

    if legal_context.audit_plan_fingerprint != _fingerprint(plan.model_dump(mode="json")):
        raise IssuePrimaryAuditStaleError("Stage 13D legal context does not match the current Audit Plan.")
    if contract.source_fingerprint != legal_context.contract_source_fingerprint:
        raise IssuePrimaryAuditStaleError("Canonical contract source fingerprint changed after Stage 13D.")
    if legal_context.as_of != legal_context.as_of:
        raise IssuePrimaryAuditStaleError("Invalid legal-context date state.")

    plan_by_id = {issue.issue_id: issue for issue in plan.issues}
    legal_by_id = {issue.issue_id: issue for issue in legal_context.issues}
    if set(plan_by_id) != set(legal_by_id):
        raise IssuePrimaryAuditStaleError("Audit Plan and issue Legal RAG issue sets differ.")

    item_map = _contract_item_map(contract)
    contexts: list[IssuePrimaryAuditContext] = []
    for issue in plan.issues:
        package = legal_by_id[issue.issue_id]
        explicit_ids = _unique(issue.contract_object_ids)
        unknown = set(explicit_ids) - set(item_map)
        if unknown:
            raise IssuePrimaryAuditStaleError(f"Audit issue {issue.issue_id} references missing canonical objects: {sorted(unknown)}")

        if explicit_ids:
            target_ids = explicit_ids
            method = IssueTargetSelectionMethod.EXPLICIT_PLAN
        else:
            target_ids = _fallback_target_ids(package, item_map)
            method = (
                IssueTargetSelectionMethod.DETERMINISTIC_CONTRACT_RETRIEVAL
                if target_ids
                else IssueTargetSelectionMethod.NONE
            )
        related_ids = _related_ids(contract, target_ids, item_map)
        targets = [item_map[item_id].model_copy(update={"relation": IssueContextRelation.TARGET}) for item_id in target_ids]
        related = [item_map[item_id].model_copy(update={"relation": IssueContextRelation.RELATED}) for item_id in related_ids]
        evidence_set = {eid for item in [*targets, *related] for eid in item.evidence_ids}
        warnings = list(package.warnings)
        if method == IssueTargetSelectionMethod.DETERMINISTIC_CONTRACT_RETRIEVAL:
            warnings.append("AuditPlan issue had no explicit canonical object binding; Law-Rag selected candidate contract objects with deterministic local text relevance.")
        if method == IssueTargetSelectionMethod.NONE:
            warnings.append("No relevant canonical contract object could be selected for this issue; Stage 13E must not invent contract evidence.")

        base = {
            "job_id": str(job_id),
            "issue_id": issue.issue_id,
            "topic": issue.topic,
            "priority": issue.priority.value,
            "sources": [source.value for source in issue.sources],
            "why_review": issue.why_review,
            "questions": issue.questions,
            "as_of": legal_context.as_of.isoformat(),
            "contract_source_fingerprint": legal_context.contract_source_fingerprint,
            "contract_content_fingerprint": legal_context.contract_content_fingerprint,
            "audit_plan_fingerprint": legal_context.audit_plan_fingerprint,
            "issue_legal_context_fingerprint": legal_context.artifact_fingerprint,
            "legal_support_state": package.support_state.value,
            "target_selection_method": method.value,
            "target_items": [item.model_dump(mode="json") for item in targets],
            "related_items": [item.model_dump(mode="json") for item in related],
            "global_facts": [item.model_dump(mode="json") for item in _select_global_facts(contract, evidence_set)],
            "deterministic_hints": [item.model_dump(mode="json") for item in _rule_hints(job_id, issue.rule_result_ids)],
            "legal_evidence": [item.model_dump(mode="json") for item in package.legal_evidence],
            "warnings": list(dict.fromkeys(warnings)),
        }
        contexts.append(IssuePrimaryAuditContext(**base, context_fingerprint=_fingerprint(base)))
    return contexts


def _evidence_sufficiency(context: IssuePrimaryAuditContext, contract_evidence_ids: list[str]) -> EvidenceSufficiency:
    cited = set(contract_evidence_ids)
    items = [*context.target_items, *context.related_items]
    if any(item.source_uncertain and cited.intersection(item.evidence_ids) for item in items):
        return EvidenceSufficiency.SOURCE_UNCERTAIN
    if context.legal_support_state == IssueLegalSupportState.VERSION_REVIEW_REQUIRED:
        return EvidenceSufficiency.VERSION_UNCERTAIN
    if context.legal_support_state == IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS:
        return EvidenceSufficiency.INSUFFICIENT_CORPUS
    if context.legal_support_state == IssueLegalSupportState.EVIDENCE_FOUND_WITH_LIMITATIONS:
        return EvidenceSufficiency.PARTIAL_CORPUS
    return EvidenceSufficiency.SUFFICIENT


def validate_issue_model_output(content: str, context: IssuePrimaryAuditContext) -> IssuePrimaryAuditResult:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise IssuePrimaryAuditValidationError(f"Primary issue model did not return valid JSON: {exc}") from exc
    try:
        draft = ModelIssuePrimaryAuditDraft.model_validate(raw)
    except ValidationError as exc:
        raise IssuePrimaryAuditValidationError(f"Primary issue JSON does not match the Stage 13E schema: {exc}") from exc

    allowed_objects = {item.canonical_object_id for item in [*context.target_items, *context.related_items]}
    allowed_contract = {eid for item in [*context.target_items, *context.related_items] for eid in item.evidence_ids}
    allowed_legal = {item.legal_evidence_id for item in context.legal_evidence}
    unknown_objects = set(draft.canonical_object_ids) - allowed_objects
    unknown_contract = set(draft.contract_evidence_ids) - allowed_contract
    unknown_legal = set(draft.legal_evidence_ids) - allowed_legal
    if unknown_objects:
        raise IssuePrimaryAuditValidationError(f"Model cited unsupplied canonical object IDs: {sorted(unknown_objects)}")
    if unknown_contract:
        raise IssuePrimaryAuditValidationError(f"Model cited unsupplied contract Evidence IDs: {sorted(unknown_contract)}")
    if unknown_legal:
        raise IssuePrimaryAuditValidationError(f"Model cited unsupplied Legal Evidence IDs: {sorted(unknown_legal)}")

    if draft.state == IssuePrimaryAuditState.SUPPORTED_FINDING and not draft.contract_evidence_ids:
        raise IssuePrimaryAuditValidationError("SUPPORTED_FINDING must cite supplied contract Evidence.")
    if draft.legal_conclusion:
        if draft.state not in {IssuePrimaryAuditState.SUPPORTED_FINDING, IssuePrimaryAuditState.NO_MATERIAL_RISK_FOUND}:
            raise IssuePrimaryAuditValidationError("Only supported/no-material-risk results may claim a legal conclusion.")
        if not draft.legal_evidence_ids:
            raise IssuePrimaryAuditValidationError("A legal conclusion must cite supplied Legal Evidence.")
        if context.legal_support_state in {IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS, IssueLegalSupportState.VERSION_REVIEW_REQUIRED}:
            raise IssuePrimaryAuditValidationError("A legal conclusion is not allowed with missing or version-uncertain Legal Evidence.")

    sufficiency = _evidence_sufficiency(context, draft.contract_evidence_ids)
    review_reasons = list(draft.review_reasons)
    final_state = draft.state
    final_legal_conclusion = draft.legal_conclusion

    if draft.state == IssuePrimaryAuditState.NO_MATERIAL_RISK_FOUND:
        if not draft.contract_evidence_ids or not draft.legal_evidence_ids or not draft.legal_conclusion:
            raise IssuePrimaryAuditValidationError("NO_MATERIAL_RISK_FOUND requires contract Evidence, Legal Evidence and legal_conclusion=true.")
        target_uncertain = any(item.source_uncertain for item in context.target_items)
        if context.legal_support_state != IssueLegalSupportState.EVIDENCE_FOUND or target_uncertain:
            final_state = IssuePrimaryAuditState.REVIEW_REQUIRED
            final_legal_conclusion = False
            review_reasons.append("NO_MATERIAL_RISK_NOT_ALLOWED_WITH_INCOMPLETE_EVIDENCE")

    if draft.state == IssuePrimaryAuditState.SUPPORTED_FINDING:
        cited_uncertain = sufficiency == EvidenceSufficiency.SOURCE_UNCERTAIN
        if cited_uncertain or context.legal_support_state == IssueLegalSupportState.VERSION_REVIEW_REQUIRED:
            final_state = IssuePrimaryAuditState.REVIEW_REQUIRED
            final_legal_conclusion = False
            review_reasons.append("SUPPORTED_FINDING_REQUIRES_REVIEW_DUE_TO_EVIDENCE_STATE")
        elif draft.legal_conclusion and context.legal_support_state == IssueLegalSupportState.EVIDENCE_FOUND_WITH_LIMITATIONS:
            review_reasons.append("PARTIAL_LEGAL_CORPUS")

    return IssuePrimaryAuditResult(
        issue_id=context.issue_id,
        topic=context.topic,
        state=final_state,
        evidence_sufficiency=sufficiency,
        legal_support_state=context.legal_support_state,
        legal_conclusion=final_legal_conclusion,
        risk_category=draft.risk_category,
        severity=draft.severity,
        title=draft.title,
        reasoning_summary=draft.reasoning_summary,
        suggestion=draft.suggestion,
        canonical_object_ids=_unique(draft.canonical_object_ids),
        contract_evidence_ids=_unique(draft.contract_evidence_ids),
        legal_evidence_ids=_unique(draft.legal_evidence_ids),
        review_reasons=_unique(review_reasons),
        context_fingerprint=context.context_fingerprint,
    )


def _no_contract_result(context: IssuePrimaryAuditContext) -> IssuePrimaryAuditResult:
    return IssuePrimaryAuditResult(
        issue_id=context.issue_id,
        topic=context.topic,
        state=IssuePrimaryAuditState.INSUFFICIENT_EVIDENCE,
        evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT_CORPUS,
        legal_support_state=context.legal_support_state,
        legal_conclusion=False,
        risk_category=context.topic,
        severity="INFO",
        title=f"合同证据不足：{context.topic}",
        reasoning_summary="该审查问题没有可验证的目标合同条款，Law-Rag 未让模型 invent 合同证据。",
        suggestion="人工定位相关条款或改进合同结构化/规划后重新审查。",
        review_reasons=["NO_RELEVANT_CONTRACT_EVIDENCE_SELECTED"],
        context_fingerprint=context.context_fingerprint,
    )


def _sum_usage(calls: list[IssuePrimaryProviderCall]) -> ProviderUsage:
    def total(field: str) -> int | None:
        values = [getattr(call.usage, field) for call in calls if getattr(call.usage, field) is not None]
        return sum(values) if values else None
    return ProviderUsage(prompt_tokens=total("prompt_tokens"), completion_tokens=total("completion_tokens"), total_tokens=total("total_tokens"))


def _artifact_payload(
    *,
    job_id: UUID,
    status: IssuePrimaryAuditStatus,
    context_template: IssuePrimaryAuditContext,
    provider: str,
    model: str,
    total_issue_count: int,
    results: list[IssuePrimaryAuditResult],
    calls: list[IssuePrimaryProviderCall],
    warnings: list[str],
) -> dict:
    return {
        "schema_version": "1.0.0",
        "engine_version": "stage13e-1.0.0",
        "job_id": str(job_id),
        "status": status.value,
        "as_of": context_template.as_of.isoformat(),
        "provider": provider,
        "model": model,
        "contract_source_fingerprint": context_template.contract_source_fingerprint,
        "contract_content_fingerprint": context_template.contract_content_fingerprint,
        "audit_plan_fingerprint": context_template.audit_plan_fingerprint,
        "issue_legal_context_fingerprint": context_template.issue_legal_context_fingerprint,
        "total_issue_count": total_issue_count,
        "completed_issue_count": len(results),
        "results": [item.model_dump(mode="json") for item in results],
        "provider_calls": [item.model_dump(mode="json") for item in calls],
        "provider_usage": _sum_usage(calls).model_dump(mode="json"),
        "warnings": _unique(warnings),
    }


def _persist_artifact(payload: dict) -> IssuePrimaryAuditArtifact:
    artifact = IssuePrimaryAuditArtifact(**payload, artifact_fingerprint=_fingerprint(payload))
    atomic_write_text(Path(job_issue_primary_audit_path(artifact.job_id)), artifact.model_dump_json(indent=2))
    return artifact


def _load_checkpoint(job_id: UUID) -> IssuePrimaryAuditArtifact | None:
    path = job_issue_primary_audit_path(job_id)
    if not path.exists():
        return None
    try:
        return IssuePrimaryAuditArtifact.model_validate_json(path.read_bytes())
    except ValidationError:
        return None


def run_issue_primary_audit(
    job_id: UUID,
    *,
    provider_name: str = "deepseek",
    provider_override: IssuePrimaryAuditProvider | None = None,
) -> IssuePrimaryAuditArtifact:
    contexts = build_issue_primary_contexts(job_id)
    if not contexts:
        raise IssuePrimaryAuditError("Audit Plan contains no issues for Stage 13E.")
    if len(contexts) > MAX_PRIMARY_ISSUE_REQUESTS:
        raise IssuePrimaryAuditError(
            f"Audit Plan contains {len(contexts)} issues, above the bounded Stage 13E limit of {MAX_PRIMARY_ISSUE_REQUESTS}. Law-Rag did not silently omit issues."
        )

    ensure_pipeline_control(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)
    try:
        provider = provider_override or issue_primary_provider_from_name(provider_name)
        health = provider.health()
    except IssuePrimaryAuditProviderError as exc:
        raise IssuePrimaryAuditError(str(exc)) from exc
    if not health.configured:
        raise IssuePrimaryAuditConfigurationError(health.detail)

    checkpoint = _load_checkpoint(job_id)
    reusable: dict[str, IssuePrimaryAuditResult] = {}
    reusable_calls: dict[str, IssuePrimaryProviderCall] = {}
    if (
        checkpoint is not None
        and checkpoint.issue_legal_context_fingerprint == contexts[0].issue_legal_context_fingerprint
        and checkpoint.provider == provider.provider_name
        and checkpoint.model == provider.model_name
    ):
        reusable = {result.issue_id: result for result in checkpoint.results}
        reusable_calls = {call.issue_id: call for call in checkpoint.provider_calls}
        if checkpoint.status == IssuePrimaryAuditStatus.COMPLETE and len(reusable) == len(contexts):
            current = {context.issue_id: context.context_fingerprint for context in contexts}
            if all(reusable[issue_id].context_fingerprint == fingerprint for issue_id, fingerprint in current.items()):
                return checkpoint

    results: list[IssuePrimaryAuditResult] = []
    calls: list[IssuePrimaryProviderCall] = []
    warnings: list[str] = []
    for context in contexts:
        old = reusable.get(context.issue_id)
        if old is not None and old.context_fingerprint == context.context_fingerprint:
            results.append(old)
            if context.issue_id in reusable_calls:
                calls.append(reusable_calls[context.issue_id])
            continue
        if not context.target_items:
            results.append(_no_contract_result(context))
            payload = _artifact_payload(
                job_id=job_id,
                status=IssuePrimaryAuditStatus.IN_PROGRESS,
                context_template=contexts[0],
                provider=provider.provider_name,
                model=provider.model_name,
                total_issue_count=len(contexts),
                results=results,
                calls=calls,
                warnings=warnings,
            )
            _persist_artifact(payload)
            continue

        try:
            begin_provider_call(job_id, provider.provider_name)
            try:
                provider_result: ProviderAuditResult = provider.generate(context)
            finally:
                finish_provider_call(job_id, provider.provider_name)
            result = validate_issue_model_output(provider_result.content, context)
        except (PipelineCancellationRequested, ProviderBoundaryPaused):
            payload = _artifact_payload(
                job_id=job_id,
                status=IssuePrimaryAuditStatus.INTERRUPTED,
                context_template=contexts[0],
                provider=provider.provider_name,
                model=provider.model_name,
                total_issue_count=len(contexts),
                results=results,
                calls=calls,
                warnings=[*warnings, "Stage 13E was interrupted by persisted provider/cancel control; completed issue results were checkpointed."],
            )
            _persist_artifact(payload)
            raise
        except (IssuePrimaryAuditProviderError, IssuePrimaryAuditValidationError) as exc:
            payload = _artifact_payload(
                job_id=job_id,
                status=IssuePrimaryAuditStatus.INTERRUPTED,
                context_template=contexts[0],
                provider=provider.provider_name,
                model=provider.model_name,
                total_issue_count=len(contexts),
                results=results,
                calls=calls,
                warnings=[*warnings, f"Issue {context.issue_id} interrupted Stage 13E: {exc}"],
            )
            _persist_artifact(payload)
            raise IssuePrimaryAuditError(str(exc)) from exc

        results.append(result)
        calls.append(
            IssuePrimaryProviderCall(
                issue_id=context.issue_id,
                provider=provider_result.provider,
                model=provider_result.model,
                request_id=provider_result.request_id,
                finish_reason=provider_result.finish_reason,
                raw_response_hash=provider_result.raw_response_hash,
                usage=provider_result.usage,
            )
        )
        payload = _artifact_payload(
            job_id=job_id,
            status=IssuePrimaryAuditStatus.IN_PROGRESS,
            context_template=contexts[0],
            provider=provider.provider_name,
            model=provider.model_name,
            total_issue_count=len(contexts),
            results=results,
            calls=calls,
            warnings=warnings,
        )
        _persist_artifact(payload)

    if {result.issue_id for result in results} != {context.issue_id for context in contexts}:
        raise IssuePrimaryAuditValidationError("Stage 13E completed without one terminal result for every AuditPlan issue.")
    final_payload = _artifact_payload(
        job_id=job_id,
        status=IssuePrimaryAuditStatus.COMPLETE,
        context_template=contexts[0],
        provider=provider.provider_name,
        model=provider.model_name,
        total_issue_count=len(contexts),
        results=results,
        calls=calls,
        warnings=warnings,
    )
    return _persist_artifact(final_payload)


def load_issue_primary_audit(job_id: UUID, *, validate_freshness: bool = True) -> IssuePrimaryAuditArtifact:
    path = job_issue_primary_audit_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Stage 13E issue-primary-audit.json does not exist for job {job_id}.")
    try:
        artifact = IssuePrimaryAuditArtifact.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise IssuePrimaryAuditValidationError("Persisted Stage 13E artifact is malformed.") from exc
    if artifact.job_id != job_id:
        raise IssuePrimaryAuditValidationError("Persisted Stage 13E artifact belongs to a different job.")
    payload = artifact.model_dump(mode="json", exclude={"artifact_fingerprint"})
    if artifact.artifact_fingerprint != _fingerprint(payload):
        raise IssuePrimaryAuditValidationError("Persisted Stage 13E artifact fingerprint is invalid.")
    if validate_freshness:
        try:
            legal_context = load_issue_legal_context(job_id)
        except (FileNotFoundError, IssueLegalContextError, IssueLegalContextStaleError) as exc:
            raise IssuePrimaryAuditStaleError("Stage 13E is stale because Stage 13D context is missing or stale.") from exc
        if artifact.issue_legal_context_fingerprint != legal_context.artifact_fingerprint:
            raise IssuePrimaryAuditStaleError("Stage 13E is stale because issue-legal-context.json changed.")
    return artifact
