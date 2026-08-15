from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .ai_audit import AiAuditValidationError, load_ai_audit_report
from .ai_audit_context import AiAuditContextError, build_audit_context
from .legal.models import VersionResolutionState
from .legal.store import get_evidence, resolve_version
from .secondary_review_models import (
    ModelSecondaryEnvelope,
    SecondaryAssessment,
    SecondaryFindingReview,
    SecondaryPossibleOmission,
    SecondaryReviewContext,
    SecondaryReviewReport,
    SecondaryReviewRunRequest,
)
from .secondary_review_providers import (
    SecondaryReviewProvider,
    SecondaryReviewProviderError,
    secondary_provider_from_name,
)
from .storage import job_secondary_review_path, legal_db_path


class SecondaryReviewError(RuntimeError):
    pass


class SecondaryReviewConfigurationError(SecondaryReviewError):
    pass


class SecondaryReviewContextError(SecondaryReviewError):
    pass


class SecondaryReviewValidationError(SecondaryReviewError):
    pass


def _fingerprint_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_secondary_review_context(
    job_id: UUID,
    *,
    use_semantic: bool = False,
) -> SecondaryReviewContext:
    try:
        primary = load_ai_audit_report(job_id)
    except (FileNotFoundError, AiAuditValidationError) as exc:
        raise SecondaryReviewContextError(
            "A valid Stage 8 ai-audit.json is required before secondary review."
        ) from exc

    try:
        audit_context = build_audit_context(
            job_id,
            as_of=primary.as_of,
            use_semantic=use_semantic,
        )
    except AiAuditContextError as exc:
        raise SecondaryReviewContextError(str(exc)) from exc

    if audit_context.context_fingerprint != primary.context_fingerprint:
        raise SecondaryReviewContextError(
            "The current audit context does not reproduce the Stage 8 context fingerprint. "
            "Use the same retrieval mode and unchanged legal/contract artifacts, or rerun Stage 8 before secondary review."
        )
    if audit_context.contract_source_fingerprint != primary.contract_source_fingerprint:
        raise SecondaryReviewContextError("Contract source fingerprint changed after Stage 8; rerun the primary audit.")
    if audit_context.contract_content_fingerprint != primary.contract_content_fingerprint:
        raise SecondaryReviewContextError("Contract content fingerprint changed after Stage 8; rerun the primary audit.")

    payload = {
        "primary_report": primary.model_dump(mode="json"),
        "audit_context": audit_context.model_dump(mode="json"),
    }
    return SecondaryReviewContext(
        job_id=job_id,
        as_of=primary.as_of,
        primary_report=primary,
        audit_context=audit_context,
        context_fingerprint=_fingerprint_payload(payload),
    )


def _allowed_ids(context: SecondaryReviewContext) -> tuple[set[str], set[str], set[str], set[str]]:
    primary_ids = {finding.finding_id for finding in context.primary_report.findings}
    object_ids = {item.canonical_object_id for item in context.audit_context.contract_items}
    contract_evidence = {
        evidence_id
        for item in context.audit_context.contract_items
        for evidence_id in item.evidence_ids
    }
    for rule in context.audit_context.rule_items:
        object_ids.update(rule.canonical_object_ids)
        contract_evidence.update(rule.evidence_ids)
    legal_evidence = {
        candidate.legal_evidence_id
        for issue in context.audit_context.issues
        for candidate in issue.retrieval.candidates
    }
    return primary_ids, object_ids, contract_evidence, legal_evidence


def _validate_legal_applicability(legal_ids: list[str], context: SecondaryReviewContext) -> None:
    db = legal_db_path()
    for legal_id in legal_ids:
        evidence = get_evidence(db, legal_id)
        resolution = resolve_version(db, evidence.authority.authority_id, context.as_of)
        if resolution.state != VersionResolutionState.RESOLVED or resolution.version is None:
            raise SecondaryReviewValidationError(
                f"Legal Evidence ID {legal_id} is not deterministically applicable on {context.as_of}."
            )
        if resolution.version.version_id != evidence.version.version_id:
            raise SecondaryReviewValidationError(
                f"Legal Evidence ID {legal_id} uses version {evidence.version.version_id}, "
                f"but {resolution.version.version_id} applies on {context.as_of}."
            )


def _stable_id(prefix: str, context_fingerprint: str, payload: dict) -> str:
    value = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{context_fingerprint}:{value}".encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def validate_secondary_output(
    content: str,
    context: SecondaryReviewContext,
) -> tuple[list[SecondaryFindingReview], list[SecondaryPossibleOmission]]:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SecondaryReviewValidationError(f"Secondary model did not return valid JSON: {exc}") from exc
    try:
        envelope = ModelSecondaryEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise SecondaryReviewValidationError(
            f"Secondary model JSON does not match the Stage 9 schema: {exc}"
        ) from exc

    allowed_primary, allowed_objects, allowed_contract, allowed_legal = _allowed_ids(context)
    seen_primary: set[str] = set()
    reviews: list[SecondaryFindingReview] = []

    for draft in envelope.finding_reviews:
        if draft.primary_finding_id in seen_primary:
            raise SecondaryReviewValidationError(
                f"Duplicate review for primary finding {draft.primary_finding_id}."
            )
        seen_primary.add(draft.primary_finding_id)
        if draft.primary_finding_id not in allowed_primary:
            raise SecondaryReviewValidationError(
                f"Secondary model invented or cited an unsupplied primary finding ID: {draft.primary_finding_id}"
            )

        unknown_contract = set(draft.contract_evidence_ids) - allowed_contract
        unknown_legal = set(draft.legal_evidence_ids) - allowed_legal
        if unknown_contract:
            raise SecondaryReviewValidationError(
                f"Secondary model invented or cited unsupplied contract Evidence IDs: {sorted(unknown_contract)}"
            )
        if unknown_legal:
            raise SecondaryReviewValidationError(
                f"Secondary model invented or cited unsupplied Legal Evidence IDs: {sorted(unknown_legal)}"
            )
        if draft.assessment in {SecondaryAssessment.SUPPORTED, SecondaryAssessment.NOT_SUPPORTED}:
            if not draft.contract_evidence_ids:
                raise SecondaryReviewValidationError(
                    f"{draft.assessment.value} review must cite supplied contract evidence."
                )
            if not draft.legal_evidence_ids:
                raise SecondaryReviewValidationError(
                    f"{draft.assessment.value} review must cite supplied Legal Evidence."
                )

        _validate_legal_applicability(draft.legal_evidence_ids, context)
        payload = draft.model_dump(mode="json")
        reviews.append(
            SecondaryFindingReview(
                review_id=_stable_id("secondary-review", context.context_fingerprint, payload),
                primary_finding_id=draft.primary_finding_id,
                assessment=draft.assessment,
                severity=draft.severity,
                reasoning_summary=draft.reasoning_summary,
                suggestion=draft.suggestion,
                contract_evidence_ids=list(dict.fromkeys(draft.contract_evidence_ids)),
                legal_evidence_ids=list(dict.fromkeys(draft.legal_evidence_ids)),
                disagreement_categories=list(dict.fromkeys(draft.disagreement_categories)),
                review_reasons=list(dict.fromkeys(draft.review_reasons)),
            )
        )

    missing = allowed_primary - seen_primary
    if missing:
        raise SecondaryReviewValidationError(
            f"Secondary model failed to review supplied primary findings: {sorted(missing)}"
        )
    extra = seen_primary - allowed_primary
    if extra:
        raise SecondaryReviewValidationError(
            f"Secondary model returned unknown primary findings: {sorted(extra)}"
        )

    seen_omissions: set[str] = set()
    omissions: list[SecondaryPossibleOmission] = []
    for draft in envelope.possible_omissions:
        if draft.client_omission_id in seen_omissions:
            raise SecondaryReviewValidationError(
                f"Duplicate client_omission_id: {draft.client_omission_id}"
            )
        seen_omissions.add(draft.client_omission_id)

        unknown_objects = set(draft.canonical_object_ids) - allowed_objects
        unknown_contract = set(draft.contract_evidence_ids) - allowed_contract
        unknown_legal = set(draft.legal_evidence_ids) - allowed_legal
        if unknown_objects:
            raise SecondaryReviewValidationError(
                f"Secondary omission cited unsupplied canonical object IDs: {sorted(unknown_objects)}"
            )
        if unknown_contract:
            raise SecondaryReviewValidationError(
                f"Secondary omission cited unsupplied contract Evidence IDs: {sorted(unknown_contract)}"
            )
        if unknown_legal:
            raise SecondaryReviewValidationError(
                f"Secondary omission cited unsupplied Legal Evidence IDs: {sorted(unknown_legal)}"
            )
        if not draft.canonical_object_ids or not draft.contract_evidence_ids or not draft.legal_evidence_ids:
            raise SecondaryReviewValidationError(
                "A possible primary omission must be grounded in supplied canonical objects, contract evidence and Legal Evidence."
            )

        _validate_legal_applicability(draft.legal_evidence_ids, context)
        payload = draft.model_dump(mode="json")
        omissions.append(
            SecondaryPossibleOmission(
                omission_id=_stable_id("secondary-omission", context.context_fingerprint, payload),
                risk_category=draft.risk_category,
                severity=draft.severity,
                title=draft.title,
                reasoning_summary=draft.reasoning_summary,
                suggestion=draft.suggestion,
                canonical_object_ids=list(dict.fromkeys(draft.canonical_object_ids)),
                contract_evidence_ids=list(dict.fromkeys(draft.contract_evidence_ids)),
                legal_evidence_ids=list(dict.fromkeys(draft.legal_evidence_ids)),
                review_reasons=list(dict.fromkeys(draft.review_reasons)),
            )
        )

    return reviews, omissions


def _atomic_write_report(path: Path, report: SecondaryReviewReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temp, path)


def run_secondary_review(
    job_id: UUID,
    request: SecondaryReviewRunRequest,
    *,
    provider_override: SecondaryReviewProvider | None = None,
) -> SecondaryReviewReport:
    context = build_secondary_review_context(job_id, use_semantic=request.use_semantic)

    try:
        provider = provider_override or secondary_provider_from_name(request.provider)
        health = provider.health()
        if not health.configured:
            raise SecondaryReviewConfigurationError(health.detail)
        # Universal Stage 9 policy: exactly one contract-level secondary generate call.
        provider_result = provider.generate(context)
    except SecondaryReviewProviderError as exc:
        raise SecondaryReviewError(str(exc)) from exc

    reviews, omissions = validate_secondary_output(provider_result.content, context)
    supplied_contract = sorted(
        {
            evidence_id
            for item in context.audit_context.contract_items
            for evidence_id in item.evidence_ids
        }
        | {
            evidence_id
            for rule in context.audit_context.rule_items
            for evidence_id in rule.evidence_ids
        }
    )
    supplied_legal = sorted(
        {
            candidate.legal_evidence_id
            for issue in context.audit_context.issues
            for candidate in issue.retrieval.candidates
        }
    )
    report = SecondaryReviewReport(
        job_id=job_id,
        as_of=context.as_of,
        primary_provider=context.primary_report.provider,
        primary_model=context.primary_report.model,
        primary_context_fingerprint=context.primary_report.context_fingerprint,
        secondary_context_fingerprint=context.context_fingerprint,
        provider=provider_result.provider,
        model=provider_result.model,
        raw_response_hash=provider_result.raw_response_hash,
        provider_request_id=provider_result.request_id,
        provider_finish_reason=provider_result.finish_reason,
        provider_usage=provider_result.usage,
        finding_reviews=reviews,
        possible_omissions=omissions,
        warnings=sorted(set([*context.primary_report.warnings, *context.audit_context.warnings])),
        supplied_contract_evidence_ids=supplied_contract,
        supplied_legal_evidence_ids=supplied_legal,
    )
    _atomic_write_report(job_secondary_review_path(job_id), report)
    return report


def load_secondary_review_report(job_id: UUID) -> SecondaryReviewReport:
    path = job_secondary_review_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Stage 9 secondary-review.json does not exist for job {job_id}.")
    try:
        return SecondaryReviewReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SecondaryReviewValidationError(
            f"Persisted secondary review report is invalid: {exc}"
        ) from exc
