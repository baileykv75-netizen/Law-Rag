from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from .ai_audit import AiAuditValidationError, load_ai_audit_report
from .ai_audit_models import AiAuditFinding, ProviderUsage
from .review_comparison_models import AgentActionRecord, ReviewComparisonReport
from .review_workflow import (
    Stage9cWorkflowError,
    Stage9cWorkflowState,
    run_stage9c_workflow,
)
from .secondary_review import SecondaryReviewValidationError, load_secondary_review_report
from .secondary_review_models import SecondaryFindingReview, SecondaryPossibleOmission
from .storage import job_review_report_path

REVIEW_REPORT_SCHEMA_VERSION = "1.0.0"
REVIEW_REPORT_ENGINE_VERSION = "stage9d-report-1.0.0"


class ReviewReport(BaseModel):
    schema_version: str = REVIEW_REPORT_SCHEMA_VERSION
    engine_version: str = REVIEW_REPORT_ENGINE_VERSION
    job_id: UUID
    as_of: str
    final_state: Stage9cWorkflowState
    primary_provider: str
    primary_model: str
    secondary_provider: str
    secondary_model: str
    primary_external_call_occurred: bool
    secondary_external_call_occurred: bool
    primary_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    secondary_usage: ProviderUsage = Field(default_factory=ProviderUsage)
    primary_findings: list[AiAuditFinding] = Field(default_factory=list)
    secondary_reviews: list[SecondaryFindingReview] = Field(default_factory=list)
    possible_primary_omissions: list[SecondaryPossibleOmission] = Field(default_factory=list)
    comparison: ReviewComparisonReport
    action_trace: list[AgentActionRecord] = Field(default_factory=list)
    evidence_gathered: bool = False
    final_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReviewReportError(RuntimeError):
    pass


def _provider_is_external(provider: str) -> bool:
    return provider.strip().lower() in {"deepseek", "kimi"}


def _atomic_write(path: Path, report: ReviewReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def build_review_report(job_id: UUID) -> ReviewReport:
    try:
        primary = load_ai_audit_report(job_id)
        secondary = load_secondary_review_report(job_id)
        workflow = run_stage9c_workflow(job_id)
    except (
        FileNotFoundError,
        AiAuditValidationError,
        SecondaryReviewValidationError,
        Stage9cWorkflowError,
    ) as exc:
        raise ReviewReportError(str(exc)) from exc

    if primary.as_of != secondary.as_of:
        raise ReviewReportError("Primary and secondary reports use different as_of dates.")

    report = ReviewReport(
        job_id=job_id,
        as_of=primary.as_of.isoformat(),
        final_state=workflow.state,
        primary_provider=primary.provider,
        primary_model=primary.model,
        secondary_provider=secondary.provider,
        secondary_model=secondary.model,
        primary_external_call_occurred=_provider_is_external(primary.provider),
        secondary_external_call_occurred=_provider_is_external(secondary.provider),
        primary_usage=primary.provider_usage,
        secondary_usage=secondary.provider_usage,
        primary_findings=primary.findings,
        secondary_reviews=secondary.finding_reviews,
        possible_primary_omissions=secondary.possible_omissions,
        comparison=workflow.comparison,
        action_trace=workflow.executed_actions,
        evidence_gathered=workflow.evidence_gathered,
        final_reasons=workflow.final_reasons,
        warnings=sorted(set([*primary.warnings, *secondary.warnings])),
    )
    _atomic_write(job_review_report_path(job_id), report)
    return report


def load_review_report(job_id: UUID) -> ReviewReport:
    path = job_review_report_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Stage 9 review-report.json does not exist for job {job_id}.")
    try:
        return ReviewReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ReviewReportError(f"Persisted review report is invalid: {exc}") from exc
