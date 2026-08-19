from __future__ import annotations

import json
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TypeVar
from uuid import UUID

from pydantic import ValidationError

from .audit_planner import AuditPlannerError, load_audit_plan, run_audit_planner
from .audit_planner_provider import (
    AuditPlannerProvider,
    AuditPlannerProviderError,
    planner_provider_from_name,
)
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report, run_audit_rules
from .contract_structure import (
    StructureIncompleteError,
    StructureProcessingError,
    build_contract_structure,
    load_contract_structure,
)
from .evidence_models import SourceEvidenceArtifact
from .issue_legal_context import (
    IssueLegalContextError,
    IssueLegalContextStaleError,
    build_issue_legal_context,
    load_issue_legal_context,
)
from .issue_primary_audit import (
    IssuePrimaryAuditConfigurationError,
    IssuePrimaryAuditError,
    IssuePrimaryAuditStaleError,
    load_issue_primary_audit,
    run_issue_primary_audit,
)
from .issue_primary_audit_models import IssuePrimaryAuditStatus
from .issue_primary_audit_provider import (
    IssuePrimaryAuditProvider,
    IssuePrimaryAuditProviderError,
    issue_primary_provider_from_name,
)
from .issue_review_report import (
    IssueReviewReportError,
    IssueReviewReportStaleError,
    build_issue_review_report,
    load_issue_review_report,
)
from .issue_secondary_review import (
    IssueSecondaryReviewError,
    IssueSecondaryReviewStaleError,
    load_issue_secondary_review,
    run_issue_secondary_review,
)
from .issue_secondary_review_models import IssueSecondaryReviewStatus
from .issue_secondary_review_provider import (
    IssueSecondaryReviewProvider,
    IssueSecondaryReviewProviderError,
    issue_secondary_provider_from_name,
)
from .models import DocumentInspection, DocumentKind, OcrRunResult
from .ocr import OcrProcessingError, OcrProviderUnavailable, run_ocr_for_job
from .pipeline_control import (
    PipelineCancellationRequested,
    ProviderBoundaryPaused,
    approve_provider_phase,
    assert_pipeline_not_cancelled,
    assert_provider_allowed,
    clear_pipeline_cancel,
    ensure_pipeline_control,
    get_pipeline_control,
    request_pipeline_cancel,
    set_provider_mode,
)
from .pipeline_control_models import PipelineControl, ProviderExecutionMode
from .pipeline_models import (
    PipelineReport,
    PipelineStage,
    PipelineStageRecord,
    PipelineStageState,
    PipelineStartRequest,
    PipelineStatus,
)
from .safe_persistence import atomic_write_text
from .storage import (
    find_source_path,
    job_audit_plan_path,
    job_audit_rules_path,
    job_contract_path,
    job_document_path,
    job_evidence_path,
    job_issue_legal_context_path,
    job_issue_primary_audit_path,
    job_issue_review_report_path,
    job_issue_secondary_review_path,
    job_ocr_path,
    job_pipeline_path,
    runtime_dir,
)


class PipelineError(RuntimeError):
    pass


class PipelineNotFoundError(PipelineError):
    pass


class _StageFailure(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class _StageWaitingConfiguration(RuntimeError):
    def __init__(self, stage: PipelineStage, code: str, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage
        self.code = code
        self.detail = detail


_STAGE_SPECS: list[tuple[PipelineStage, str, int]] = [
    (PipelineStage.INGEST, "文件已接收", 10),
    (PipelineStage.OCR, "识别扫描文本", 25),
    (PipelineStage.STRUCTURE, "整理合同结构", 38),
    (PipelineStage.RULES, "执行确定性检查", 48),
    (PipelineStage.AUDIT_PLAN, "制定完整审计计划", 58),
    (PipelineStage.ISSUE_LEGAL_CONTEXT, "逐项检索适用法律", 68),
    (PipelineStage.ISSUE_PRIMARY_AUDIT, "DeepSeek 逐项主审", 82),
    (PipelineStage.ISSUE_SECONDARY_REVIEW, "Kimi 逐项独立复核", 92),
    (PipelineStage.ISSUE_REVIEW_REPORT, "确定性比较并整理结果", 100),
]

_LEGACY_PIPELINE_STAGES = {
    PipelineStage.PRIMARY_AUDIT,
    PipelineStage.SECONDARY_REVIEW,
    PipelineStage.REVIEW_REPORT,
}

PIPELINE_MAX_WORKERS = 4
LOCAL_STAGE_CONCURRENCY = 2
OCR_STAGE_CONCURRENCY = 1
EXTERNAL_PROVIDER_CONCURRENCY = 2

_EXECUTOR = ThreadPoolExecutor(max_workers=PIPELINE_MAX_WORKERS, thread_name_prefix="law-rag-pipeline")
_FUTURES: dict[str, Future[None]] = {}
_FUTURES_LOCK = threading.RLock()
_LOCAL_STAGE_SEMAPHORE = threading.Semaphore(LOCAL_STAGE_CONCURRENCY)
_OCR_STAGE_SEMAPHORE = threading.Semaphore(OCR_STAGE_CONCURRENCY)
_EXTERNAL_PROVIDER_SEMAPHORE = threading.Semaphore(EXTERNAL_PROVIDER_CONCURRENCY)

_T = TypeVar("_T")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _initial_stages() -> list[PipelineStageRecord]:
    return [
        PipelineStageRecord(stage=stage, label=label, progress_percent=progress)
        for stage, label, progress in _STAGE_SPECS
    ]


def _persist(report: PipelineReport) -> None:
    report.updated_at = _now()
    atomic_write_text(job_pipeline_path(report.job_id), report.model_dump_json(indent=2))


def _load_report_if_present(job_id: UUID) -> PipelineReport | None:
    path = runtime_dir() / "jobs" / str(job_id) / "pipeline.json"
    if not path.exists():
        return None
    try:
        return PipelineReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise PipelineError(f"Persisted pipeline state is invalid for job {job_id}.") from exc


def load_pipeline_report(job_id: UUID) -> PipelineReport:
    report = _load_report_if_present(job_id)
    if report is None:
        raise PipelineNotFoundError(f"Pipeline has not been started for job {job_id}.")
    return report


def _ensure_job_exists(job_id: UUID) -> None:
    document = runtime_dir() / "jobs" / str(job_id) / "document.json"
    evidence = runtime_dir() / "jobs" / str(job_id) / "evidence.json"
    if not document.exists() or not evidence.exists():
        raise PipelineNotFoundError(f"Document job {job_id} does not exist or is incomplete.")
    try:
        find_source_path(job_id)
    except FileNotFoundError as exc:
        raise PipelineNotFoundError(str(exc)) from exc


def _is_legacy_pipeline(report: PipelineReport) -> bool:
    return any(item.stage in _LEGACY_PIPELINE_STAGES for item in report.stages)


def _stage(report: PipelineReport, stage: PipelineStage) -> PipelineStageRecord:
    for item in report.stages:
        if item.stage == stage:
            return item
    raise PipelineError(f"Pipeline stage {stage.value} is missing from persisted state.")


def _mark_running(report: PipelineReport, stage: PipelineStage, detail: str = "") -> None:
    item = _stage(report, stage)
    item.state = PipelineStageState.RUNNING
    item.detail = detail
    item.reused_existing_artifact = False
    item.started_at = item.started_at or _now()
    item.finished_at = None
    report.status = PipelineStatus.RUNNING
    report.current_stage = stage
    report.failure_code = None
    report.failure_detail = None
    _persist(report)


def _mark_done(
    report: PipelineReport,
    stage: PipelineStage,
    *,
    detail: str = "",
    skipped: bool = False,
    reused: bool = False,
) -> None:
    item = _stage(report, stage)
    item.state = PipelineStageState.SKIPPED if skipped else PipelineStageState.COMPLETE
    item.detail = detail
    item.reused_existing_artifact = reused
    item.started_at = item.started_at or _now()
    item.finished_at = _now()
    report.progress_percent = max(report.progress_percent, item.progress_percent)
    report.current_stage = stage
    _persist(report)


def _mark_waiting_worker(report: PipelineReport, stage: PipelineStage, detail: str) -> None:
    item = _stage(report, stage)
    item.state = PipelineStageState.WAITING
    item.detail = detail
    item.finished_at = None
    report.status = PipelineStatus.WAITING_WORKER
    report.current_stage = stage
    report.failure_code = None
    report.failure_detail = None
    _persist(report)


def _acquire_resource(
    report: PipelineReport,
    stage: PipelineStage,
    semaphore: threading.Semaphore,
    wait_detail: str,
) -> None:
    if semaphore.acquire(blocking=False):
        return
    _mark_waiting_worker(report, stage, wait_detail)
    semaphore.acquire()


def _mark_waiting(
    report: PipelineReport,
    stage: PipelineStage,
    *,
    status: PipelineStatus,
    code: str,
    detail: str,
) -> None:
    item = _stage(report, stage)
    item.state = PipelineStageState.WAITING
    item.detail = detail
    item.finished_at = _now()
    report.status = status
    report.current_stage = stage
    report.failure_code = code
    report.failure_detail = detail
    _persist(report)


def _mark_failed(report: PipelineReport, stage: PipelineStage, code: str, detail: str) -> None:
    item = _stage(report, stage)
    item.state = PipelineStageState.FAILED
    item.detail = detail
    item.finished_at = _now()
    report.status = PipelineStatus.FAILED
    report.current_stage = stage
    report.failure_code = code
    report.failure_detail = detail
    _persist(report)


def _next_incomplete_stage(report: PipelineReport) -> PipelineStageRecord | None:
    return next(
        (
            item
            for item in report.stages
            if item.state not in {PipelineStageState.COMPLETE, PipelineStageState.SKIPPED}
        ),
        None,
    )


def _mark_cancel_requested(report: PipelineReport, *, provider_in_flight: bool) -> None:
    report.status = PipelineStatus.CANCEL_REQUESTED
    report.failure_code = "PIPELINE_CANCEL_REQUESTED"
    report.failure_detail = (
        "已记录取消请求；当前外部模型阶段已经进入，若请求已发出则无法撤回，系统会在返回后的安全检查点停止。"
        if provider_in_flight
        else "已记录取消请求；Law-Rag 将在当前安全检查点停止，不再启动新的外部模型调用。"
    )
    _persist(report)


def _mark_cancelled(report: PipelineReport) -> None:
    target = _next_incomplete_stage(report)
    if target is not None:
        target.state = PipelineStageState.CANCELLED
        target.detail = "审计已由用户取消；已有本地产物与逐项 checkpoint 保留，不会自动继续外部模型调用。"
        target.finished_at = _now()
        report.current_stage = target.stage
    report.status = PipelineStatus.CANCELLED
    report.failure_code = "PIPELINE_CANCELLED"
    report.failure_detail = "审计已取消。已完成的本地/模型产物保持不变；重新开始需要用户显式操作。"
    report.completed_at = None
    _persist(report)


def _checkpoint_cancel(report: PipelineReport) -> bool:
    try:
        assert_pipeline_not_cancelled(report.job_id)
        return True
    except PipelineCancellationRequested:
        _mark_cancelled(report)
        return False


def _load_document(job_id: UUID) -> DocumentInspection:
    """Load common document metadata without forcing every source into pages.

    PDF/image jobs keep their historical PageEvidence[] persistence. DOCX jobs
    persist a SourceEvidenceArtifact instead, so the pipeline validates that
    typed artifact and supplies an empty pages list to the common inspection
    model. Source-format differences stop here; later pipeline stages remain
    format-neutral.
    """

    try:
        document_payload = json.loads(job_document_path(job_id).read_text(encoding="utf-8"))
        document_kind = DocumentKind(document_payload["document_kind"])
        evidence_text = job_evidence_path(job_id).read_text(encoding="utf-8")

        if document_kind == DocumentKind.DOCX:
            evidence = SourceEvidenceArtifact.model_validate_json(evidence_text)
            if evidence.job_id != job_id:
                raise ValueError("DOCX evidence job identity does not match the pipeline job")
            if evidence.source_document.document_kind != DocumentKind.DOCX:
                raise ValueError("DOCX evidence source kind does not match document metadata")
            if evidence.source_document.filename != document_payload.get("filename"):
                raise ValueError("DOCX evidence filename does not match document metadata")
            if evidence.source_document.media_type != document_payload.get("media_type"):
                raise ValueError("DOCX evidence media type does not match document metadata")
            pages = []
        else:
            pages = json.loads(evidence_text)
            if not isinstance(pages, list):
                raise ValueError("PDF/image evidence must remain a paginated evidence list")

        return DocumentInspection.model_validate({**document_payload, "pages": pages})
    except Exception as exc:
        raise _StageFailure("DOCUMENT_EVIDENCE_INVALID", "已接收文件的文档证据无法安全读取。") from exc


def _existing_ocr(job_id: UUID) -> OcrRunResult | None:
    path = job_ocr_path(job_id)
    if not path.exists():
        return None
    try:
        return OcrRunResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def _run_ocr_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    document = _load_document(job_id)
    if document.ocr_required_pages == 0:
        _mark_done(report, PipelineStage.OCR, detail="现有源文本可用，无需 OCR。", skipped=True)
        return

    existing = _existing_ocr(job_id)
    if existing is not None and existing.status == "complete":
        _mark_done(report, PipelineStage.OCR, detail="复用已完成 OCR 结果。", reused=True)
        return

    _acquire_resource(report, PipelineStage.OCR, _OCR_STAGE_SEMAPHORE, "等待 OCR 处理名额。")
    try:
        _mark_running(report, PipelineStage.OCR, "正在识别需要 OCR 的页面。")
        result = run_ocr_for_job(job_id)
        if result.status != "complete":
            raise _StageFailure(
                "OCR_INCOMPLETE",
                "OCR 未完整完成；请检查无文本/失败页面后重试，已有其他合同任务不会受影响。",
            )
        _mark_done(report, PipelineStage.OCR, detail="OCR 已完成。")
    finally:
        _OCR_STAGE_SEMAPHORE.release()


def _run_structure_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_contract_path(job_id).exists():
        try:
            load_contract_structure(job_id)
            _mark_done(report, PipelineStage.STRUCTURE, detail="复用已生成合同结构。", reused=True)
            return
        except Exception:
            pass

    _acquire_resource(report, PipelineStage.STRUCTURE, _LOCAL_STAGE_SEMAPHORE, "等待本地处理名额。")
    try:
        _mark_running(report, PipelineStage.STRUCTURE, "正在整理合同条款与关键字段。")
        build_contract_structure(job_id)
        _mark_done(report, PipelineStage.STRUCTURE, detail="合同结构已生成。")
    finally:
        _LOCAL_STAGE_SEMAPHORE.release()


def _run_rules_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_audit_rules_path(job_id).exists():
        try:
            load_audit_rule_report(job_id)
            _mark_done(report, PipelineStage.RULES, detail="复用已完成确定性检查。", reused=True)
            return
        except Exception:
            pass

    _acquire_resource(report, PipelineStage.RULES, _LOCAL_STAGE_SEMAPHORE, "等待本地处理名额。")
    try:
        _mark_running(report, PipelineStage.RULES, "正在执行确定性合同检查。")
        run_audit_rules(job_id)
        _mark_done(report, PipelineStage.RULES, detail="确定性检查已完成。")
    finally:
        _LOCAL_STAGE_SEMAPHORE.release()


def _provider_slot_call(
    report: PipelineReport,
    stage: PipelineStage,
    *,
    wait_detail: str,
    running_detail: str,
    action: Callable[[], _T],
) -> _T:
    """Limit actual outbound work while preserving Stage 13A persisted controls.

    Stage 13B/E/F records the provider boundary immediately before calling the
    provider object. The pipeline-owned provider adapters then acquire the global
    outbound slot and re-check persisted provider/cancel intent before performing
    the real HTTP-producing delegate call. If the user pauses/cancels while the
    adapter is waiting for a slot, no new external request is sent.
    """

    _acquire_resource(report, stage, _EXTERNAL_PROVIDER_SEMAPHORE, wait_detail)
    try:
        assert_provider_allowed(report.job_id)
        _mark_running(report, stage, running_detail)
        return action()
    finally:
        _EXTERNAL_PROVIDER_SEMAPHORE.release()


class _PipelinePlannerProvider(AuditPlannerProvider):
    def __init__(self, delegate: AuditPlannerProvider, report: PipelineReport) -> None:
        self.delegate = delegate
        self.report = report
        self.provider_name = delegate.provider_name
        self.model_name = delegate.model_name

    def generate(self, planner_input):
        return _provider_slot_call(
            self.report,
            PipelineStage.AUDIT_PLAN,
            wait_detail="审计规划上下文已准备，等待外部模型调用名额。",
            running_detail="正在调用 DeepSeek 制定受限审计计划。",
            action=lambda: self.delegate.generate(planner_input),
        )


class _PipelinePrimaryProvider(IssuePrimaryAuditProvider):
    def __init__(self, delegate: IssuePrimaryAuditProvider, report: PipelineReport) -> None:
        self.delegate = delegate
        self.report = report
        self.provider_name = delegate.provider_name
        self.model_name = delegate.model_name

    def health(self):
        return self.delegate.health()

    def generate(self, context):
        return _provider_slot_call(
            self.report,
            PipelineStage.ISSUE_PRIMARY_AUDIT,
            wait_detail="当前 Issue 已准备，等待 DeepSeek 调用名额。",
            running_detail=f"正在调用 DeepSeek 审查 Issue：{context.topic}",
            action=lambda: self.delegate.generate(context),
        )


class _PipelineSecondaryProvider(IssueSecondaryReviewProvider):
    def __init__(self, delegate: IssueSecondaryReviewProvider, report: PipelineReport) -> None:
        self.delegate = delegate
        self.report = report
        self.provider_name = delegate.provider_name
        self.model_name = delegate.model_name

    def health(self):
        return self.delegate.health()

    def generate(self, context, primary):
        return _provider_slot_call(
            self.report,
            PipelineStage.ISSUE_SECONDARY_REVIEW,
            wait_detail="当前 Issue 二审上下文已准备，等待 Kimi 调用名额。",
            running_detail=f"正在调用 Kimi 独立复核 Issue：{context.topic}",
            action=lambda: self.delegate.generate(context, primary),
        )


def _run_audit_plan_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_audit_plan_path(job_id).exists():
        try:
            existing = load_audit_plan(job_id)
            contract = load_contract_structure(job_id)
            rules = load_audit_rule_report(job_id)
            if (
                existing.coverage_complete
                and existing.contract_source_fingerprint == contract.source_fingerprint
                and existing.contract_content_fingerprint == rules.contract_content_fingerprint
            ):
                _mark_done(
                    report,
                    PipelineStage.AUDIT_PLAN,
                    detail="复用与当前合同和确定性检查一致的审计计划。",
                    reused=True,
                )
                return
        except Exception:
            pass

    try:
        delegate = planner_provider_from_name("deepseek")
    except AuditPlannerProviderError:
        raise
    if delegate.provider_name == "deepseek" and not getattr(delegate, "api_key", ""):
        raise _StageWaitingConfiguration(
            PipelineStage.AUDIT_PLAN,
            "DEEPSEEK_NOT_CONFIGURED",
            "DeepSeek API key is not configured.",
        )

    _mark_running(report, PipelineStage.AUDIT_PLAN, "正在本机构建完整 Audit Planner 输入。")
    run_audit_planner(job_id, provider=_PipelinePlannerProvider(delegate, report))
    _mark_done(report, PipelineStage.AUDIT_PLAN, detail="完整审计计划与条款覆盖记录已生成。")


def _run_issue_legal_context_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_issue_legal_context_path(job_id).exists():
        try:
            existing = load_issue_legal_context(job_id)
            if existing.as_of == report.as_of and existing.use_semantic == report.use_semantic:
                _mark_done(
                    report,
                    PipelineStage.ISSUE_LEGAL_CONTEXT,
                    detail="复用与当前 AuditPlan、法律语料和检索配置一致的逐项法律上下文。",
                    reused=True,
                )
                return
        except (IssueLegalContextError, IssueLegalContextStaleError, FileNotFoundError):
            pass

    _acquire_resource(
        report,
        PipelineStage.ISSUE_LEGAL_CONTEXT,
        _LOCAL_STAGE_SEMAPHORE,
        "等待本地 Legal RAG 处理名额。",
    )
    try:
        _mark_running(report, PipelineStage.ISSUE_LEGAL_CONTEXT, "正在按 AuditPlan Issue 逐项检索本地法律证据。")
        build_issue_legal_context(
            job_id,
            as_of=report.as_of,
            use_semantic=report.use_semantic,
        )
        _mark_done(report, PipelineStage.ISSUE_LEGAL_CONTEXT, detail="逐项法律证据上下文已生成。")
    finally:
        _LOCAL_STAGE_SEMAPHORE.release()


def _run_issue_primary_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    try:
        delegate = issue_primary_provider_from_name("deepseek")
    except IssuePrimaryAuditProviderError:
        raise

    if job_issue_primary_audit_path(job_id).exists():
        try:
            existing = load_issue_primary_audit(job_id)
            if (
                existing.status == IssuePrimaryAuditStatus.COMPLETE
                and existing.as_of == report.as_of
                and existing.provider == delegate.provider_name
                and existing.model == delegate.model_name
            ):
                _mark_done(
                    report,
                    PipelineStage.ISSUE_PRIMARY_AUDIT,
                    detail="复用与当前 Issue Legal RAG 一致的 DeepSeek 逐项主审结果。",
                    reused=True,
                )
                return
        except (IssuePrimaryAuditError, IssuePrimaryAuditStaleError, FileNotFoundError):
            pass

    health = delegate.health()
    if not health.configured:
        raise _StageWaitingConfiguration(
            PipelineStage.ISSUE_PRIMARY_AUDIT,
            "DEEPSEEK_NOT_CONFIGURED",
            health.detail,
        )

    _mark_running(report, PipelineStage.ISSUE_PRIMARY_AUDIT, "正在重建逐项证据上下文并复用已有 checkpoint。")
    run_issue_primary_audit(
        job_id,
        provider_override=_PipelinePrimaryProvider(delegate, report),
    )
    _mark_done(report, PipelineStage.ISSUE_PRIMARY_AUDIT, detail="DeepSeek 已完成全部 AuditPlan Issue 的主审。")


def _run_issue_secondary_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    try:
        delegate = issue_secondary_provider_from_name("kimi")
    except IssueSecondaryReviewProviderError:
        raise

    if job_issue_secondary_review_path(job_id).exists():
        try:
            existing = load_issue_secondary_review(job_id)
            if (
                existing.status == IssueSecondaryReviewStatus.COMPLETE
                and existing.provider == delegate.provider_name
                and existing.model == delegate.model_name
            ):
                _mark_done(
                    report,
                    PipelineStage.ISSUE_SECONDARY_REVIEW,
                    detail="复用与当前 DeepSeek 主审一致的 Kimi 逐项复核结果。",
                    reused=True,
                )
                return
        except (IssueSecondaryReviewError, IssueSecondaryReviewStaleError, FileNotFoundError):
            pass

    health = delegate.health()
    if not health.configured:
        raise _StageWaitingConfiguration(
            PipelineStage.ISSUE_SECONDARY_REVIEW,
            "KIMI_NOT_CONFIGURED",
            health.detail,
        )

    _mark_running(report, PipelineStage.ISSUE_SECONDARY_REVIEW, "正在重建 Kimi 逐项复核上下文并复用已有 checkpoint。")
    run_issue_secondary_review(
        job_id,
        provider_override=_PipelineSecondaryProvider(delegate, report),
    )
    _mark_done(report, PipelineStage.ISSUE_SECONDARY_REVIEW, detail="Kimi 已完成全部 AuditPlan Issue 的独立复核。")


def _run_issue_review_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_issue_review_report_path(job_id).exists():
        try:
            existing = load_issue_review_report(job_id)
            if existing.as_of == report.as_of:
                _mark_done(
                    report,
                    PipelineStage.ISSUE_REVIEW_REPORT,
                    detail="复用当前 13E/13F 结果对应的确定性 Issue Review Report。",
                    reused=True,
                )
                return
        except (IssueReviewReportError, IssueReviewReportStaleError, FileNotFoundError):
            pass

    _acquire_resource(
        report,
        PipelineStage.ISSUE_REVIEW_REPORT,
        _LOCAL_STAGE_SEMAPHORE,
        "等待本地比较处理名额。",
    )
    try:
        _mark_running(report, PipelineStage.ISSUE_REVIEW_REPORT, "正在逐 Issue 确定性比较 DeepSeek 与 Kimi 结果。")
        build_issue_review_report(job_id)
        _mark_done(report, PipelineStage.ISSUE_REVIEW_REPORT, detail="逐项比较与最终 Issue Review Report 已生成。")
    finally:
        _LOCAL_STAGE_SEMAPHORE.release()


def _run_pipeline(job_id: UUID) -> None:
    try:
        report = load_pipeline_report(job_id)
        if _is_legacy_pipeline(report):
            raise PipelineError(
                "This is an unfinished legacy RC2 pipeline. Stage 13G.3 will not silently resume it with the new issue architecture; legacy migration is handled in Stage 13G.4."
            )

        ingest = _stage(report, PipelineStage.INGEST)
        if ingest.state not in {PipelineStageState.COMPLETE, PipelineStageState.SKIPPED}:
            ingest.state = PipelineStageState.COMPLETE
            ingest.detail = "上传与文档初检已完成。"
            ingest.reused_existing_artifact = True
            ingest.started_at = ingest.started_at or report.started_at
            ingest.finished_at = _now()
            report.progress_percent = max(report.progress_percent, ingest.progress_percent)
            report.status = PipelineStatus.RUNNING
            _persist(report)

        stages: list[Callable[[PipelineReport], None]] = [
            _run_ocr_stage,
            _run_structure_stage,
            _run_rules_stage,
            _run_audit_plan_stage,
            _run_issue_legal_context_stage,
            _run_issue_primary_stage,
            _run_issue_secondary_stage,
            _run_issue_review_stage,
        ]
        for runner in stages:
            if not _checkpoint_cancel(report):
                return
            runner(report)
        if not _checkpoint_cancel(report):
            return

        report.status = PipelineStatus.COMPLETE
        report.current_stage = PipelineStage.COMPLETE
        report.progress_percent = 100
        report.completed_at = _now()
        report.failure_code = None
        report.failure_detail = None
        _persist(report)
    except ProviderBoundaryPaused as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            report.current_stage,
            status=PipelineStatus.PAUSED_BEFORE_PROVIDER,
            code=exc.code,
            detail=exc.detail,
        )
    except PipelineCancellationRequested:
        report = load_pipeline_report(job_id)
        _mark_cancelled(report)
    except OcrProviderUnavailable as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            PipelineStage.OCR,
            status=PipelineStatus.WAITING_OPTIONAL_COMPONENT,
            code="OCR_NOT_AVAILABLE",
            detail=str(exc),
        )
    except _StageWaitingConfiguration as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            exc.stage,
            status=PipelineStatus.WAITING_CONFIGURATION,
            code=exc.code,
            detail=exc.detail,
        )
    except IssuePrimaryAuditConfigurationError as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            PipelineStage.ISSUE_PRIMARY_AUDIT,
            status=PipelineStatus.WAITING_CONFIGURATION,
            code="DEEPSEEK_NOT_CONFIGURED",
            detail=str(exc),
        )
    except _StageFailure as exc:
        report = load_pipeline_report(job_id)
        _mark_failed(report, report.current_stage, exc.code, exc.detail)
    except (
        FileNotFoundError,
        OcrProcessingError,
        StructureIncompleteError,
        StructureProcessingError,
        AuditRuleProcessingError,
        AuditPlannerProviderError,
        AuditPlannerError,
        IssueLegalContextError,
        IssuePrimaryAuditProviderError,
        IssuePrimaryAuditError,
        IssueSecondaryReviewProviderError,
        IssueSecondaryReviewError,
        IssueReviewReportError,
        PipelineError,
    ) as exc:
        report = load_pipeline_report(job_id)
        _mark_failed(report, report.current_stage, type(exc).__name__, str(exc))
    except Exception as exc:
        report = load_pipeline_report(job_id)
        _mark_failed(
            report,
            report.current_stage,
            "UNEXPECTED_PIPELINE_ERROR",
            f"Unexpected pipeline failure: {type(exc).__name__}.",
        )


def _active_future(job_id: UUID) -> Future[None] | None:
    with _FUTURES_LOCK:
        future = _FUTURES.get(str(job_id))
        if future is not None and not future.done():
            return future
    return None


def _forget_future(job_key: str, completed: Future[None]) -> None:
    with _FUTURES_LOCK:
        if _FUTURES.get(job_key) is completed:
            _FUTURES.pop(job_key, None)


def start_pipeline(job_id: UUID, request: PipelineStartRequest) -> PipelineReport:
    _ensure_job_exists(job_id)
    existing = _load_report_if_present(job_id)

    if existing is not None:
        if existing.as_of != request.as_of or existing.use_semantic != request.use_semantic:
            raise PipelineError(
                "A pipeline already exists for this job with different as_of/use_semantic settings. "
                "Create a new job or use the existing pipeline settings."
            )
        if existing.status == PipelineStatus.COMPLETE:
            return existing
        if _is_legacy_pipeline(existing):
            raise PipelineError(
                "This job has an unfinished legacy RC2 pipeline. Stage 13G.3 keeps it readable but will not migrate it in place; Stage 13G.4 provides the compatibility path."
            )
        if existing.status == PipelineStatus.CANCELLED:
            raise PipelineError("This pipeline was explicitly cancelled. Use the resume action to restart it.")
        if _active_future(job_id) is not None:
            return existing
        ensure_pipeline_control(job_id, request.provider_mode)
    else:
        ensure_pipeline_control(job_id, request.provider_mode)

    if existing is None:
        now = _now()
        stages = _initial_stages()
        stages[0].detail = "等待后台处理名额。"
        report = PipelineReport(
            job_id=job_id,
            status=PipelineStatus.QUEUED,
            current_stage=PipelineStage.INGEST,
            progress_percent=0,
            as_of=request.as_of,
            use_semantic=request.use_semantic,
            started_at=now,
            updated_at=now,
            stages=stages,
        )
    else:
        report = existing
        report.status = PipelineStatus.QUEUED
        report.failure_code = None
        report.failure_detail = None
        report.completed_at = None
        for item in report.stages:
            if item.state in {
                PipelineStageState.RUNNING,
                PipelineStageState.WAITING,
                PipelineStageState.FAILED,
            }:
                item.state = PipelineStageState.PENDING
                item.detail = ""
                item.finished_at = None
        pending = next((item for item in report.stages if item.state == PipelineStageState.PENDING), None)
        if pending is not None:
            report.current_stage = pending.stage
            pending.detail = "等待后台处理名额。"

    _persist(report)

    with _FUTURES_LOCK:
        active = _FUTURES.get(str(job_id))
        if active is not None and not active.done():
            return load_pipeline_report(job_id)
        future = _EXECUTOR.submit(_run_pipeline, job_id)
        _FUTURES[str(job_id)] = future
        future.add_done_callback(lambda done, key=str(job_id): _forget_future(key, done))
    return load_pipeline_report(job_id)


def retry_pipeline(job_id: UUID) -> PipelineReport:
    existing = load_pipeline_report(job_id)
    if existing.status == PipelineStatus.COMPLETE:
        return existing
    if existing.status in {PipelineStatus.CANCELLED, PipelineStatus.CANCEL_REQUESTED}:
        raise PipelineError("Cancelled pipelines require the explicit resume action.")
    control = get_pipeline_control(job_id)
    return start_pipeline(
        job_id,
        PipelineStartRequest(
            as_of=existing.as_of,
            use_semantic=existing.use_semantic,
            provider_mode=control.provider_mode,
        ),
    )


def approve_provider_and_resume(job_id: UUID) -> PipelineReport:
    existing = load_pipeline_report(job_id)
    if existing.status == PipelineStatus.COMPLETE:
        return existing
    if existing.status in {PipelineStatus.CANCELLED, PipelineStatus.CANCEL_REQUESTED}:
        raise PipelineError("Cancelled pipelines must be resumed before provider approval.")
    control = approve_provider_phase(job_id)
    return start_pipeline(
        job_id,
        PipelineStartRequest(
            as_of=existing.as_of,
            use_semantic=existing.use_semantic,
            provider_mode=control.provider_mode,
        ),
    )


def pause_before_provider(job_id: UUID) -> PipelineControl:
    load_pipeline_report(job_id)
    return set_provider_mode(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)


def set_pipeline_provider_mode(job_id: UUID, provider_mode: ProviderExecutionMode) -> PipelineControl:
    report = load_pipeline_report(job_id)
    control = set_provider_mode(job_id, provider_mode)
    if provider_mode == ProviderExecutionMode.AUTO_CONTINUE and report.status == PipelineStatus.PAUSED_BEFORE_PROVIDER:
        start_pipeline(
            job_id,
            PipelineStartRequest(
                as_of=report.as_of,
                use_semantic=report.use_semantic,
                provider_mode=provider_mode,
            ),
        )
    return control


def cancel_pipeline(job_id: UUID) -> tuple[PipelineReport, PipelineControl]:
    report = load_pipeline_report(job_id)
    if report.status == PipelineStatus.COMPLETE:
        raise PipelineError("Completed pipelines cannot be cancelled.")
    if report.status == PipelineStatus.CANCELLED:
        return report, get_pipeline_control(job_id)

    control = request_pipeline_cancel(job_id)
    active = _active_future(job_id)
    if active is None:
        _mark_cancelled(report)
    else:
        _mark_cancel_requested(report, provider_in_flight=control.active_provider is not None)
    return load_pipeline_report(job_id), control


def resume_cancelled_pipeline(job_id: UUID) -> PipelineReport:
    existing = load_pipeline_report(job_id)
    if existing.status not in {PipelineStatus.CANCELLED, PipelineStatus.CANCEL_REQUESTED}:
        raise PipelineError("Only cancelled pipelines use the explicit resume action.")
    if _active_future(job_id) is not None:
        raise PipelineError("Cancellation is still being applied; retry after the current stage reaches a safe stop.")
    if _is_legacy_pipeline(existing):
        raise PipelineError(
            "Cancelled legacy RC2 pipelines stay preserved in Stage 13G.3; explicit legacy migration is handled in Stage 13G.4."
        )

    control = clear_pipeline_cancel(job_id)
    for item in existing.stages:
        if item.state == PipelineStageState.CANCELLED:
            item.state = PipelineStageState.PENDING
            item.detail = ""
            item.finished_at = None
    existing.status = PipelineStatus.FAILED
    existing.failure_code = "PIPELINE_RESUME_REQUESTED"
    existing.failure_detail = "用户已显式要求重新开始已取消的审计。"
    _persist(existing)
    return start_pipeline(
        job_id,
        PipelineStartRequest(
            as_of=existing.as_of,
            use_semantic=existing.use_semantic,
            provider_mode=control.provider_mode,
        ),
    )
