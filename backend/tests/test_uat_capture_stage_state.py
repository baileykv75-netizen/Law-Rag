from __future__ import annotations

from uuid import uuid4

import pytest

from app.issue_primary_audit_models import IssuePrimaryAuditArtifact, IssuePrimaryAuditStatus
from app.issue_secondary_review_models import IssueSecondaryReviewArtifact, IssueSecondaryReviewStatus
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStageRecord, PipelineStageState, PipelineStatus
from app.uat_capture import UATCaptureError, _chain_state


def _pipeline(*records: PipelineStageRecord) -> PipelineReport:
    return PipelineReport.model_construct(
        job_id=uuid4(),
        status=PipelineStatus.CANCELLED,
        current_stage=PipelineStage.ISSUE_PRIMARY_AUDIT,
        stages=list(records),
    )


def _record(stage: PipelineStage, state: PipelineStageState) -> PipelineStageRecord:
    return PipelineStageRecord(
        stage=stage,
        state=state,
        label=stage.value,
        progress_percent=50,
    )


def test_primary_interrupted_rejects_pipeline_marking_primary_complete() -> None:
    pipeline = _pipeline(
        _record(PipelineStage.AUDIT_PLAN, PipelineStageState.COMPLETE),
        _record(PipelineStage.ISSUE_LEGAL_CONTEXT, PipelineStageState.COMPLETE),
        _record(PipelineStage.ISSUE_PRIMARY_AUDIT, PipelineStageState.COMPLETE),
    )
    primary = IssuePrimaryAuditArtifact.model_construct(status=IssuePrimaryAuditStatus.INTERRUPTED)

    with pytest.raises(UATCaptureError, match="pipeline stage state"):
        _chain_state(pipeline, primary, None, None)


def test_secondary_interrupted_rejects_pipeline_marking_secondary_complete() -> None:
    pipeline = _pipeline(
        _record(PipelineStage.AUDIT_PLAN, PipelineStageState.COMPLETE),
        _record(PipelineStage.ISSUE_LEGAL_CONTEXT, PipelineStageState.COMPLETE),
        _record(PipelineStage.ISSUE_PRIMARY_AUDIT, PipelineStageState.COMPLETE),
        _record(PipelineStage.ISSUE_SECONDARY_REVIEW, PipelineStageState.COMPLETE),
    )
    primary = IssuePrimaryAuditArtifact.model_construct(status=IssuePrimaryAuditStatus.COMPLETE)
    secondary = IssueSecondaryReviewArtifact.model_construct(status=IssueSecondaryReviewStatus.INTERRUPTED)

    with pytest.raises(UATCaptureError, match="pipeline stage state"):
        _chain_state(pipeline, primary, secondary, None)


def test_complete_chain_requires_complete_issue_stage_records() -> None:
    pipeline = PipelineReport.model_construct(
        job_id=uuid4(),
        status=PipelineStatus.COMPLETE,
        current_stage=PipelineStage.COMPLETE,
        stages=[
            _record(PipelineStage.AUDIT_PLAN, PipelineStageState.COMPLETE),
            _record(PipelineStage.ISSUE_LEGAL_CONTEXT, PipelineStageState.COMPLETE),
            _record(PipelineStage.ISSUE_PRIMARY_AUDIT, PipelineStageState.COMPLETE),
            _record(PipelineStage.ISSUE_SECONDARY_REVIEW, PipelineStageState.COMPLETE),
            _record(PipelineStage.ISSUE_REVIEW_REPORT, PipelineStageState.PENDING),
        ],
    )
    primary = IssuePrimaryAuditArtifact.model_construct(status=IssuePrimaryAuditStatus.COMPLETE)
    secondary = IssueSecondaryReviewArtifact.model_construct(status=IssueSecondaryReviewStatus.COMPLETE)
    report = object()

    with pytest.raises(UATCaptureError, match="pipeline stage state"):
        _chain_state(pipeline, primary, secondary, report)  # type: ignore[arg-type]
