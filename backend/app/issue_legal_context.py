from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .audit_planner import AuditPlannerError, load_audit_plan
from .issue_legal_context_models import (
    IssueLegalContextArtifact,
    IssueLegalEvidenceHit,
    IssueLegalEvidencePackage,
    IssueLegalSupportState,
    IssueRetrievalRun,
)
from .legal.retrieval import RetrievalIndexError, get_retrieval_index_summary, retrieve_legal_evidence
from .legal.retrieval_models import RetrievalRequest, RetrievalState
from .safe_persistence import atomic_write_text
from .storage import (
    job_issue_legal_context_path,
    legal_db_path,
    legal_retrieval_index_path,
)

MAX_TOTAL_RETRIEVAL_QUERIES = 2000


class IssueLegalContextError(RuntimeError):
    pass


class IssueLegalContextStaleError(IssueLegalContextError):
    pass


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _plan_fingerprint(plan) -> str:
    return _fingerprint(plan.model_dump(mode="json"))


def _index_fingerprint(index_summary) -> str:
    return _fingerprint(index_summary.model_dump(mode="json"))


def _support_state(runs: list[IssueRetrievalRun], hits: list[IssueLegalEvidenceHit]) -> IssueLegalSupportState:
    states = {run.response.state for run in runs}
    if hits:
        if states == {RetrievalState.OK}:
            return IssueLegalSupportState.EVIDENCE_FOUND
        return IssueLegalSupportState.EVIDENCE_FOUND_WITH_LIMITATIONS
    if states & {RetrievalState.NO_APPLICABLE_VERSION, RetrievalState.VERSION_AMBIGUOUS}:
        return IssueLegalSupportState.VERSION_REVIEW_REQUIRED
    return IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS


def _deduplicate_candidates(runs: list[IssueRetrievalRun]) -> list[IssueLegalEvidenceHit]:
    by_id: dict[str, dict[str, object]] = {}
    first_seen: list[str] = []
    for run in runs:
        for rank, candidate in enumerate(run.response.candidates, start=1):
            evidence_id = candidate.legal_evidence_id
            current = by_id.get(evidence_id)
            if current is None:
                by_id[evidence_id] = {
                    "query_indexes": [run.query_index],
                    "best_rank": rank,
                    "candidate": candidate,
                }
                first_seen.append(evidence_id)
                continue
            query_indexes = current["query_indexes"]
            assert isinstance(query_indexes, list)
            if run.query_index not in query_indexes:
                query_indexes.append(run.query_index)
            best_rank = int(current["best_rank"])
            current_candidate = current["candidate"]
            if rank < best_rank or (
                rank == best_rank
                and getattr(candidate, "exact_hit", False)
                and not getattr(current_candidate, "exact_hit", False)
            ):
                current["best_rank"] = rank
                current["candidate"] = candidate

    hits = [
        IssueLegalEvidenceHit(
            legal_evidence_id=evidence_id,
            matched_query_indexes=list(by_id[evidence_id]["query_indexes"]),
            best_rank=int(by_id[evidence_id]["best_rank"]),
            candidate=by_id[evidence_id]["candidate"],
        )
        for evidence_id in first_seen
    ]
    hits.sort(key=lambda item: (item.best_rank, not item.candidate.exact_hit, -item.candidate.fused_score, item.legal_evidence_id))
    return hits


def build_issue_legal_context(
    job_id: UUID,
    *,
    as_of: date,
    use_semantic: bool = False,
    top_k_per_query: int = 5,
) -> IssueLegalContextArtifact:
    try:
        plan = load_audit_plan(job_id)
    except (FileNotFoundError, AuditPlannerError) as exc:
        raise IssueLegalContextError("A validated audit-plan.json is required before issue-based Legal RAG.") from exc

    if not plan.coverage_complete:
        raise IssueLegalContextError(
            "Audit Plan coverage is incomplete. Law-Rag will not build issue Legal RAG from a partial planning scope."
        )
    if not plan.issues:
        raise IssueLegalContextError("Audit Plan contains no review issues.")

    query_count = 0
    for issue in plan.issues:
        if not issue.retrieval_queries:
            raise IssueLegalContextError(f"Audit issue {issue.issue_id} has no retrieval query.")
        query_count += len(issue.retrieval_queries)
    if query_count > MAX_TOTAL_RETRIEVAL_QUERIES:
        raise IssueLegalContextError(
            f"Audit Plan requests {query_count} Legal RAG queries, above the bounded limit of {MAX_TOTAL_RETRIEVAL_QUERIES}. "
            "Law-Rag did not silently omit planned issues."
        )

    index_summary = get_retrieval_index_summary(legal_retrieval_index_path(), legal_db_path())
    if not index_summary.ready or not index_summary.lexical_ready or not index_summary.legal_source_fingerprint:
        raise IssueLegalContextError(
            "The local legal retrieval index is not ready or is stale. Rebuild the legal retrieval index before issue-based Legal RAG."
        )

    issue_packages: list[IssueLegalEvidencePackage] = []
    artifact_warnings: list[str] = []
    lexical_versions: list[str] = []
    semantic_providers: list[str] = []
    semantic_models: list[str] = []
    for issue in plan.issues:
        runs: list[IssueRetrievalRun] = []
        issue_warnings: list[str] = []
        for query_index, query in enumerate(issue.retrieval_queries, start=1):
            response = retrieve_legal_evidence(
                legal_db_path(),
                legal_retrieval_index_path(),
                RetrievalRequest(
                    query=query,
                    as_of=as_of,
                    top_k=top_k_per_query,
                    use_semantic=use_semantic,
                ),
            )
            runs.append(IssueRetrievalRun(query_index=query_index, query=query, response=response))
            issue_warnings.extend(f"query {query_index}: {warning}" for warning in response.warnings)
            if response.lexical_index_version and response.lexical_index_version not in lexical_versions:
                lexical_versions.append(response.lexical_index_version)
            if response.semantic_provider and response.semantic_provider not in semantic_providers:
                semantic_providers.append(response.semantic_provider)
            if response.semantic_model and response.semantic_model not in semantic_models:
                semantic_models.append(response.semantic_model)

        hits = _deduplicate_candidates(runs)
        support_state = _support_state(runs, hits)
        if support_state == IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS:
            issue_warnings.append(
                "No legal evidence matched this issue in the current local corpus. This is not evidence that no applicable legal rule exists."
            )
        elif support_state == IssueLegalSupportState.VERSION_REVIEW_REQUIRED:
            issue_warnings.append(
                "Legal version resolution requires review for this issue; Law-Rag did not substitute another version automatically."
            )

        package = IssueLegalEvidencePackage(
            issue_id=issue.issue_id,
            topic=issue.topic,
            priority=issue.priority,
            sources=issue.sources,
            questions=issue.questions,
            contract_object_ids=issue.contract_object_ids,
            contract_evidence_ids=issue.contract_evidence_ids,
            retrieval_runs=runs,
            legal_evidence=hits,
            support_state=support_state,
            warnings=list(dict.fromkeys(issue_warnings)),
        )
        issue_packages.append(package)
        artifact_warnings.extend(f"{issue.topic}: {warning}" for warning in package.warnings)

    if len(lexical_versions) > 1 or len(semantic_providers) > 1 or len(semantic_models) > 1:
        raise IssueLegalContextError("Retrieval engine metadata changed during one issue-based Legal RAG build; no artifact was persisted.")

    base = {
        "schema_version": "1.0.0",
        "builder_version": "stage13d-1.0.0",
        "job_id": str(job_id),
        "as_of": as_of.isoformat(),
        "use_semantic": use_semantic,
        "top_k_per_query": top_k_per_query,
        "audit_plan_schema_version": plan.schema_version,
        "audit_planner_version": plan.planner_version,
        "audit_plan_fingerprint": _plan_fingerprint(plan),
        "contract_source_fingerprint": plan.contract_source_fingerprint,
        "contract_content_fingerprint": plan.contract_content_fingerprint,
        "legal_source_fingerprint": index_summary.legal_source_fingerprint,
        "retrieval_index_fingerprint": _index_fingerprint(index_summary),
        "retrieval_schema_version": index_summary.schema_version,
        "lexical_tokenizer": index_summary.lexical_tokenizer,
        "lexical_index_version": lexical_versions[0] if lexical_versions else None,
        "semantic_provider": semantic_providers[0] if semantic_providers else None,
        "semantic_model": semantic_models[0] if semantic_models else None,
        "total_issue_count": len(issue_packages),
        "total_query_count": query_count,
        "issues": [item.model_dump(mode="json") for item in issue_packages],
        "warnings": list(dict.fromkeys(artifact_warnings)),
    }
    artifact = IssueLegalContextArtifact(**base, artifact_fingerprint=_fingerprint(base))
    atomic_write_text(Path(job_issue_legal_context_path(job_id)), artifact.model_dump_json(indent=2))
    return artifact


def load_issue_legal_context(job_id: UUID, *, validate_freshness: bool = True) -> IssueLegalContextArtifact:
    path = job_issue_legal_context_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Issue legal context for job {job_id} does not exist.")
    try:
        artifact = IssueLegalContextArtifact.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise IssueLegalContextError("Persisted issue-legal-context.json is malformed and cannot be loaded safely.") from exc
    if artifact.job_id != job_id:
        raise IssueLegalContextError("Persisted issue-legal-context.json belongs to a different job ID.")

    if validate_freshness:
        try:
            plan = load_audit_plan(job_id)
        except (FileNotFoundError, AuditPlannerError) as exc:
            raise IssueLegalContextStaleError("The source Audit Plan is missing or unreadable.") from exc
        if artifact.audit_plan_fingerprint != _plan_fingerprint(plan):
            raise IssueLegalContextStaleError("Issue legal context is stale because audit-plan.json changed.")
        index_summary = get_retrieval_index_summary(legal_retrieval_index_path(), legal_db_path())
        if not index_summary.ready or artifact.legal_source_fingerprint != index_summary.legal_source_fingerprint:
            raise IssueLegalContextStaleError("Issue legal context is stale because the local legal corpus changed.")
        if artifact.retrieval_index_fingerprint != _index_fingerprint(index_summary):
            raise IssueLegalContextStaleError("Issue legal context is stale because the local retrieval index configuration changed.")
    return artifact
