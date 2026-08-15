from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from .human_review_models import (
    HumanDecisionRequest,
    HumanDecisionRevision,
    HumanDecisionView,
    HumanReviewArtifact,
    HumanReviewTargetType,
    HumanReviewView,
)
from .review_report import ReviewReport, ReviewReportError, load_review_report
from .storage import job_human_review_path


class HumanReviewError(RuntimeError):
    pass


def _fingerprint(report: ReviewReport) -> str:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temp, path)


def _target_evidence(
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

    omission = next(
        (item for item in report.possible_primary_omissions if item.omission_id == request.target_id),
        None,
    )
    if omission is None:
        raise HumanReviewError(f"Possible omission {request.target_id} does not exist in the current review report.")
    return sorted(set(omission.contract_evidence_ids)), sorted(set(omission.legal_evidence_ids))


def _view(job_id: UUID, report: ReviewReport, artifact: HumanReviewArtifact) -> HumanReviewView:
    current_fingerprint = _fingerprint(report)
    revisions = [
        HumanDecisionView(
            **revision.model_dump(),
            is_stale=revision.review_report_fingerprint != current_fingerprint,
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
        current_review_report_fingerprint=current_fingerprint,
        revisions=revisions,
        latest_by_target=latest,
    )


def load_human_review(job_id: UUID) -> HumanReviewView:
    try:
        report = load_review_report(job_id)
    except (FileNotFoundError, ReviewReportError) as exc:
        raise HumanReviewError("A valid Stage 9 review-report.json is required before human review.") from exc
    return _view(job_id, report, _load_artifact(job_id))


def record_human_decision(job_id: UUID, request: HumanDecisionRequest) -> HumanReviewView:
    try:
        report = load_review_report(job_id)
    except (FileNotFoundError, ReviewReportError) as exc:
        raise HumanReviewError("A valid Stage 9 review-report.json is required before human review.") from exc

    contract_ids, legal_ids = _target_evidence(report, request)
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
        review_report_fingerprint=_fingerprint(report),
    )
    artifact.revisions.append(revision)
    _atomic_write(job_human_review_path(job_id), artifact)
    return _view(job_id, report, artifact)
