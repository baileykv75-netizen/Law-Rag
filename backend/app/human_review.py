from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from .audit_planner import load_audit_plan
from .human_review_models import (
    HUMAN_REVIEW_SCHEMA_VERSION,
    HumanDecisionRequest,
    HumanDecisionRevision,
    HumanDecisionView,
    HumanReviewArtifact,
    HumanReviewTargetType,
    HumanReviewView,
)
from .issue_legal_context import load_issue_legal_context
from .issue_primary_audit import load_issue_primary_audit
from .issue_review_report import IssueReviewReportError, load_issue_review_report
from .issue_review_report_models import IssueReviewReport
from .issue_secondary_review import load_issue_secondary_review
from .job_architecture import JobArchitectureError, resolve_job_architecture
from .job_architecture_models import JobAuditArchitecture
from .review_report import ReviewReport, ReviewReportError, load_review_report
from .safe_persistence import atomic_write_text
from .storage import job_human_review_path


class HumanReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class _CurrentReviewContext:
    architecture: JobAuditArchitecture
    artifact_name: str
    fingerprint: str
    report: ReviewReport | IssueReviewReport


def _legacy_fingerprint(report: ReviewReport) -> str:
    """Preserve the exact Stage 10 fingerprint semantics used by existing RC2 decisions."""

    payload = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_artifact(job_id: UUID) -> HumanReviewArtifact:
    path = job_human_review_path(job_id)
    if not path.exists():
        return HumanReviewArtifact(job_id=job_id)
    try:
        artifact = HumanReviewArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise HumanReviewError(f"Persisted human-review.json is invalid: {exc}") from exc
    if artifact.job_id != job_id:
        raise HumanReviewError("human-review.json job_id does not match the requested job.")
    return artifact


def _atomic_write(path: Path, artifact: HumanReviewArtifact) -> None:
    artifact.schema_version = HUMAN_REVIEW_SCHEMA_VERSION
    atomic_write_text(path, artifact.model_dump_json(indent=2))


def _current_review_context(job_id: UUID) -> _CurrentReviewContext:
    try:
        architecture = resolve_job_architecture(job_id)
    except (FileNotFoundError, JobArchitectureError) as exc:
        raise HumanReviewError(f"Unable to resolve the authoritative audit architecture: {exc}") from exc

    if architecture.architecture == JobAuditArchitecture.CONFLICT:
        raise HumanReviewError(
            "Job audit architecture is conflicted; human review will not mix Legacy RC2 and Issue V1 reports."
        )

    if architecture.architecture == JobAuditArchitecture.LEGACY_RC2:
        try:
            report = load_review_report(job_id)
        except (FileNotFoundError, ReviewReportError) as exc:
            raise HumanReviewError(
                "A valid authoritative Legacy RC2 review-report.json is required before human review."
            ) from exc
        return _CurrentReviewContext(
            architecture=JobAuditArchitecture.LEGACY_RC2,
            artifact_name="review-report.json",
            fingerprint=_legacy_fingerprint(report),
            report=report,
        )

    try:
        report = load_issue_review_report(job_id)
    except (FileNotFoundError, IssueReviewReportError) as exc:
        raise HumanReviewError(
            "A valid authoritative Issue V1 issue-review-report.json is required before human review."
        ) from exc
    return _CurrentReviewContext(
        architecture=JobAuditArchitecture.ISSUE_V1,
        artifact_name="issue-review-report.json",
        fingerprint=report.artifact_fingerprint,
        report=report,
    )


def _legacy_target_evidence(
    report: ReviewReport,
    request: HumanDecisionRequest,
) -> tuple[list[str], list[str]]:
    if request.target_type == HumanReviewTargetType.FINDING:
        primary = next((item for item in report.primary_findings if item.finding_id == request.target_id), None)
        if primary is None:
            raise HumanReviewError(f"Primary finding {request.target_id} does not exist in the current review report.")
        secondary = next(
            (item for item in report.secondary_reviews if item.primary_finding_id == request.target_id),
            None,
        )
        contract_ids = set(primary.contract_evidence_ids)
        legal_ids = set(primary.legal_evidence_ids)
        if secondary is not None:
            contract_ids.update(secondary.contract_evidence_ids)
            legal_ids.update(secondary.legal_evidence_ids)
        return sorted(contract_ids), sorted(legal_ids)

    if request.target_type != HumanReviewTargetType.OMISSION:
        raise HumanReviewError(
            "Issue targets are not valid for an authoritative Legacy RC2 review report."
        )

    omission = next(
        (item for item in report.possible_primary_omissions if item.omission_id == request.target_id),
        None,
    )
    if omission is None:
        raise HumanReviewError(f"Possible omission {request.target_id} does not exist in the current review report.")
    return sorted(set(omission.contract_evidence_ids)), sorted(set(omission.legal_evidence_ids))


def _issue_target_evidence(
    job_id: UUID,
    report: IssueReviewReport,
    request: HumanDecisionRequest,
) -> tuple[list[str], list[str]]:
    if request.target_type != HumanReviewTargetType.ISSUE:
        raise HumanReviewError(
            "Finding/omission targets are historical Legacy RC2 identities and are not valid for an authoritative Issue V1 report."
        )

    comparison = next((item for item in report.comparisons if item.issue_id == request.target_id), None)
    if comparison is None:
        raise HumanReviewError(f"AuditPlan issue {request.target_id} does not exist in the current issue review report.")

    try:
        plan = load_audit_plan(job_id)
        legal = load_issue_legal_context(job_id)
        primary = load_issue_primary_audit(job_id)
        secondary = load_issue_secondary_review(job_id)
    except Exception as exc:
        raise HumanReviewError(
            "Fresh Stage 13B-13F artifacts are required to snapshot Issue evidence for human review."
        ) from exc

    plan_issue = next((item for item in plan.issues if item.issue_id == request.target_id), None)
    legal_issue = next((item for item in legal.issues if item.issue_id == request.target_id), None)
    primary_issue = next((item for item in primary.results if item.issue_id == request.target_id), None)
    secondary_issue = next((item for item in secondary.results if item.issue_id == request.target_id), None)
    if not all((plan_issue, legal_issue, primary_issue, secondary_issue)):
        raise HumanReviewError(
            f"AuditPlan issue {request.target_id} does not have a complete Stage 13B-13F evidence chain."
        )

    contract_ids = set(plan_issue.contract_evidence_ids)
    contract_ids.update(primary_issue.contract_evidence_ids)
    contract_ids.update(secondary_issue.contract_evidence_ids)
    contract_ids.update(comparison.contract_evidence.shared)
    contract_ids.update(comparison.contract_evidence.primary_only)
    contract_ids.update(comparison.contract_evidence.secondary_only)

    legal_ids = {item.legal_evidence_id for item in legal_issue.legal_evidence}
    legal_ids.update(primary_issue.legal_evidence_ids)
    legal_ids.update(secondary_issue.legal_evidence_ids)
    legal_ids.update(comparison.legal_evidence.shared)
    legal_ids.update(comparison.legal_evidence.primary_only)
    legal_ids.update(comparison.legal_evidence.secondary_only)
    return sorted(contract_ids), sorted(legal_ids)


def _target_evidence(
    job_id: UUID,
    context: _CurrentReviewContext,
    request: HumanDecisionRequest,
) -> tuple[list[str], list[str]]:
    if context.architecture == JobAuditArchitecture.LEGACY_RC2:
        if not isinstance(context.report, ReviewReport):
            raise HumanReviewError("Internal human-review architecture mismatch for Legacy RC2.")
        return _legacy_target_evidence(context.report, request)
    if not isinstance(context.report, IssueReviewReport):
        raise HumanReviewError("Internal human-review architecture mismatch for Issue V1.")
    return _issue_target_evidence(job_id, context.report, request)


def _revision_architecture(revision: HumanDecisionRevision) -> JobAuditArchitecture:
    return (
        JobAuditArchitecture.ISSUE_V1
        if revision.target_type == HumanReviewTargetType.ISSUE
        else JobAuditArchitecture.LEGACY_RC2
    )


def _view(
    job_id: UUID,
    context: _CurrentReviewContext,
    artifact: HumanReviewArtifact,
) -> HumanReviewView:
    revisions = [
        HumanDecisionView(
            **revision.model_dump(),
            is_stale=(
                _revision_architecture(revision) != context.architecture
                or revision.review_report_fingerprint != context.fingerprint
            ),
        )
        for revision in artifact.revisions
    ]
    latest: dict[str, HumanDecisionView] = {}
    for revision in revisions:
        key = f"{revision.target_type.value}:{revision.target_id}"
        previous = latest.get(key)
        if previous is None or revision.revision > previous.revision:
            latest[key] = revision
    return HumanReviewView(
        job_id=job_id,
        authoritative_architecture=context.architecture.value,
        current_review_report_artifact=context.artifact_name,
        current_review_report_fingerprint=context.fingerprint,
        revisions=revisions,
        latest_by_target=latest,
    )


def load_human_review(job_id: UUID) -> HumanReviewView:
    context = _current_review_context(job_id)
    return _view(job_id, context, _load_artifact(job_id))


def record_human_decision(job_id: UUID, request: HumanDecisionRequest) -> HumanReviewView:
    context = _current_review_context(job_id)
    contract_ids, legal_ids = _target_evidence(job_id, context, request)
    artifact = _load_artifact(job_id)
    existing = [
        revision
        for revision in artifact.revisions
        if revision.target_type == request.target_type and revision.target_id == request.target_id
    ]
    revision_number = max((item.revision for item in existing), default=0) + 1
    revision = HumanDecisionRevision(
        decision_id=f"human-{uuid4()}",
        revision=revision_number,
        job_id=job_id,
        target_type=request.target_type,
        target_id=request.target_id,
        state=request.state,
        reviewer_note=request.reviewer_note.strip(),
        decided_at=datetime.now(timezone.utc),
        contract_evidence_ids=contract_ids,
        legal_evidence_ids=legal_ids,
        review_report_fingerprint=context.fingerprint,
    )
    artifact.revisions.append(revision)
    _atomic_write(job_human_review_path(job_id), artifact)
    return _view(job_id, context, artifact)
