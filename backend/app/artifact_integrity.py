from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from .ai_audit_models import AiAuditReport
from .artifact_integrity_models import (
    ArtifactIntegrityCheck,
    ArtifactIntegrityState,
    ArtifactLinkCheck,
    JobArtifactIntegrityReport,
)
from .audit_rule_models import AuditRuleReport
from .contract_models import CanonicalContract
from .human_review_models import HumanReviewArtifact
from .review_report import ReviewReport
from .secondary_review_models import SecondaryReviewReport
from .storage import runtime_dir


_JSON_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("contract.json", CanonicalContract),
    ("audit-rules.json", AuditRuleReport),
    ("ai-audit.json", AiAuditReport),
    ("secondary-review.json", SecondaryReviewReport),
    ("review-report.json", ReviewReport),
    ("human-review.json", HumanReviewArtifact),
)


def _job_dir(job_id: UUID) -> Path:
    return runtime_dir() / "jobs" / str(job_id)


def _source_candidates(job_id: UUID) -> list[Path]:
    return sorted((runtime_dir() / "uploads" / str(job_id)).glob("source.*"))


def _load_model(path: Path, model_type: type[BaseModel], job_id: UUID) -> tuple[ArtifactIntegrityCheck, BaseModel | None]:
    if not path.exists():
        return (
            ArtifactIntegrityCheck(
                artifact=path.name,
                state=ArtifactIntegrityState.MISSING,
                detail=f"{path.name} is not present for this job.",
            ),
            None,
        )
    try:
        value = model_type.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError):
        return (
            ArtifactIntegrityCheck(
                artifact=path.name,
                state=ArtifactIntegrityState.CORRUPT,
                detail=f"{path.name} could not be parsed and schema-validated safely.",
                action="Preserve the file for diagnosis; rerun only the owning pipeline stage after confirming upstream artifacts are valid.",
            ),
            None,
        )
    embedded_job_id = getattr(value, "job_id", None)
    if embedded_job_id is not None and str(embedded_job_id) != str(job_id):
        return (
            ArtifactIntegrityCheck(
                artifact=path.name,
                state=ArtifactIntegrityState.MISMATCH,
                detail=f"{path.name} belongs to a different job ID.",
                action="Do not reuse or rename this artifact into the current job. Restore/regenerate the correct job artifact.",
            ),
            None,
        )
    return (
        ArtifactIntegrityCheck(
            artifact=path.name,
            state=ArtifactIntegrityState.READY,
            detail=f"{path.name} is parseable, schema-valid, and bound to the requested job.",
        ),
        value,
    )


def _link(
    link_id: str,
    ok: bool,
    detail_ok: str,
    detail_bad: str,
    artifacts: list[str],
    action: str,
) -> ArtifactLinkCheck:
    return ArtifactLinkCheck(
        link_id=link_id,
        state=ArtifactIntegrityState.READY if ok else ArtifactIntegrityState.MISMATCH,
        detail=detail_ok if ok else detail_bad,
        artifacts=artifacts,
        action=None if ok else action,
    )


def _review_report_fingerprint(report: ReviewReport) -> str:
    payload = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def inspect_job_artifact_integrity(job_id: UUID) -> JobArtifactIntegrityReport:
    job_dir = _job_dir(job_id)
    sources = _source_candidates(job_id)
    any_artifact = any((job_dir / name).exists() for name, _ in _JSON_MODELS)
    if not sources and not any_artifact:
        raise FileNotFoundError(f"No local Law-Rag job exists for {job_id}.")

    source_available = len(sources) == 1
    source_state = (
        ArtifactIntegrityState.READY
        if source_available
        else ArtifactIntegrityState.MISSING if not sources else ArtifactIntegrityState.MISMATCH
    )
    artifacts: list[ArtifactIntegrityCheck] = [
        ArtifactIntegrityCheck(
            artifact="source.*",
            state=source_state,
            detail=(
                "Exactly one original source file is present."
                if source_available
                else "Original source file is missing."
                if not sources
                else "Multiple source files exist for one job; source identity is ambiguous."
            ),
            action=(
                None
                if source_available
                else "Restore the original source file from a trusted copy before relying on source navigation or rerunning extraction."
                if not sources
                else "Preserve all candidates and manually resolve which source belongs to this job; do not auto-delete files."
            ),
        )
    ]
    values: dict[str, Any] = {}
    for filename, model_type in _JSON_MODELS:
        check, value = _load_model(job_dir / filename, model_type, job_id)
        artifacts.append(check)
        if value is not None:
            values[filename] = value

    links: list[ArtifactLinkCheck] = []
    contract = values.get("contract.json")
    rules = values.get("audit-rules.json")
    primary = values.get("ai-audit.json")
    secondary = values.get("secondary-review.json")
    report = values.get("review-report.json")
    human = values.get("human-review.json")

    if isinstance(contract, CanonicalContract) and isinstance(rules, AuditRuleReport):
        links.append(
            _link(
                "contract-to-rules-source",
                contract.source_fingerprint == rules.contract_source_fingerprint,
                "Contract source fingerprint matches the deterministic-rules report.",
                "Contract source fingerprint does not match the deterministic-rules report.",
                ["contract.json", "audit-rules.json"],
                "Regenerate deterministic rules from the current validated contract.json; preserve the mismatched report for diagnosis.",
            )
        )

    if isinstance(rules, AuditRuleReport) and isinstance(primary, AiAuditReport):
        links.append(
            _link(
                "rules-to-primary-content",
                rules.contract_content_fingerprint == primary.contract_content_fingerprint,
                "Primary audit is bound to the same canonical contract content as the rule report.",
                "Primary audit contract-content fingerprint differs from the rule report.",
                ["audit-rules.json", "ai-audit.json"],
                "Do not reuse the old primary audit. Rebuild the bounded audit context and rerun primary audit explicitly.",
            )
        )

    if isinstance(primary, AiAuditReport) and isinstance(secondary, SecondaryReviewReport):
        links.extend(
            [
                _link(
                    "primary-to-secondary-context",
                    primary.context_fingerprint == secondary.primary_context_fingerprint,
                    "Secondary review points to the exact primary context fingerprint.",
                    "Secondary review points to a different primary context fingerprint.",
                    ["ai-audit.json", "secondary-review.json"],
                    "Rerun secondary review against the current validated primary audit context.",
                ),
                _link(
                    "primary-to-secondary-as-of",
                    primary.as_of == secondary.as_of,
                    "Primary and secondary reviews use the same as_of date.",
                    "Primary and secondary reviews use different as_of dates.",
                    ["ai-audit.json", "secondary-review.json"],
                    "Rerun the review chain with one explicit as_of date.",
                ),
            ]
        )

    if isinstance(primary, AiAuditReport) and isinstance(secondary, SecondaryReviewReport) and isinstance(report, ReviewReport):
        report_ok = (
            report.primary_provider == primary.provider
            and report.primary_model == primary.model
            and report.secondary_provider == secondary.provider
            and report.secondary_model == secondary.model
            and report.as_of == primary.as_of.isoformat()
            and report.comparison.primary_context_fingerprint == primary.context_fingerprint
            and report.comparison.secondary_context_fingerprint == secondary.secondary_context_fingerprint
        )
        links.append(
            _link(
                "dual-model-to-review-report",
                report_ok,
                "review-report.json is linked to the current validated primary/secondary review identities and contexts.",
                "review-report.json does not match the current primary/secondary review identities or context fingerprints.",
                ["ai-audit.json", "secondary-review.json", "review-report.json"],
                "Regenerate review-report.json locally from the current validated primary and secondary artifacts.",
            )
        )

    if isinstance(report, ReviewReport) and isinstance(human, HumanReviewArtifact):
        current_fp = _review_report_fingerprint(report)
        stale_count = sum(item.review_report_fingerprint != current_fp for item in human.revisions)
        links.append(
            ArtifactLinkCheck(
                link_id="review-report-to-human-review",
                state=ArtifactIntegrityState.STALE if stale_count else ArtifactIntegrityState.READY,
                detail=(
                    f"{stale_count} human-review revision(s) reference an older review-report fingerprint."
                    if stale_count
                    else "All human-review revisions reference the current review-report fingerprint."
                ),
                artifacts=["review-report.json", "human-review.json"],
                action=(
                    "Keep stale revisions in history and record a new human decision against the current report where needed."
                    if stale_count
                    else None
                ),
            )
        )

    invalid_states = {ArtifactIntegrityState.CORRUPT, ArtifactIntegrityState.MISMATCH}
    all_present_valid = all(
        item.state not in invalid_states
        for item in artifacts
        if item.state != ArtifactIntegrityState.MISSING
    ) and all(item.state != ArtifactIntegrityState.MISMATCH for item in links)
    action_required = (not source_available) or any(
        item.state in invalid_states for item in artifacts
    ) or any(item.state in {ArtifactIntegrityState.MISMATCH, ArtifactIntegrityState.STALE} for item in links)

    return JobArtifactIntegrityReport(
        job_id=job_id,
        source_available=source_available,
        all_present_artifacts_valid=all_present_valid,
        action_required=action_required,
        artifacts=artifacts,
        links=links,
        warnings=[
            "Missing later-stage artifacts can be normal for an incomplete job and are not treated as corruption.",
            "Integrity inspection is read-only and never repairs, deletes, renames, or regenerates artifacts.",
        ],
    )
