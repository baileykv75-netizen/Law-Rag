from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import UUID

from pydantic import ValidationError

from .audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanPass,
    AuditPlanPassType,
    AuditPlanPlanningMode,
    AuditPlanSource,
    AuditPlanningCoverage,
    AuditPlanningCoverageState,
    AuditPlannerInput,
    ModelAuditPlanDraft,
    PlannerContractItem,
    PlannerGlobalFact,
    PlannerProviderResult,
    ReviewPriority,
)
from .audit_planner import (
    DIRECT_PLANNER_TEXT_CHAR_LIMIT,
    AuditPlannerError,
    AuditPlannerValidationError,
    _fingerprint,
    _global_facts,
    _legacy_hints,
    _object_text,
    _rule_hints,
    merge_audit_plan,
)
from .audit_planner_provider import AuditPlannerProvider
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report
from .contract_structure import StructureProcessingError, load_contract_structure
from .pipeline_control import begin_provider_call, ensure_pipeline_control, finish_provider_call
from .pipeline_control_models import ProviderExecutionMode
from .safe_persistence import atomic_write_text
from .storage import job_audit_plan_path

HIERARCHICAL_CHUNK_TARGET_CHARS = 18_000
HIERARCHICAL_CHUNK_MAX_ITEMS = 24
MAX_HIERARCHICAL_PROVIDER_PASSES = 256
GLOBAL_INDEX_TARGET_CHARS = 36_000
GLOBAL_INDEX_MIN_PREVIEW_CHARS = 24
GLOBAL_INDEX_MAX_PREVIEW_CHARS = 180


class HierarchicalAuditPlannerError(AuditPlannerError):
    pass


@dataclass(frozen=True)
class PlannerChunk:
    chunk_id: str
    items: tuple[PlannerContractItem, ...]
    text_chars: int


@dataclass(frozen=True)
class ChunkDraft:
    chunk: PlannerChunk
    planner_input: AuditPlannerInput
    draft: ModelAuditPlanDraft
    provider_result: PlannerProviderResult


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _input_from_parts(
    *,
    job_id: UUID,
    contract_schema_version: str,
    contract_source_fingerprint: str,
    contract_content_fingerprint: str,
    items: list[PlannerContractItem],
    facts: list[PlannerGlobalFact],
    rule_hints,
    topic_hints,
) -> AuditPlannerInput:
    total_text_chars = sum(len(item.text) for item in items) + sum(len(item.label) + len(item.value) for item in facts)
    base = {
        "job_id": str(job_id),
        "contract_schema_version": contract_schema_version,
        "contract_source_fingerprint": contract_source_fingerprint,
        "contract_content_fingerprint": contract_content_fingerprint,
        "contract_items": [item.model_dump(mode="json") for item in items],
        "global_facts": [item.model_dump(mode="json") for item in facts],
        "deterministic_rule_hints": [item.model_dump(mode="json") for item in rule_hints],
        "legacy_topic_hints": [item.model_dump(mode="json") for item in topic_hints],
        "total_text_chars": total_text_chars,
    }
    return AuditPlannerInput(**base, input_fingerprint=_fingerprint(base))


def build_clause_index(items: list[PlannerContractItem]) -> list[dict[str, object]]:
    return [
        {
            "order_index": index,
            "canonical_object_id": item.canonical_object_id,
            "object_type": item.object_type,
            "text_chars": len(item.text),
            "evidence_ids": item.evidence_ids,
        }
        for index, item in enumerate(items, start=1)
    ]


def build_planner_chunks(items: list[PlannerContractItem]) -> list[PlannerChunk]:
    chunks: list[PlannerChunk] = []
    current: list[PlannerContractItem] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        chunks.append(
            PlannerChunk(
                chunk_id=f"chunk-{len(chunks) + 1:04d}",
                items=tuple(current),
                text_chars=current_chars,
            )
        )
        current = []
        current_chars = 0

    for item in items:
        size = len(item.text)
        if size > DIRECT_PLANNER_TEXT_CHAR_LIMIT:
            raise HierarchicalAuditPlannerError(
                f"Canonical object {item.canonical_object_id} has {size} characters, above the maximum bounded Planner request size "
                f"of {DIRECT_PLANNER_TEXT_CHAR_LIMIT}. Law-Rag did not truncate this object."
            )
        would_exceed = current and (
            current_chars + size > HIERARCHICAL_CHUNK_TARGET_CHARS
            or len(current) >= HIERARCHICAL_CHUNK_MAX_ITEMS
        )
        if would_exceed:
            flush()
        current.append(item)
        current_chars += size
        if current_chars >= HIERARCHICAL_CHUNK_TARGET_CHARS or len(current) >= HIERARCHICAL_CHUNK_MAX_ITEMS:
            flush()
    flush()
    if len(chunks) + 1 > MAX_HIERARCHICAL_PROVIDER_PASSES:
        raise HierarchicalAuditPlannerError(
            f"Hierarchical planning would require {len(chunks) + 1} external Planner passes, above the bounded limit "
            f"of {MAX_HIERARCHICAL_PROVIDER_PASSES}. No Planner request was started."
        )
    return chunks


def _filter_rule_hints(rule_hints, object_ids: set[str]):
    output = []
    for hint in rule_hints:
        ids = [value for value in hint.canonical_object_ids if value in object_ids]
        if hint.canonical_object_ids and not ids:
            continue
        output.append(hint.model_copy(update={"canonical_object_ids": ids}))
    return output


def _filter_topic_hints(topic_hints, object_ids: set[str]):
    output = []
    for hint in topic_hints:
        ids = [value for value in hint.contract_object_ids if value in object_ids]
        if ids:
            output.append(hint.model_copy(update={"contract_object_ids": ids}))
    return output


def _parse_draft(result: PlannerProviderResult, *, label: str) -> ModelAuditPlanDraft:
    try:
        return ModelAuditPlanDraft.model_validate_json(result.content)
    except ValidationError as exc:
        raise AuditPlannerValidationError(f"{label} returned JSON that does not match the strict AuditPlan draft schema.") from exc


def _run_provider_pass(
    job_id: UUID,
    provider: AuditPlannerProvider,
    planner_input: AuditPlannerInput,
    *,
    boundary_suffix: str,
    label: str,
) -> tuple[ModelAuditPlanDraft, PlannerProviderResult]:
    boundary_name = f"{provider.provider_name}-planner-{boundary_suffix}"
    begin_provider_call(job_id, boundary_name)
    try:
        result = provider.generate(planner_input)
    finally:
        finish_provider_call(job_id, boundary_name)
    return _parse_draft(result, label=label), result


def _compact_preview(text: str, limit: int) -> str:
    single = " ".join(text.split())
    if len(single) <= limit:
        return single
    return single[: max(0, limit - 1)].rstrip() + "…"


def _topic_key(value: str) -> str:
    return "".join(value.lower().split())


def _priority_max(left: ReviewPriority, right: ReviewPriority) -> ReviewPriority:
    rank = {ReviewPriority.NORMAL: 0, ReviewPriority.IMPORTANT: 1, ReviewPriority.HIGH_ATTENTION: 2}
    return left if rank[left] >= rank[right] else right


def _global_summary_facts(chunk_drafts: list[ChunkDraft]) -> list[PlannerGlobalFact]:
    """Compact local Planner outputs for global synthesis without dropping final-plan data.

    Full local drafts are preserved separately and merged into the final AuditPlan after
    the global pass. The global pass receives a deterministic topic-level summary only,
    so its bounded input does not grow with every local question/retrieval phrase.
    """

    facts: list[PlannerGlobalFact] = []
    classifications: dict[str, int] = {}
    aggregated: dict[str, dict[str, object]] = {}

    for chunk_draft in chunk_drafts:
        draft = chunk_draft.draft
        classification = f"{draft.contract_type.value}/{draft.contract_type_confidence.value}"
        classifications[classification] = classifications.get(classification, 0) + 1
        for issue in draft.issues:
            key = _topic_key(issue.topic)
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = {
                    "topic": issue.topic,
                    "priority": issue.priority,
                    "occurrences": 1,
                    "object_ids": list(issue.contract_object_ids),
                }
                continue
            current["priority"] = _priority_max(current["priority"], issue.priority)  # type: ignore[arg-type]
            current["occurrences"] = int(current["occurrences"]) + 1
            current["object_ids"] = _unique([*current["object_ids"], *issue.contract_object_ids])  # type: ignore[list-item]

    for classification in sorted(classifications):
        facts.append(
            PlannerGlobalFact(
                fact_id="local-classification-" + hashlib.sha256(classification.encode("utf-8")).hexdigest()[:12],
                fact_type="LOCAL_PLANNER_CLASSIFICATION",
                label=classification,
                value=f"local_pass_count={classifications[classification]}",
            )
        )

    for key in sorted(aggregated):
        item = aggregated[key]
        object_ids = item["object_ids"]
        facts.append(
            PlannerGlobalFact(
                fact_id="local-topic-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
                fact_type="LOCAL_PLANNER_ISSUE",
                label=str(item["topic"]),
                value=(
                    f"priority={item['priority'].value}; occurrences={item['occurrences']}; "
                    f"objects={','.join(object_ids) or '<none>'}"
                ),
            )
        )
    return facts


def _build_global_input(
    *,
    job_id: UUID,
    contract_schema_version: str,
    contract_source_fingerprint: str,
    contract_content_fingerprint: str,
    items: list[PlannerContractItem],
    base_facts: list[PlannerGlobalFact],
    rule_hints,
    topic_hints,
    chunk_drafts: list[ChunkDraft],
) -> AuditPlannerInput:
    if not items:
        preview_limit = GLOBAL_INDEX_MAX_PREVIEW_CHARS
    else:
        available = max(GLOBAL_INDEX_MIN_PREVIEW_CHARS, GLOBAL_INDEX_TARGET_CHARS // len(items))
        preview_limit = min(GLOBAL_INDEX_MAX_PREVIEW_CHARS, available)

    summary_items = [
        PlannerContractItem(
            canonical_object_id=item.canonical_object_id,
            object_type=f"{item.object_type}_INDEX_SUMMARY",
            text=_compact_preview(item.text, preview_limit),
            evidence_ids=item.evidence_ids,
        )
        for item in items
    ]
    facts = [*base_facts, *_global_summary_facts(chunk_drafts)]
    global_input = _input_from_parts(
        job_id=job_id,
        contract_schema_version=contract_schema_version,
        contract_source_fingerprint=contract_source_fingerprint,
        contract_content_fingerprint=contract_content_fingerprint,
        items=summary_items,
        facts=facts,
        rule_hints=rule_hints,
        topic_hints=topic_hints,
    )
    if global_input.total_text_chars > DIRECT_PLANNER_TEXT_CHAR_LIMIT:
        raise HierarchicalAuditPlannerError(
            "Hierarchical local planning completed, but the bounded global synthesis index still exceeds the Planner request budget. "
            "Law-Rag preserved every local draft and did not silently drop planning topics; a deeper reduction layer is required for this unusually large structure."
        )
    return global_input


def _aggregate_usage(results: list[PlannerProviderResult]):
    from .ai_audit_models import ProviderUsage

    def total(field: str) -> int | None:
        values = [getattr(result.usage, field) for result in results if getattr(result.usage, field) is not None]
        return sum(values) if values else None

    return ProviderUsage(
        prompt_tokens=total("prompt_tokens"),
        completion_tokens=total("completion_tokens"),
        total_tokens=total("total_tokens"),
    )


def _combined_response_hash(results: list[PlannerProviderResult]) -> str:
    payload = "\n".join(result.raw_response_hash for result in results)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pass_records(chunk_drafts: list[ChunkDraft], global_input: AuditPlannerInput, global_result: PlannerProviderResult) -> list[AuditPlanPass]:
    records: list[AuditPlanPass] = []
    for item in chunk_drafts:
        records.append(
            AuditPlanPass(
                pass_id=item.chunk.chunk_id,
                pass_type=AuditPlanPassType.CHUNK,
                contract_object_ids=[value.canonical_object_id for value in item.chunk.items],
                input_fingerprint=item.planner_input.input_fingerprint,
                response_hash=item.provider_result.raw_response_hash,
                provider_request_id=item.provider_result.request_id,
                provider_usage=item.provider_result.usage,
            )
        )
    records.append(
        AuditPlanPass(
            pass_id="global-0001",
            pass_type=AuditPlanPassType.GLOBAL,
            contract_object_ids=[item.canonical_object_id for item in global_input.contract_items],
            input_fingerprint=global_input.input_fingerprint,
            response_hash=global_result.raw_response_hash,
            provider_request_id=global_result.request_id,
            provider_usage=global_result.usage,
        )
    )
    return records


def _merge_issue(target: AuditPlanIssue, source: AuditPlanIssue) -> None:
    target.priority = _priority_max(target.priority, source.priority)
    target.sources = list(dict.fromkeys([*target.sources, *source.sources]))
    target.why_review = _unique([*target.why_review, *source.why_review])
    target.contract_object_ids = _unique([*target.contract_object_ids, *source.contract_object_ids])
    target.contract_evidence_ids = _unique([*target.contract_evidence_ids, *source.contract_evidence_ids])
    target.questions = _unique([*target.questions, *source.questions])
    target.retrieval_queries = _unique([*target.retrieval_queries, *source.retrieval_queries])
    target.rule_result_ids = _unique([*target.rule_result_ids, *source.rule_result_ids])
    target.legacy_hint_topics = _unique([*target.legacy_hint_topics, *source.legacy_hint_topics])


def _merge_local_dynamic_issues(plan: AuditPlan, full_input: AuditPlannerInput, chunk_drafts: list[ChunkDraft]) -> None:
    by_id = {item.issue_id: item for item in plan.issues}
    for chunk_draft in chunk_drafts:
        local_plan = merge_audit_plan(full_input, chunk_draft.draft, chunk_draft.provider_result)
        for issue in local_plan.issues:
            if AuditPlanSource.LLM_DYNAMIC not in issue.sources:
                continue
            existing = by_id.get(issue.issue_id)
            if existing is None:
                plan.issues.append(issue)
                by_id[issue.issue_id] = issue
            else:
                _merge_issue(existing, issue)

    priority_rank = {ReviewPriority.HIGH_ATTENTION: 0, ReviewPriority.IMPORTANT: 1, ReviewPriority.NORMAL: 2}
    plan.issues = sorted(plan.issues, key=lambda item: (priority_rank[item.priority], item.topic, item.issue_id))


def _coverage(items: list[PlannerContractItem], chunks: list[PlannerChunk], plan: AuditPlan) -> list[AuditPlanningCoverage]:
    chunk_ids_by_object: dict[str, list[str]] = {item.canonical_object_id: [] for item in items}
    for chunk in chunks:
        for item in chunk.items:
            chunk_ids_by_object[item.canonical_object_id].append(chunk.chunk_id)

    issues_by_object: dict[str, list[str]] = {item.canonical_object_id: [] for item in items}
    for issue in plan.issues:
        for object_id in issue.contract_object_ids:
            if object_id in issues_by_object:
                issues_by_object[object_id].append(issue.issue_id)

    output: list[AuditPlanningCoverage] = []
    for item in items:
        issue_ids = _unique(issues_by_object[item.canonical_object_id])
        output.append(
            AuditPlanningCoverage(
                canonical_object_id=item.canonical_object_id,
                object_type=item.object_type,
                chunk_ids=chunk_ids_by_object[item.canonical_object_id],
                state=(
                    AuditPlanningCoverageState.REVIEWED_WITH_ISSUE
                    if issue_ids
                    else AuditPlanningCoverageState.REVIEWED_NO_SPECIFIC_ISSUE
                ),
                issue_ids=issue_ids,
            )
        )
    return output


def run_hierarchical_audit_planner(job_id: UUID, *, provider: AuditPlannerProvider) -> AuditPlan:
    try:
        contract = load_contract_structure(job_id)
    except (FileNotFoundError, StructureProcessingError) as exc:
        raise AuditPlannerError("Canonical contract structure is required before Audit Planner.") from exc
    try:
        rules = load_audit_rule_report(job_id)
    except (FileNotFoundError, AuditRuleProcessingError) as exc:
        raise AuditPlannerError("Deterministic audit-rules.json is required before Audit Planner.") from exc

    items = _object_text(contract)
    facts = _global_facts(contract)
    rule_hints = _rule_hints(rules)
    topic_hints = _legacy_hints(items)
    chunks = build_planner_chunks(items)
    if not chunks:
        raise HierarchicalAuditPlannerError("Hierarchical planning requires at least one canonical clause/block object.")

    ensure_pipeline_control(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)
    chunk_drafts: list[ChunkDraft] = []
    for chunk in chunks:
        object_ids = {item.canonical_object_id for item in chunk.items}
        planner_input = _input_from_parts(
            job_id=job_id,
            contract_schema_version=contract.schema_version,
            contract_source_fingerprint=contract.source_fingerprint,
            contract_content_fingerprint=rules.contract_content_fingerprint,
            items=list(chunk.items),
            facts=facts,
            rule_hints=_filter_rule_hints(rule_hints, object_ids),
            topic_hints=_filter_topic_hints(topic_hints, object_ids),
        )
        if planner_input.total_text_chars > DIRECT_PLANNER_TEXT_CHAR_LIMIT:
            raise HierarchicalAuditPlannerError(
                f"Chunk {chunk.chunk_id} exceeds the bounded Planner request budget after global facts are included; no provider request was made for that chunk."
            )
        draft, provider_result = _run_provider_pass(
            job_id,
            provider,
            planner_input,
            boundary_suffix=chunk.chunk_id,
            label=chunk.chunk_id,
        )
        # Validate each local draft immediately against only the canonical objects actually shown in the chunk.
        merge_audit_plan(planner_input, draft, provider_result)
        chunk_drafts.append(ChunkDraft(chunk=chunk, planner_input=planner_input, draft=draft, provider_result=provider_result))

    global_input = _build_global_input(
        job_id=job_id,
        contract_schema_version=contract.schema_version,
        contract_source_fingerprint=contract.source_fingerprint,
        contract_content_fingerprint=rules.contract_content_fingerprint,
        items=items,
        base_facts=facts,
        rule_hints=rule_hints,
        topic_hints=topic_hints,
        chunk_drafts=chunk_drafts,
    )
    global_draft, global_result = _run_provider_pass(
        job_id,
        provider,
        global_input,
        boundary_suffix="global-0001",
        label="global Planner",
    )
    # The global pass may reference any canonical object in the compact clause index.
    merge_audit_plan(global_input, global_draft, global_result)

    all_results = [item.provider_result for item in chunk_drafts] + [global_result]
    synthetic_result = PlannerProviderResult(
        provider=global_result.provider,
        model=global_result.model,
        base_url=global_result.base_url,
        request_id=global_result.request_id,
        finish_reason=global_result.finish_reason,
        content=global_draft.model_dump_json(),
        raw_response_hash=_combined_response_hash(all_results),
        usage=_aggregate_usage(all_results),
    )
    full_input = _input_from_parts(
        job_id=job_id,
        contract_schema_version=contract.schema_version,
        contract_source_fingerprint=contract.source_fingerprint,
        contract_content_fingerprint=rules.contract_content_fingerprint,
        items=items,
        facts=facts,
        rule_hints=rule_hints,
        topic_hints=topic_hints,
    )
    plan = merge_audit_plan(full_input, global_draft, synthetic_result)
    _merge_local_dynamic_issues(plan, full_input, chunk_drafts)
    plan.planning_mode = AuditPlanPlanningMode.HIERARCHICAL
    plan.planner_passes = _pass_records(chunk_drafts, global_input, global_result)
    plan.coverage = _coverage(items, chunks, plan)
    plan.coverage_complete = len(plan.coverage) == len(items) and all(item.chunk_ids for item in plan.coverage)
    if not plan.coverage_complete:
        raise HierarchicalAuditPlannerError("Hierarchical planning coverage is incomplete; Law-Rag refused to persist a partial AuditPlan.")
    plan.warnings.append(
        f"Hierarchical Planner reviewed {len(items)} canonical objects across {len(chunks)} local chunk pass(es) plus one global synthesis pass."
    )
    atomic_write_text(Path(job_audit_plan_path(job_id)), plan.model_dump_json(indent=2))
    return plan
