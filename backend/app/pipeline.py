from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .ai_audit import (
    AiAuditConfigurationError,
    AiAuditError,
    load_ai_audit_report,
    run_primary_ai_audit,
)
from .ai_audit_models import AiAuditRunRequest
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report, run_audit_rules
from .contract_structure import (
    StructureIncompleteError,
    StructureProcessingError,
    build_contract_structure,
    load_contract_structure,
)
from .models import DocumentInspection, OcrRunResult
from .ocr import OcrProcessingError, OcrProviderUnavailable, run_ocr_for_job
from .pipeline_models import (
    PipelineReport,
    PipelineStage,
    PipelineStageRecord,
    PipelineStageState,
    PipelineStartRequest,
    PipelineStatus,
)
from .review_report import ReviewReportError, build_review_report, load_review_report
from .safe_persistence import atomic_write_text
from .secondary_review import (
    SecondaryReviewConfigurationError,
    SecondaryReviewContextError,
    SecondaryReviewError,
    SecondaryReviewValidationError,
    load_secondary_review_report,
    run_secondary_review,
)
from .secondary_review_models import SecondaryReviewRunRequest
from .storage import (
    find_source_path,
    job_ai_audit_path,
    job_audit_rules_path,
    job_contract_path,
    job_document_path,
    job_evidence_path,
    job_ocr_path,
    job_pipeline_path,
    job_review_report_path,
    job_secondary_review_path,
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


_STAGE_SPECS: list[tuple[PipelineStage, str, int]] = [
    (PipelineStage.INGEST, "文件已接收", 10),
    (PipelineStage.OCR, "识别扫描文本", 30),
    (PipelineStage.STRUCTURE, "整理合同结构", 45),
    (PipelineStage.RULES, "执行确定性检查", 55),
    (PipelineStage.PRIMARY_AUDIT, "检索法律依据并进行主审", 75),
    (PipelineStage.SECONDARY_REVIEW, "进行独立二审", 90),
    (PipelineStage.REVIEW_REPORT, "比较双模型并整理结果", 100),
]

_THREADS: dict[str, threading.Thread] = {}
_THREADS_LOCK = threading.Lock()


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


def _load_document(job_id: UUID) -> DocumentInspection:
    try:
        document_payload = json.loads(job_document_path(job_id).read_text(encoding="utf-8"))
        evidence_payload = json.loads(job_evidence_path(job_id).read_text(encoding="utf-8"))
        return DocumentInspection.model_validate({**document_payload, "pages": evidence_payload})
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
        _mark_done(report, PipelineStage.OCR, detail="原生文本可用，无需 OCR。", skipped=True)
        return

    existing = _existing_ocr(job_id)
    if existing is not None and existing.status == "complete":
        _mark_done(report, PipelineStage.OCR, detail="复用已完成 OCR 结果。", reused=True)
        return

    _mark_running(report, PipelineStage.OCR, "正在识别需要 OCR 的页面。")
    result = run_ocr_for_job(job_id)
    if result.status != "complete":
        raise _StageFailure(
            "OCR_INCOMPLETE",
            "OCR 未完整完成；请检查无文本/失败页面后重试，已有其他合同任务不会受影响。",
        )
    _mark_done(report, PipelineStage.OCR, detail="OCR 已完成。")


def _run_structure_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_contract_path(job_id).exists():
        try:
            load_contract_structure(job_id)
            _mark_done(report, PipelineStage.STRUCTURE, detail="复用已生成合同结构。", reused=True)
            return
        except Exception:
            pass
    _mark_running(report, PipelineStage.STRUCTURE, "正在整理合同条款与关键字段。")
    build_contract_structure(job_id)
    _mark_done(report, PipelineStage.STRUCTURE, detail="合同结构已生成。")


def _run_rules_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_audit_rules_path(job_id).exists():
        try:
            load_audit_rule_report(job_id)
            _mark_done(report, PipelineStage.RULES, detail="复用已完成确定性检查。", reused=True)
            return
        except Exception:
            pass
    _mark_running(report, PipelineStage.RULES, "正在执行确定性合同检查。")
    run_audit_rules(job_id)
    _mark_done(report, PipelineStage.RULES, detail="确定性检查已完成。")


def _run_primary_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    if job_ai_audit_path(job_id).exists():
        try:
            existing = load_ai_audit_report(job_id)
            if existing.as_of == report.as_of:
                _mark_done(
                    report,
                    PipelineStage.PRIMARY_AUDIT,
                    detail="复用同一法律适用日期的主审结果。",
                    reused=True,
                )
                return
        except Exception:
            pass
    _mark_running(report, PipelineStage.PRIMARY_AUDIT, "正在检索法律依据并进行 DeepSeek 主审。")
    run_primary_ai_audit(
        job_id,
        AiAuditRunRequest(as_of=report.as_of, provider="deepseek", use_semantic=report.use_semantic),
    )
    _mark_done(report, PipelineStage.PRIMARY_AUDIT, detail="法律检索与 DeepSeek 主审已完成。")


def _run_secondary_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    primary = load_ai_audit_report(job_id)
    if job_secondary_review_path(job_id).exists():
        try:
            existing = load_secondary_review_report(job_id)
            if (
                existing.as_of == report.as_of
                and existing.primary_context_fingerprint == primary.context_fingerprint
            ):
                _mark_done(
                    report,
                    PipelineStage.SECONDARY_REVIEW,
                    detail="复用与当前主审一致的 Kimi 二审结果。",
                    reused=True,
                )
                return
        except Exception:
            pass
    _mark_running(report, PipelineStage.SECONDARY_REVIEW, "正在进行 Kimi 独立二审。")
    run_secondary_review(
        job_id,
        SecondaryReviewRunRequest(provider="kimi", use_semantic=report.use_semantic),
    )
    _mark_done(report, PipelineStage.SECONDARY_REVIEW, detail="Kimi 二审已完成。")


def _run_review_stage(report: PipelineReport) -> None:
    job_id = report.job_id
    primary = load_ai_audit_report(job_id)
    secondary = load_secondary_review_report(job_id)
    if job_review_report_path(job_id).exists():
        try:
            existing = load_review_report(job_id)
            if (
                existing.as_of == report.as_of.isoformat()
                and existing.primary_provider == primary.provider
                and existing.secondary_provider == secondary.provider
            ):
                _mark_done(
                    report,
                    PipelineStage.REVIEW_REPORT,
                    detail="复用当前双模型结果对应的复核报告。",
                    reused=True,
                )
                return
        except Exception:
            pass
    _mark_running(report, PipelineStage.REVIEW_REPORT, "正在比较双模型结果并执行受限本地补证据。")
    build_review_report(job_id)
    _mark_done(report, PipelineStage.REVIEW_REPORT, detail="双模型比较与最终复核报告已生成。")


def _run_pipeline(job_id: UUID) -> None:
    try:
        report = load_pipeline_report(job_id)
        ingest = _stage(report, PipelineStage.INGEST)
        if ingest.state not in {PipelineStageState.COMPLETE, PipelineStageState.SKIPPED}:
            ingest.state = PipelineStageState.COMPLETE
            ingest.detail = "上传与文档初检已完成。"
            ingest.reused_existing_artifact = True
            ingest.started_at = ingest.started_at or report.started_at
            ingest.finished_at = _now()
            report.progress_percent = max(report.progress_percent, ingest.progress_percent)
            _persist(report)

        _run_ocr_stage(report)
        _run_structure_stage(report)
        _run_rules_stage(report)
        _run_primary_stage(report)
        _run_secondary_stage(report)
        _run_review_stage(report)

        report.status = PipelineStatus.COMPLETE
        report.current_stage = PipelineStage.COMPLETE
        report.progress_percent = 100
        report.completed_at = _now()
        report.failure_code = None
        report.failure_detail = None
        _persist(report)
    except OcrProviderUnavailable as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            PipelineStage.OCR,
            status=PipelineStatus.WAITING_OPTIONAL_COMPONENT,
            code="OCR_NOT_AVAILABLE",
            detail=str(exc),
        )
    except AiAuditConfigurationError as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            PipelineStage.PRIMARY_AUDIT,
            status=PipelineStatus.WAITING_CONFIGURATION,
            code="DEEPSEEK_NOT_CONFIGURED",
            detail=str(exc),
        )
    except SecondaryReviewConfigurationError as exc:
        report = load_pipeline_report(job_id)
        _mark_waiting(
            report,
            PipelineStage.SECONDARY_REVIEW,
            status=PipelineStatus.WAITING_CONFIGURATION,
            code="KIMI_NOT_CONFIGURED",
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
        AiAuditError,
        SecondaryReviewContextError,
        SecondaryReviewValidationError,
        SecondaryReviewError,
        ReviewReportError,
    ) as exc:
        report = load_pipeline_report(job_id)
        _mark_failed(report, report.current_stage, type(exc).__name__, str(exc))
    except Exception as exc:  # fail closed without persisting arbitrary exception payloads
        report = load_pipeline_report(job_id)
        _mark_failed(
            report,
            report.current_stage,
            "UNEXPECTED_PIPELINE_ERROR",
            f"Unexpected pipeline failure: {type(exc).__name__}.",
        )
    finally:
        with _THREADS_LOCK:
            current = _THREADS.get(str(job_id))
            if current is threading.current_thread():
                _THREADS.pop(str(job_id), None)


def start_pipeline(job_id: UUID, request: PipelineStartRequest) -> PipelineReport:
    _ensure_job_exists(job_id)
    existing = _load_report_if_present(job_id)
    if existing is not None and existing.status == PipelineStatus.COMPLETE:
        return existing

    if existing is None:
        now = _now()
        report = PipelineReport(
            job_id=job_id,
            status=PipelineStatus.QUEUED,
            current_stage=PipelineStage.INGEST,
            progress_percent=0,
            as_of=request.as_of,
            use_semantic=request.use_semantic,
            started_at=now,
            updated_at=now,
            stages=_initial_stages(),
        )
    else:
        report = existing
        if report.as_of != request.as_of or report.use_semantic != request.use_semantic:
            raise PipelineError(
                "A pipeline already exists for this job with different as_of/use_semantic settings. "
                "Create a new job or use the existing pipeline settings."
            )
        report.status = PipelineStatus.QUEUED
        report.failure_code = None
        report.failure_detail = None
        report.completed_at = None
        for item in report.stages:
            if item.state in {PipelineStageState.RUNNING, PipelineStageState.WAITING, PipelineStageState.FAILED}:
                item.state = PipelineStageState.PENDING
                item.detail = ""
                item.finished_at = None

    _persist(report)

    with _THREADS_LOCK:
        active = _THREADS.get(str(job_id))
        if active is not None and active.is_alive():
            return load_pipeline_report(job_id)
        thread = threading.Thread(
            target=_run_pipeline,
            args=(job_id,),
            name=f"law-rag-pipeline-{job_id}",
            daemon=True,
        )
        _THREADS[str(job_id)] = thread
        thread.start()
    return load_pipeline_report(job_id)


def retry_pipeline(job_id: UUID) -> PipelineReport:
    existing = load_pipeline_report(job_id)
    if existing.status == PipelineStatus.COMPLETE:
        return existing
    return start_pipeline(
        job_id,
        PipelineStartRequest(as_of=existing.as_of, use_semantic=existing.use_semantic),
    )
