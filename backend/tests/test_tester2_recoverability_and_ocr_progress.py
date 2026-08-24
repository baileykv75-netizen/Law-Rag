from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.audit_planner_provider import AuditPlannerProviderError
from app.issue_primary_audit import IssuePrimaryAuditError
from app.issue_primary_audit_provider import IssuePrimaryAuditProviderError
from app.issue_secondary_review import IssueSecondaryReviewError
from app.issue_secondary_review_provider import IssueSecondaryReviewProviderError
from app.ocr import PaddleOcrProvider, _persist_ocr_progress, load_ocr_progress
from app.pipeline import _mark_recoverable_provider_wait
from app.pipeline_models import PipelineStage, PipelineStatus


def _wrapped(wrapper_type, provider_error):
    try:
        raise provider_error
    except type(provider_error) as exc:
        try:
            raise wrapper_type(str(exc)) from exc
        except wrapper_type as wrapped:
            return wrapped
    raise AssertionError("unreachable")


def test_recoverable_provider_wait_accepts_direct_planner_error(monkeypatch) -> None:
    job_id = uuid4()
    report = SimpleNamespace(current_stage=PipelineStage.AUDIT_PLAN)
    captured = {}
    monkeypatch.setattr("app.pipeline.load_pipeline_report", lambda _: report)

    def fake_mark_waiting(current, stage, *, status, code, detail):
        captured.update(report=current, stage=stage, status=status, code=code, detail=detail)

    monkeypatch.setattr("app.pipeline._mark_waiting", fake_mark_waiting)
    error = AuditPlannerProviderError(
        "DeepSeek connection temporarily interrupted.",
        code="DEEPSEEK_NETWORK_TRANSIENT",
        recoverable=True,
    )

    assert _mark_recoverable_provider_wait(job_id, error) is True
    assert captured["status"] == PipelineStatus.WAITING_EXTERNAL_SERVICE
    assert captured["code"] == "DEEPSEEK_NETWORK_TRANSIENT"


def test_recoverable_provider_wait_follows_wrapped_primary_provider_cause(monkeypatch) -> None:
    job_id = uuid4()
    report = SimpleNamespace(current_stage=PipelineStage.ISSUE_PRIMARY_AUDIT)
    captured = {}
    monkeypatch.setattr("app.pipeline.load_pipeline_report", lambda _: report)
    monkeypatch.setattr(
        "app.pipeline._mark_waiting",
        lambda current, stage, *, status, code, detail: captured.update(
            report=current, stage=stage, status=status, code=code, detail=detail
        ),
    )
    wrapped = _wrapped(
        IssuePrimaryAuditError,
        IssuePrimaryAuditProviderError(
            "DeepSeek transient disconnect.",
            code="DEEPSEEK_NETWORK_TRANSIENT",
            recoverable=True,
        ),
    )

    assert _mark_recoverable_provider_wait(job_id, wrapped) is True
    assert captured["status"] == PipelineStatus.WAITING_EXTERNAL_SERVICE
    assert captured["code"] == "DEEPSEEK_NETWORK_TRANSIENT"


def test_recoverable_provider_wait_follows_wrapped_secondary_provider_cause(monkeypatch) -> None:
    job_id = uuid4()
    report = SimpleNamespace(current_stage=PipelineStage.ISSUE_SECONDARY_REVIEW)
    captured = {}
    monkeypatch.setattr("app.pipeline.load_pipeline_report", lambda _: report)
    monkeypatch.setattr(
        "app.pipeline._mark_waiting",
        lambda current, stage, *, status, code, detail: captured.update(
            report=current, stage=stage, status=status, code=code, detail=detail
        ),
    )
    wrapped = _wrapped(
        IssueSecondaryReviewError,
        IssueSecondaryReviewProviderError(
            "Kimi service temporarily unavailable.",
            code="KIMI_SERVICE_UNAVAILABLE",
            recoverable=True,
        ),
    )

    assert _mark_recoverable_provider_wait(job_id, wrapped) is True
    assert captured["status"] == PipelineStatus.WAITING_EXTERNAL_SERVICE
    assert captured["code"] == "KIMI_SERVICE_UNAVAILABLE"


def test_nonrecoverable_wrapped_provider_error_remains_fail_closed(monkeypatch) -> None:
    job_id = uuid4()
    monkeypatch.setattr(
        "app.pipeline.load_pipeline_report",
        lambda _: SimpleNamespace(current_stage=PipelineStage.ISSUE_PRIMARY_AUDIT),
    )
    wrapped = _wrapped(
        IssuePrimaryAuditError,
        IssuePrimaryAuditProviderError(
            "DeepSeek credential rejected.",
            code="DEEPSEEK_AUTH_REJECTED",
            recoverable=False,
        ),
    )

    assert _mark_recoverable_provider_wait(job_id, wrapped) is False


def test_paddle_pipeline_factory_is_initialized_once_and_reused() -> None:
    calls = 0
    pipeline = object()

    def factory():
        nonlocal calls
        calls += 1
        return pipeline

    provider = PaddleOcrProvider(pipeline_factory=factory, provider_version="test")

    assert provider._get_pipeline() is pipeline
    assert provider._get_pipeline() is pipeline
    assert calls == 1


def test_ocr_page_progress_round_trip_is_atomic(tmp_path, monkeypatch) -> None:
    job_id = uuid4()
    path = tmp_path / "ocr-progress.json"
    monkeypatch.setattr("app.ocr._ocr_progress_path", lambda _: path)

    _persist_ocr_progress(
        job_id,
        state="RUNNING",
        ocr_pages_total=5,
        ocr_pages_processed=2,
        current_page=7,
        detail="正在识别第 3/5 个 OCR 页面。",
    )
    progress = load_ocr_progress(job_id)

    assert progress["state"] == "RUNNING"
    assert progress["ocr_pages_total"] == 5
    assert progress["ocr_pages_processed"] == 2
    assert progress["current_page"] == 7
