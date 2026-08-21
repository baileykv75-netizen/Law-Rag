from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ValidationError

from .audit_plan_models import AuditPlan
from .issue_legal_context_models import IssueLegalContextArtifact
from .issue_primary_audit_models import IssuePrimaryAuditArtifact, IssuePrimaryAuditStatus
from .issue_review_report_models import IssueReviewReport
from .issue_secondary_review_models import IssueSecondaryReviewArtifact, IssueSecondaryReviewStatus
from .pipeline_models import PipelineReport, PipelineStage, PipelineStatus
from .safe_persistence import atomic_write_text
from .storage import (
    job_audit_plan_path,
    job_issue_legal_context_path,
    job_issue_primary_audit_path,
    job_issue_review_report_path,
    job_issue_secondary_review_path,
    job_pipeline_path,
)
from .uat_capture_models import (
    IssueV1UATObservation,
    IssueV1UATSanitizedReport,
    UATArtifactProvenance,
    UATCaptureMode,
    UATChainState,
    UATIssueCoverage,
    UATProviderCallProvenance,
    UATProviderStage,
    UATProviderSummary,
)


class UATCaptureError(RuntimeError):
    pass


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FAKE_RE = re.compile(r"(?:^|[-_\s])(fake|test|stub|mock|double|dummy)(?:$|[-_\s])", re.IGNORECASE)
_ISSUE_STAGES = {
    PipelineStage.AUDIT_PLAN,
    PipelineStage.ISSUE_LEGAL_CONTEXT,
    PipelineStage.ISSUE_PRIMARY_AUDIT,
    PipelineStage.ISSUE_SECONDARY_REVIEW,
    PipelineStage.ISSUE_REVIEW_REPORT,
}
_LEGACY_STAGES = {
    PipelineStage.PRIMARY_AUDIT,
    PipelineStage.SECONDARY_REVIEW,
    PipelineStage.REVIEW_REPORT,
}


def _stable_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise UATCaptureError(f"Could not hash UAT source artifact {path}: {exc}") from exc
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_private_output(path: Path, repo_root: Path) -> None:
    path = path.resolve()
    repo_root = repo_root.resolve()
    private_root = (repo_root / "benchmark_private").resolve()
    if _is_within(path, repo_root) and not _is_within(path, private_root):
        raise UATCaptureError(
            "UAT observation output must stay external or under ignored benchmark_private/; tracked repository paths are forbidden."
        )
    if path.exists():
        raise UATCaptureError(
            "UAT observation output already exists; capture files are append-only evidence and are never overwritten."
        )


def _load(path: Path, model_type: type[BaseModel], label: str):
    if not path.exists():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    try:
        return model_type.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as exc:
        raise UATCaptureError(f"{label} is malformed or schema-invalid.") from exc


def _validate_embedded_fingerprint(value: BaseModel, *, label: str) -> str:
    embedded = getattr(value, "artifact_fingerprint", None)
    if not isinstance(embedded, str) or not _SHA256_RE.fullmatch(embedded):
        raise UATCaptureError(f"{label} does not contain a valid embedded artifact fingerprint.")
    payload = value.model_dump(mode="json", exclude={"artifact_fingerprint"})
    expected = _stable_fingerprint(payload)
    if embedded != expected:
        raise UATCaptureError(f"{label} embedded artifact fingerprint is stale or invalid.")
    return embedded


def _artifact(path: Path, *, embedded: str | None = None) -> UATArtifactProvenance:
    return UATArtifactProvenance(
        artifact=path.name,
        file_sha256=_file_sha256(path),
        embedded_fingerprint=embedded,
    )


def _require_hash(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise UATCaptureError(f"{label} is not a valid SHA-256 response/artifact hash.")
    return normalized


def _validate_pipeline(pipeline: PipelineReport, job_id: UUID) -> None:
    if pipeline.job_id != job_id:
        raise UATCaptureError("pipeline.json belongs to a different job ID.")
    stages = {item.stage for item in pipeline.stages}
    if stages & _LEGACY_STAGES:
        raise UATCaptureError("REAL_PROVIDER_UAT capture refuses a pipeline containing legacy RC2 audit stages.")
    required = {
        PipelineStage.AUDIT_PLAN,
        PipelineStage.ISSUE_LEGAL_CONTEXT,
        PipelineStage.ISSUE_PRIMARY_AUDIT,
    }
    if not required.issubset(stages):
        raise UATCaptureError("pipeline.json does not establish the current ISSUE_V1 provider path.")


def _provider_identity_allowed(provider: str, model: str, *, expected_provider: str) -> None:
    if provider.strip().lower() != expected_provider:
        raise UATCaptureError(
            f"REAL_PROVIDER UAT expected {expected_provider} for the current production stage, got {provider!r}."
        )
    if _FAKE_RE.search(provider) or _FAKE_RE.search(model):
        raise UATCaptureError("Fake/test provider or model identities cannot be labeled REAL_PROVIDER UAT evidence.")


def _planner_calls(plan: AuditPlan) -> list[UATProviderCallProvenance]:
    calls: list[UATProviderCallProvenance] = []
    if plan.planner_passes:
        for item in plan.planner_passes:
            calls.append(
                UATProviderCallProvenance(
                    stage=UATProviderStage.PLANNER,
                    provider=plan.provider,
                    model=plan.model,
                    request_id=item.provider_request_id,
                    raw_response_hash=_require_hash(
                        item.response_hash,
                        label=f"Audit Planner pass {item.pass_id} response_hash",
                    ),
                    usage=item.provider_usage,
                )
            )
        return calls
    calls.append(
        UATProviderCallProvenance(
            stage=UATProviderStage.PLANNER,
            provider=plan.provider,
            model=plan.model,
            request_id=plan.provider_request_id,
            finish_reason=plan.provider_finish_reason,
            raw_response_hash=_require_hash(
                plan.planner_response_hash,
                label="Audit Planner response hash",
            ),
            usage=plan.provider_usage,
        )
    )
    return calls


def _primary_calls(primary: IssuePrimaryAuditArtifact) -> list[UATProviderCallProvenance]:
    calls: list[UATProviderCallProvenance] = []
    seen: set[str] = set()
    result_ids = {item.issue_id for item in primary.results}
    for item in primary.provider_calls:
        if item.issue_id in seen:
            raise UATCaptureError("issue-primary-audit.json contains duplicate provider-call issue IDs.")
        seen.add(item.issue_id)
        if item.issue_id not in result_ids:
            raise UATCaptureError("Primary provider call exists without a persisted terminal Issue result.")
        if item.provider != primary.provider or item.model != primary.model:
            raise UATCaptureError("Primary provider-call identity differs from its artifact provider/model.")
        calls.append(
            UATProviderCallProvenance(
                stage=UATProviderStage.PRIMARY,
                issue_id=item.issue_id,
                provider=item.provider,
                model=item.model,
                request_id=item.request_id,
                finish_reason=item.finish_reason,
                raw_response_hash=_require_hash(
                    item.raw_response_hash,
                    label=f"Primary Issue {item.issue_id} raw_response_hash",
                ),
                usage=item.usage,
            )
        )
    return calls


def _secondary_calls(secondary: IssueSecondaryReviewArtifact) -> list[UATProviderCallProvenance]:
    calls: list[UATProviderCallProvenance] = []
    seen: set[str] = set()
    result_ids = {item.issue_id for item in secondary.results}
    for item in secondary.provider_calls:
        if item.issue_id in seen:
            raise UATCaptureError("issue-secondary-review.json contains duplicate provider-call issue IDs.")
        seen.add(item.issue_id)
        if item.issue_id not in result_ids:
            raise UATCaptureError("Secondary provider call exists without a persisted terminal Issue result.")
        if item.provider != secondary.provider or item.model != secondary.model:
            raise UATCaptureError("Secondary provider-call identity differs from its artifact provider/model.")
        calls.append(
            UATProviderCallProvenance(
                stage=UATProviderStage.SECONDARY,
                issue_id=item.issue_id,
                provider=item.provider,
                model=item.model,
                request_id=item.request_id,
                finish_reason=item.finish_reason,
                raw_response_hash=_require_hash(
                    item.raw_response_hash,
                    label=f"Secondary Issue {item.issue_id} raw_response_hash",
                ),
                usage=item.usage,
            )
        )
    return calls


def _validate_issue_counts(
    plan: AuditPlan,
    primary: IssuePrimaryAuditArtifact,
    secondary: IssueSecondaryReviewArtifact | None,
    report: IssueReviewReport | None,
) -> list[str]:
    issue_ids = [item.issue_id for item in plan.issues]
    if len(issue_ids) != len(set(issue_ids)):
        raise UATCaptureError("AuditPlan contains duplicate Issue IDs.")
    expected = set(issue_ids)

    primary_ids = [item.issue_id for item in primary.results]
    if len(primary_ids) != len(set(primary_ids)):
        raise UATCaptureError("Primary artifact contains duplicate Issue results.")
    if primary.total_issue_count != len(issue_ids) or primary.completed_issue_count != len(primary_ids):
        raise UATCaptureError("Primary artifact Issue counts do not reconcile with the AuditPlan/results.")
    if not set(primary_ids).issubset(expected):
        raise UATCaptureError("Primary artifact contains Issue IDs not present in the AuditPlan.")
    if primary.status == IssuePrimaryAuditStatus.COMPLETE and set(primary_ids) != expected:
        raise UATCaptureError("A COMPLETE primary artifact must cover every AuditPlan Issue.")

    if secondary is not None:
        secondary_ids = [item.issue_id for item in secondary.results]
        if len(secondary_ids) != len(set(secondary_ids)):
            raise UATCaptureError("Secondary artifact contains duplicate Issue results.")
        if secondary.total_issue_count != len(issue_ids) or secondary.completed_issue_count != len(secondary_ids):
            raise UATCaptureError("Secondary artifact Issue counts do not reconcile with the AuditPlan/results.")
        if not set(secondary_ids).issubset(expected):
            raise UATCaptureError("Secondary artifact contains Issue IDs not present in the AuditPlan.")
        if secondary.status == IssueSecondaryReviewStatus.COMPLETE and set(secondary_ids) != expected:
            raise UATCaptureError("A COMPLETE secondary artifact must cover every AuditPlan Issue.")

    if report is not None:
        comparison_ids = [item.issue_id for item in report.comparisons]
        if len(comparison_ids) != len(set(comparison_ids)) or set(comparison_ids) != expected:
            raise UATCaptureError("Final Issue comparison does not cover exactly the AuditPlan Issue set.")
    return issue_ids


def _chain_state(
    pipeline: PipelineReport,
    primary: IssuePrimaryAuditArtifact,
    secondary: IssueSecondaryReviewArtifact | None,
    report: IssueReviewReport | None,
) -> UATChainState:
    if primary.status == IssuePrimaryAuditStatus.INTERRUPTED:
        if secondary is not None or report is not None:
            raise UATCaptureError("Interrupted primary UAT cannot coexist with downstream secondary/report artifacts.")
        if pipeline.status == PipelineStatus.COMPLETE:
            raise UATCaptureError("Pipeline cannot be COMPLETE while the primary Issue audit is INTERRUPTED.")
        return UATChainState.PRIMARY_INTERRUPTED

    if primary.status != IssuePrimaryAuditStatus.COMPLETE:
        raise UATCaptureError("UAT capture accepts only COMPLETE or INTERRUPTED primary checkpoints.")
    if secondary is None:
        raise UATCaptureError(
            "Primary is COMPLETE but no secondary checkpoint exists; capture cannot distinguish not-started from lost/stale Stage 13F evidence."
        )
    if secondary.status == IssueSecondaryReviewStatus.INTERRUPTED:
        if report is not None:
            raise UATCaptureError("Interrupted secondary UAT cannot coexist with a final Issue review report.")
        if pipeline.status == PipelineStatus.COMPLETE:
            raise UATCaptureError("Pipeline cannot be COMPLETE while secondary review is INTERRUPTED.")
        return UATChainState.SECONDARY_INTERRUPTED
    if secondary.status != IssueSecondaryReviewStatus.COMPLETE:
        raise UATCaptureError("UAT capture accepts only COMPLETE or INTERRUPTED secondary checkpoints.")
    if report is None:
        raise UATCaptureError("A complete primary+secondary chain requires issue-review-report.json for UAT capture.")
    if pipeline.status != PipelineStatus.COMPLETE:
        raise UATCaptureError("A COMPLETE Issue V1 UAT chain requires pipeline.json status COMPLETE.")
    return UATChainState.COMPLETE


def _sum_usage(calls: list[UATProviderCallProvenance], field: str) -> int | None:
    values = [getattr(item.usage, field) for item in calls if getattr(item.usage, field) is not None]
    return sum(values) if values else None


def _provider_summaries(calls: list[UATProviderCallProvenance]) -> list[UATProviderSummary]:
    summaries: list[UATProviderSummary] = []
    for stage in UATProviderStage:
        stage_calls = [item for item in calls if item.stage == stage]
        if not stage_calls:
            continue
        identities = {(item.provider, item.model) for item in stage_calls}
        if len(identities) != 1:
            raise UATCaptureError(f"UAT {stage.value} calls contain mixed provider/model identities.")
        provider, model = next(iter(identities))
        summaries.append(
            UATProviderSummary(
                stage=stage,
                provider=provider,
                model=model,
                provider_call_count=len(stage_calls),
                total_prompt_tokens=_sum_usage(stage_calls, "prompt_tokens"),
                total_completion_tokens=_sum_usage(stage_calls, "completion_tokens"),
                total_tokens=_sum_usage(stage_calls, "total_tokens"),
            )
        )
    return summaries


def _load_optional(path: Path, model_type: type[BaseModel], label: str):
    if not path.exists():
        return None
    return _load(path, model_type, label)


def capture_issue_v1_uat(
    repo_root: Path,
    job_id: UUID,
    output_path: Path,
    *,
    capture_mode: UATCaptureMode,
    confirm_real_provider_uat: bool = False,
) -> tuple[IssueV1UATObservation, IssueV1UATSanitizedReport]:
    repo_root = repo_root.resolve()
    output_path = output_path.resolve()
    _require_private_output(output_path, repo_root)
    if capture_mode == UATCaptureMode.REAL_PROVIDER and not confirm_real_provider_uat:
        raise UATCaptureError(
            "REAL_PROVIDER capture requires explicit confirm_real_provider_uat=True; test-double evidence must not be relabeled as real UAT."
        )

    pipeline_path = Path(job_pipeline_path(job_id))
    plan_path = Path(job_audit_plan_path(job_id))
    legal_path = Path(job_issue_legal_context_path(job_id))
    primary_path = Path(job_issue_primary_audit_path(job_id))
    secondary_path = Path(job_issue_secondary_review_path(job_id))
    report_path = Path(job_issue_review_report_path(job_id))

    pipeline: PipelineReport = _load(pipeline_path, PipelineReport, "pipeline.json")
    plan: AuditPlan = _load(plan_path, AuditPlan, "audit-plan.json")
    legal: IssueLegalContextArtifact = _load(legal_path, IssueLegalContextArtifact, "issue-legal-context.json")
    primary: IssuePrimaryAuditArtifact = _load(primary_path, IssuePrimaryAuditArtifact, "issue-primary-audit.json")
    secondary: IssueSecondaryReviewArtifact | None = _load_optional(
        secondary_path, IssueSecondaryReviewArtifact, "issue-secondary-review.json"
    )
    report: IssueReviewReport | None = _load_optional(
        report_path, IssueReviewReport, "issue-review-report.json"
    )

    _validate_pipeline(pipeline, job_id)
    for label, value in (
        ("audit-plan.json", plan),
        ("issue-legal-context.json", legal),
        ("issue-primary-audit.json", primary),
    ):
        if getattr(value, "job_id", None) != job_id:
            raise UATCaptureError(f"{label} belongs to a different job ID.")
    if secondary is not None and secondary.job_id != job_id:
        raise UATCaptureError("issue-secondary-review.json belongs to a different job ID.")
    if report is not None and report.job_id != job_id:
        raise UATCaptureError("issue-review-report.json belongs to a different job ID.")

    plan_fingerprint = _stable_fingerprint(plan.model_dump(mode="json"))
    legal_fingerprint = _validate_embedded_fingerprint(legal, label="issue-legal-context.json")
    primary_fingerprint = _validate_embedded_fingerprint(primary, label="issue-primary-audit.json")
    secondary_fingerprint = (
        _validate_embedded_fingerprint(secondary, label="issue-secondary-review.json")
        if secondary is not None
        else None
    )
    report_fingerprint = (
        _validate_embedded_fingerprint(report, label="issue-review-report.json")
        if report is not None
        else None
    )

    if legal.audit_plan_fingerprint != plan_fingerprint:
        raise UATCaptureError("Issue Legal Context does not belong to the current AuditPlan fingerprint.")
    if primary.audit_plan_fingerprint != plan_fingerprint:
        raise UATCaptureError("Primary Issue audit does not belong to the current AuditPlan fingerprint.")
    if primary.issue_legal_context_fingerprint != legal_fingerprint:
        raise UATCaptureError("Primary Issue audit does not belong to the current Issue Legal Context fingerprint.")
    if secondary is not None:
        if secondary.audit_plan_fingerprint != plan_fingerprint:
            raise UATCaptureError("Secondary review does not belong to the current AuditPlan fingerprint.")
        if secondary.issue_legal_context_fingerprint != legal_fingerprint:
            raise UATCaptureError("Secondary review does not belong to the current Issue Legal Context fingerprint.")
        if secondary.issue_primary_audit_fingerprint != primary_fingerprint:
            raise UATCaptureError("Secondary review does not belong to the current Primary Issue audit fingerprint.")
    if report is not None:
        if report.audit_plan_fingerprint != plan_fingerprint:
            raise UATCaptureError("Final Issue report does not belong to the current AuditPlan fingerprint.")
        if report.issue_primary_audit_fingerprint != primary_fingerprint:
            raise UATCaptureError("Final Issue report does not belong to the current Primary Issue audit fingerprint.")
        if secondary_fingerprint is None or report.issue_secondary_review_fingerprint != secondary_fingerprint:
            raise UATCaptureError("Final Issue report does not belong to the current Secondary review fingerprint.")
        if report.primary_provider != primary.provider or report.primary_model != primary.model:
            raise UATCaptureError("Final Issue report primary provider/model differs from the primary artifact.")
        if secondary is None or report.secondary_provider != secondary.provider or report.secondary_model != secondary.model:
            raise UATCaptureError("Final Issue report secondary provider/model differs from the secondary artifact.")

    issue_ids = _validate_issue_counts(plan, primary, secondary, report)
    chain_state = _chain_state(pipeline, primary, secondary, report)

    calls = [*_planner_calls(plan), *_primary_calls(primary)]
    if secondary is not None:
        calls.extend(_secondary_calls(secondary))

    if capture_mode == UATCaptureMode.REAL_PROVIDER:
        _provider_identity_allowed(plan.provider, plan.model, expected_provider="deepseek")
        _provider_identity_allowed(primary.provider, primary.model, expected_provider="deepseek")
        for item in calls:
            expected = "kimi" if item.stage == UATProviderStage.SECONDARY else "deepseek"
            _provider_identity_allowed(item.provider, item.model, expected_provider=expected)
        if secondary is not None:
            _provider_identity_allowed(secondary.provider, secondary.model, expected_provider="kimi")

    primary_result_ids = {item.issue_id for item in primary.results}
    primary_call_ids = {item.issue_id for item in primary.provider_calls}
    secondary_result_ids = {item.issue_id for item in secondary.results} if secondary else set()
    secondary_call_ids = {item.issue_id for item in secondary.provider_calls} if secondary else set()
    comparison_ids = {item.issue_id for item in report.comparisons} if report else set()
    issue_coverage = [
        UATIssueCoverage(
            issue_id=issue_id,
            primary_result_present=issue_id in primary_result_ids,
            primary_provider_call_present=issue_id in primary_call_ids,
            secondary_result_present=issue_id in secondary_result_ids,
            secondary_provider_call_present=issue_id in secondary_call_ids,
            comparison_present=issue_id in comparison_ids,
        )
        for issue_id in issue_ids
    ]

    artifacts = [
        _artifact(pipeline_path),
        _artifact(plan_path, embedded=plan_fingerprint),
        _artifact(legal_path, embedded=legal_fingerprint),
        _artifact(primary_path, embedded=primary_fingerprint),
    ]
    if secondary is not None:
        artifacts.append(_artifact(secondary_path, embedded=secondary_fingerprint))
    if report is not None:
        artifacts.append(_artifact(report_path, embedded=report_fingerprint))

    observation_payload = {
        "schema_version": "1.0.0",
        "capture_version": "stage16d-1.0.0",
        "capture_mode": capture_mode.value,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "architecture": "ISSUE_V1",
        "job_id": str(job_id),
        "chain_state": chain_state.value,
        "pipeline_status": pipeline.status.value,
        "pipeline_failure_code": pipeline.failure_code,
        "audit_plan_issue_count": len(issue_ids),
        "primary_completed_issue_count": primary.completed_issue_count,
        "secondary_completed_issue_count": secondary.completed_issue_count if secondary else 0,
        "compared_issue_count": report.compared_issue_count if report else 0,
        "issue_coverage": [item.model_dump(mode="json") for item in issue_coverage],
        "provider_calls": [item.model_dump(mode="json") for item in calls],
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
    }
    observation_fingerprint = _stable_fingerprint(observation_payload)
    observation = IssueV1UATObservation(
        **observation_payload,
        observation_fingerprint=observation_fingerprint,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output_path, observation.model_dump_json(indent=2))

    artifact_fingerprints: dict[str, str] = {}
    for item in artifacts:
        artifact_fingerprints[f"{item.artifact}.file_sha256"] = item.file_sha256
        if item.embedded_fingerprint:
            artifact_fingerprints[f"{item.artifact}.embedded_fingerprint"] = item.embedded_fingerprint

    sanitized = IssueV1UATSanitizedReport(
        capture_mode=capture_mode,
        chain_state=chain_state,
        pipeline_status=pipeline.status.value,
        pipeline_failure_code_present=pipeline.failure_code is not None,
        audit_plan_issue_count=len(issue_ids),
        primary_completed_issue_count=primary.completed_issue_count,
        secondary_completed_issue_count=secondary.completed_issue_count if secondary else 0,
        compared_issue_count=report.compared_issue_count if report else 0,
        provider_summaries=_provider_summaries(calls),
        artifact_fingerprints=artifact_fingerprints,
        observation_fingerprint=observation_fingerprint,
        warnings=[
            "UAT capture is provenance/behavior evidence only; it does not establish legal correctness or professional accuracy.",
            "The capture reader never invokes Audit Planner, DeepSeek, Kimi, OCR or another provider; real network execution must already have occurred through the production ISSUE_V1 Pipeline.",
            "Detailed job/Issue/request provenance remains only in the private UAT observation file.",
        ],
    )
    return observation, sanitized


def load_issue_v1_uat_observation(path: Path) -> IssueV1UATObservation:
    try:
        observation = IssueV1UATObservation.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as exc:
        raise UATCaptureError(f"Invalid UAT observation {path}.") from exc
    payload = observation.model_dump(mode="json", exclude={"observation_fingerprint"})
    if observation.observation_fingerprint != _stable_fingerprint(payload):
        raise UATCaptureError("UAT observation fingerprint is stale or invalid.")
    return observation
