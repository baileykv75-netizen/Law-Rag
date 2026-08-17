from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .ai_audit_context import AiAuditContextError, build_audit_context
from .ai_audit_models import (
    AiAuditFinding,
    AiAuditReport,
    AiAuditRunRequest,
    AuditContextPackage,
    EvidenceSufficiency,
    FindingState,
    ModelAuditEnvelope,
)
from .ai_audit_providers import (
    PrimaryAuditProvider,
    PrimaryAuditProviderError,
    provider_from_name,
)
from .legal.models import VersionResolutionState
from .legal.retrieval_models import RetrievalState
from .legal.store import get_evidence, resolve_version
from .models import SourceMethod
from .storage import job_ai_audit_path, legal_db_path


class AiAuditError(RuntimeError):
    pass


class AiAuditConfigurationError(AiAuditError):
    pass


class AiAuditValidationError(AiAuditError):
    pass


OCR_REVIEW_THRESHOLD = 0.85


def _allowed_context_ids(context: AuditContextPackage) -> tuple[set[str], set[str], set[str], set[str]]:
    issue_ids = {issue.issue_id for issue in context.issues}
    object_ids = {item.canonical_object_id for item in context.contract_items}
    evidence_ids = {eid for item in context.contract_items for eid in item.evidence_ids}
    for rule in context.rule_items:
        object_ids.update(rule.canonical_object_ids)
        evidence_ids.update(rule.evidence_ids)
    legal_ids = {
        candidate.legal_evidence_id
        for issue in context.issues
        for candidate in issue.retrieval.candidates
    }
    return issue_ids, object_ids, evidence_ids, legal_ids


def _issue_map(context: AuditContextPackage) -> dict[str, object]:
    return {issue.issue_id: issue for issue in context.issues}


def _source_is_uncertain(context: AuditContextPackage, cited_evidence_ids: list[str]) -> bool:
    cited = set(cited_evidence_ids)
    spans = []
    for item in context.contract_items:
        if cited.intersection(item.evidence_ids):
            spans.extend(item.source_spans)
    for rule in context.rule_items:
        if cited.intersection(rule.evidence_ids):
            spans.extend(rule.source_spans)
    for span in spans:
        if span.source_method != SourceMethod.OCR:
            continue
        if span.confidence is None or span.confidence < OCR_REVIEW_THRESHOLD:
            return True
    return False


def _validate_legal_applicability(legal_ids: list[str], context: AuditContextPackage) -> None:
    db = legal_db_path()
    for legal_id in legal_ids:
        evidence = get_evidence(db, legal_id)
        resolution = resolve_version(db, evidence.authority.authority_id, context.as_of)
        if resolution.state != VersionResolutionState.RESOLVED or resolution.version is None:
            raise AiAuditValidationError(
                f"Legal Evidence ID {legal_id} is not deterministically applicable on {context.as_of}."
            )
        if resolution.version.version_id != evidence.version.version_id:
            raise AiAuditValidationError(
                f"Legal Evidence ID {legal_id} uses version {evidence.version.version_id}, but {resolution.version.version_id} applies on {context.as_of}."
            )


def _evidence_sufficiency(context: AuditContextPackage, issue_ids: list[str], contract_evidence_ids: list[str]) -> tuple[EvidenceSufficiency, list[str]]:
    issue_by_id = _issue_map(context)
    states = [issue_by_id[item].retrieval.state for item in issue_ids if item in issue_by_id]
    reasons: list[str] = []
    if any(state in {RetrievalState.VERSION_AMBIGUOUS, RetrievalState.NO_APPLICABLE_VERSION} for state in states):
        reasons.append("LEGAL_VERSION_UNCERTAIN")
        return EvidenceSufficiency.VERSION_UNCERTAIN, reasons
    if any(state in {RetrievalState.INSUFFICIENT_CORPUS, RetrievalState.INDEX_NOT_READY} for state in states):
        reasons.append("INSUFFICIENT_LEGAL_CORPUS")
        return EvidenceSufficiency.INSUFFICIENT_CORPUS, reasons
    if _source_is_uncertain(context, contract_evidence_ids):
        reasons.append("SOURCE_OCR_UNCERTAIN")
        return EvidenceSufficiency.SOURCE_UNCERTAIN, reasons
    if any(state == RetrievalState.PARTIAL_COVERAGE for state in states):
        reasons.append("PARTIAL_LEGAL_CORPUS")
        return EvidenceSufficiency.PARTIAL_CORPUS, reasons
    return EvidenceSufficiency.SUFFICIENT, reasons


def _finding_id(context_fingerprint: str, payload: dict) -> str:
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{context_fingerprint}:{value}".encode("utf-8")).hexdigest()[:20]
    return f"finding-{digest}"


def validate_model_output(content: str, context: AuditContextPackage) -> list[AiAuditFinding]:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AiAuditValidationError(f"Primary model did not return valid JSON: {exc}") from exc
    try:
        envelope = ModelAuditEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise AiAuditValidationError(f"Primary model JSON does not match the Stage 8 schema: {exc}") from exc

    allowed_issues, allowed_objects, allowed_contract_evidence, allowed_legal = _allowed_context_ids(context)
    seen_client_ids: set[str] = set()
    findings: list[AiAuditFinding] = []
    issue_by_id = _issue_map(context)

    for draft in envelope.findings:
        if draft.client_finding_id in seen_client_ids:
            raise AiAuditValidationError(f"Duplicate client_finding_id: {draft.client_finding_id}")
        seen_client_ids.add(draft.client_finding_id)

        unknown_issues = set(draft.issue_ids) - allowed_issues
        unknown_objects = set(draft.canonical_object_ids) - allowed_objects
        unknown_contract = set(draft.contract_evidence_ids) - allowed_contract_evidence
        unknown_legal = set(draft.legal_evidence_ids) - allowed_legal
        if unknown_issues:
            raise AiAuditValidationError(f"Model invented or cited unsupplied issue IDs: {sorted(unknown_issues)}")
        if unknown_objects:
            raise AiAuditValidationError(f"Model invented or cited unsupplied canonical object IDs: {sorted(unknown_objects)}")
        if unknown_contract:
            raise AiAuditValidationError(f"Model invented or cited unsupplied contract Evidence IDs: {sorted(unknown_contract)}")
        if unknown_legal:
            raise AiAuditValidationError(f"Model invented or cited unsupplied Legal Evidence IDs: {sorted(unknown_legal)}")

        if draft.legal_evidence_ids and not draft.issue_ids:
            raise AiAuditValidationError("A finding citing legal evidence must cite at least one supplied issue package.")
        issue_legal_ids = {
            candidate.legal_evidence_id
            for issue_id in draft.issue_ids
            for candidate in issue_by_id[issue_id].retrieval.candidates
        }
        if set(draft.legal_evidence_ids) - issue_legal_ids:
            raise AiAuditValidationError(
                "A finding cited Legal Evidence outside the issue packages it referenced."
            )
        if draft.state == FindingState.SUPPORTED_FINDING:
            if not draft.contract_evidence_ids:
                raise AiAuditValidationError("SUPPORTED_FINDING must cite supplied contract evidence.")
            if not draft.legal_evidence_ids:
                raise AiAuditValidationError("SUPPORTED_FINDING must cite supplied Legal Evidence.")

        _validate_legal_applicability(draft.legal_evidence_ids, context)
        sufficiency, deterministic_reasons = _evidence_sufficiency(
            context, draft.issue_ids, draft.contract_evidence_ids
        )
        review_reasons = list(dict.fromkeys([*draft.review_reasons, *deterministic_reasons]))
        final_state = draft.state
        if draft.state == FindingState.NO_FINDING and sufficiency != EvidenceSufficiency.SUFFICIENT:
            final_state = FindingState.REVIEW_REQUIRED
            review_reasons.append("NO_FINDING_NOT_ALLOWED_WITH_INCOMPLETE_EVIDENCE")
        if draft.state == FindingState.SUPPORTED_FINDING and sufficiency in {
            EvidenceSufficiency.INSUFFICIENT_CORPUS,
            EvidenceSufficiency.VERSION_UNCERTAIN,
            EvidenceSufficiency.SOURCE_UNCERTAIN,
        }:
            final_state = FindingState.REVIEW_REQUIRED
            review_reasons.append("SUPPORTED_FINDING_REQUIRES_REVIEW_DUE_TO_EVIDENCE_STATE")

        payload = draft.model_dump(mode="json")
        findings.append(
            AiAuditFinding(
                finding_id=_finding_id(context.context_fingerprint, payload),
                state=final_state,
                evidence_sufficiency=sufficiency,
                risk_category=draft.risk_category,
                severity=draft.severity,
                title=draft.title,
                reasoning_summary=draft.reasoning_summary,
                suggestion=draft.suggestion,
                issue_ids=draft.issue_ids,
                canonical_object_ids=draft.canonical_object_ids,
                contract_evidence_ids=draft.contract_evidence_ids,
                legal_evidence_ids=draft.legal_evidence_ids,
                review_reasons=list(dict.fromkeys(review_reasons)),
            )
        )
    return findings


def _atomic_write_report(path: Path, report: AiAuditReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temp, path)


def run_primary_ai_audit(
    job_id: UUID,
    request: AiAuditRunRequest,
    *,
    provider_override: PrimaryAuditProvider | None = None,
    provider_gate: Callable[[], None] | None = None,
    before_provider_generate: Callable[[], None] | None = None,
) -> AiAuditReport:
    """Build the complete local Stage 8 context before crossing the provider boundary.

    provider_gate is called after deterministic local context/retrieval construction
    but before provider configuration/generation. before_provider_generate is then
    called immediately before provider.generate(), allowing the application control
    plane to atomically recheck cancellation and record an in-flight request.
    """

    try:
        context = build_audit_context(job_id, as_of=request.as_of, use_semantic=request.use_semantic)
    except AiAuditContextError as exc:
        raise AiAuditError(str(exc)) from exc

    if provider_gate is not None:
        provider_gate()

    try:
        provider = provider_override or provider_from_name(request.provider)
        health = provider.health()
        if not health.configured:
            raise AiAuditConfigurationError(health.detail)
        if before_provider_generate is not None:
            before_provider_generate()
        provider_result = provider.generate(context)
    except PrimaryAuditProviderError as exc:
        raise AiAuditError(str(exc)) from exc

    findings = validate_model_output(provider_result.content, context)
    supplied_legal = sorted(
        {
            candidate.legal_evidence_id
            for issue in context.issues
            for candidate in issue.retrieval.candidates
        }
    )
    supplied_contract = sorted(
        {
            evidence_id
            for item in context.contract_items
            for evidence_id in item.evidence_ids
        }
        | {
            evidence_id
            for rule in context.rule_items
            for evidence_id in rule.evidence_ids
        }
    )
    report = AiAuditReport(
        job_id=job_id,
        as_of=request.as_of,
        provider=provider_result.provider,
        model=provider_result.model,
        contract_source_fingerprint=context.contract_source_fingerprint,
        contract_content_fingerprint=context.contract_content_fingerprint,
        context_fingerprint=context.context_fingerprint,
        raw_response_hash=provider_result.raw_response_hash,
        provider_request_id=provider_result.request_id,
        provider_finish_reason=provider_result.finish_reason,
        provider_usage=provider_result.usage,
        findings=findings,
        warnings=context.warnings,
        supplied_legal_evidence_ids=supplied_legal,
        supplied_contract_evidence_ids=supplied_contract,
    )
    _atomic_write_report(job_ai_audit_path(job_id), report)
    return report


def load_ai_audit_report(job_id: UUID) -> AiAuditReport:
    path = job_ai_audit_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Stage 8 ai-audit.json does not exist for job {job_id}.")
    try:
        return AiAuditReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise AiAuditValidationError(f"Persisted AI audit report is invalid: {exc}") from exc