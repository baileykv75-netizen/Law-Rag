from __future__ import annotations

from copy import deepcopy
from datetime import date
from uuid import UUID

from .contract_models import CanonicalContract, Clause, SourceSpan
from .contract_structure import StructureProcessingError, load_contract_structure
from .legal.models import VersionResolutionState
from .legal.retrieval import retrieve_legal_evidence
from .legal.retrieval_models import RetrievalRequest
from .legal.store import get_evidence, resolve_version
from .review_comparison_models import (
    AgentActionRecord,
    AgentActionState,
    AgentToolName,
)
from .storage import legal_db_path, legal_retrieval_index_path


class AgentToolExecutionError(RuntimeError):
    pass


def _all_spanned_objects(contract: CanonicalContract):
    collections = [
        ("TITLE_CANDIDATE", contract.title_candidates, "candidate_id"),
        ("CLAUSE", contract.clauses, "clause_id"),
        ("UNNUMBERED_BLOCK", contract.unnumbered_blocks, "block_id"),
        ("PARTY_MENTION", contract.parties, "mention_id"),
        ("DATE_MENTION", contract.dates, "mention_id"),
        ("MONEY_MENTION", contract.money_mentions, "mention_id"),
        ("PERCENTAGE_MENTION", contract.percentages, "mention_id"),
        ("IDENTIFIER_MENTION", contract.identifiers, "mention_id"),
        ("REFERENCE_MENTION", contract.references, "reference_id"),
        ("STRUCTURED_BLOCK", contract.structured_blocks, "block_id"),
    ]
    for object_type, items, id_field in collections:
        for item in items:
            yield object_type, str(getattr(item, id_field)), item, item.source_spans


def _span_payload(span: SourceSpan) -> dict:
    return span.model_dump(mode="json")


def _load_contract(job_id: UUID) -> CanonicalContract:
    try:
        return load_contract_structure(job_id)
    except (FileNotFoundError, StructureProcessingError) as exc:
        raise AgentToolExecutionError("Canonical contract is unavailable for Agent tool execution.") from exc


def _finish(
    action: AgentActionRecord,
    *,
    state: AgentActionState,
    output_ids: list[str] | None = None,
    payload: dict | None = None,
    error: str | None = None,
) -> AgentActionRecord:
    result = deepcopy(action)
    result.state = state
    result.output_evidence_ids = sorted(set(output_ids or []))
    result.result_payload = payload or {}
    result.validation_or_error = error
    # Stage 9 tools in this module are local-only. If a future tool performs a
    # provider/network call it must explicitly override these fields.
    result.provider_call_occurred = False
    result.private_contract_evidence_left_machine = False
    return result


def _inspect_contract_evidence(job_id: UUID, action: AgentActionRecord) -> AgentActionRecord:
    contract = _load_contract(job_id)
    requested = set(action.input_evidence_ids)
    if not requested:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error="inspect_contract_evidence requires explicit input Evidence IDs.",
        )

    hits: list[dict] = []
    found: set[str] = set()
    for object_type, object_id, item, spans in _all_spanned_objects(contract):
        for span in spans:
            matched = requested & set(span.evidence_ids)
            if not matched:
                continue
            found.update(matched)
            hits.append(
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "matched_evidence_ids": sorted(matched),
                    "source_span": _span_payload(span),
                }
            )

    missing = sorted(requested - found)
    if missing:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            output_ids=sorted(found),
            payload={"hits": hits, "missing_evidence_ids": missing},
            error=f"Unknown canonical contract Evidence IDs: {missing}",
        )
    return _finish(
        action,
        state=AgentActionState.COMPLETED,
        output_ids=sorted(found),
        payload={"hits": hits},
    )


def _clause_payload(clause: Clause) -> dict:
    return {
        "clause_id": clause.clause_id,
        "heading_token": clause.heading_token,
        "heading_text": clause.heading_text,
        "body_text": clause.body_text,
        "level": clause.level,
        "parent_clause_id": clause.parent_clause_id,
        "page_start": clause.page_start,
        "page_end": clause.page_end,
        "source_spans": [span.model_dump(mode="json") for span in clause.source_spans],
    }


def _get_clause_context(job_id: UUID, action: AgentActionRecord) -> AgentActionRecord:
    contract = _load_contract(job_id)
    clause_id = str(action.normalized_arguments.get("clause_id") or "").strip()
    if not clause_id:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error="get_clause_context requires a canonical clause_id.",
        )
    by_id = {clause.clause_id: clause for clause in contract.clauses}
    target = by_id.get(clause_id)
    if target is None:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error=f"Unknown canonical clause_id: {clause_id}",
        )

    ordered = contract.clauses
    index = next(i for i, clause in enumerate(ordered) if clause.clause_id == clause_id)
    context: list[Clause] = [target]
    if target.parent_clause_id and target.parent_clause_id in by_id:
        context.append(by_id[target.parent_clause_id])
    if index > 0:
        context.append(ordered[index - 1])
    if index + 1 < len(ordered):
        context.append(ordered[index + 1])
    context.extend(clause for clause in ordered if clause.parent_clause_id == clause_id)

    unique: dict[str, Clause] = {clause.clause_id: clause for clause in context}
    output_ids = sorted(
        {
            evidence_id
            for clause in unique.values()
            for span in clause.source_spans
            for evidence_id in span.evidence_ids
        }
    )
    return _finish(
        action,
        state=AgentActionState.COMPLETED,
        output_ids=output_ids,
        payload={
            "target_clause_id": clause_id,
            "clauses": [_clause_payload(unique[key]) for key in sorted(unique)],
        },
    )


def _inspect_legal_evidence(action: AgentActionRecord, *, as_of: date) -> AgentActionRecord:
    requested = action.normalized_arguments.get("legal_evidence_ids") or action.input_evidence_ids
    legal_ids = [str(item) for item in requested]
    if not legal_ids:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error="inspect_legal_evidence requires explicit Legal Evidence IDs.",
        )

    records: list[dict] = []
    output_ids: list[str] = []
    try:
        for legal_id in legal_ids:
            evidence = get_evidence(legal_db_path(), legal_id)
            resolution = resolve_version(legal_db_path(), evidence.authority.authority_id, as_of)
            if resolution.state != VersionResolutionState.RESOLVED or resolution.version is None:
                return _finish(
                    action,
                    state=AgentActionState.REJECTED,
                    output_ids=output_ids,
                    payload={"records": records},
                    error=f"Legal version is not deterministically resolved for {legal_id} on {as_of}.",
                )
            if resolution.version.version_id != evidence.version.version_id:
                return _finish(
                    action,
                    state=AgentActionState.REJECTED,
                    output_ids=output_ids,
                    payload={"records": records},
                    error=(
                        f"Legal Evidence {legal_id} is stale for {as_of}; "
                        f"applicable version is {resolution.version.version_id}."
                    ),
                )
            records.append(evidence.model_dump(mode="json"))
            output_ids.append(legal_id)
    except FileNotFoundError as exc:
        return _finish(action, state=AgentActionState.REJECTED, error=str(exc))

    return _finish(
        action,
        state=AgentActionState.COMPLETED,
        output_ids=output_ids,
        payload={"as_of": as_of.isoformat(), "records": records},
    )


def _retrieve_more_legal(action: AgentActionRecord, *, as_of: date) -> AgentActionRecord:
    query = str(action.normalized_arguments.get("query") or "").strip()
    if not query or len(query) > 500:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error="retrieve_more_legal requires a non-empty query of at most 500 characters.",
        )
    try:
        response = retrieve_legal_evidence(
            legal_db_path(),
            legal_retrieval_index_path(),
            RetrievalRequest(query=query, as_of=as_of, top_k=5, use_semantic=False),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _finish(action, state=AgentActionState.FAILED, error=str(exc))

    output_ids = [candidate.legal_evidence_id for candidate in response.candidates]
    return _finish(
        action,
        state=AgentActionState.COMPLETED,
        output_ids=output_ids,
        payload={"query": query, "as_of": as_of.isoformat(), "retrieval": response.model_dump(mode="json")},
    )


def _resolve_contract_reference(job_id: UUID, action: AgentActionRecord) -> AgentActionRecord:
    contract = _load_contract(job_id)
    reference_id = str(action.normalized_arguments.get("reference_id") or "").strip()
    if not reference_id:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error="resolve_contract_reference requires reference_id.",
        )
    reference = next((item for item in contract.references if item.reference_id == reference_id), None)
    if reference is None:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error=f"Unknown canonical reference_id: {reference_id}",
        )
    output_ids = sorted({eid for span in reference.source_spans for eid in span.evidence_ids})
    return _finish(
        action,
        state=AgentActionState.COMPLETED,
        output_ids=output_ids,
        payload={"reference": reference.model_dump(mode="json")},
    )


def _request_ocr_retry(job_id: UUID, action: AgentActionRecord) -> AgentActionRecord:
    contract = _load_contract(job_id)
    requested = set(action.input_evidence_ids)
    ocr_ids: set[str] = set()
    for _, _, _, spans in _all_spanned_objects(contract):
        for span in spans:
            if span.source_method.value == "ocr":
                ocr_ids.update(requested & set(span.evidence_ids))
    if not ocr_ids:
        return _finish(
            action,
            state=AgentActionState.REJECTED,
            error="request_ocr_retry is only applicable to cited OCR-derived Evidence IDs.",
        )
    return _finish(
        action,
        state=AgentActionState.UNAVAILABLE,
        output_ids=sorted(ocr_ids),
        payload={"eligible_ocr_evidence_ids": sorted(ocr_ids)},
        error="OCR retry execution is not configured in the current Stage 9C tool runner.",
    )


def execute_agent_action(
    job_id: UUID,
    action: AgentActionRecord,
    *,
    as_of: date,
) -> AgentActionRecord:
    if action.state != AgentActionState.REQUESTED:
        raise AgentToolExecutionError("Only REQUESTED Agent actions may be executed.")

    if action.tool_name == AgentToolName.INSPECT_CONTRACT_EVIDENCE:
        return _inspect_contract_evidence(job_id, action)
    if action.tool_name == AgentToolName.GET_CLAUSE_CONTEXT:
        return _get_clause_context(job_id, action)
    if action.tool_name == AgentToolName.INSPECT_LEGAL_EVIDENCE:
        return _inspect_legal_evidence(action, as_of=as_of)
    if action.tool_name == AgentToolName.RETRIEVE_MORE_LEGAL:
        return _retrieve_more_legal(action, as_of=as_of)
    if action.tool_name == AgentToolName.RESOLVE_CONTRACT_REFERENCE:
        return _resolve_contract_reference(job_id, action)
    if action.tool_name == AgentToolName.REQUEST_OCR_RETRY:
        return _request_ocr_retry(job_id, action)

    # This branch should be unreachable because AgentToolName is an Enum, but
    # it remains fail-closed if the schema changes in the future.
    return _finish(
        action,
        state=AgentActionState.REJECTED,
        error=f"Tool is not in the executable allowlist: {action.tool_name}",
    )
