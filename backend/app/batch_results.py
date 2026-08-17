from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from .batch_results_models import (
    BatchJobResult,
    BatchJobState,
    BatchManifest,
    BatchResultSummary,
    SeverityCounts,
)
from .models import DocumentInspection
from .pipeline import PipelineError, load_pipeline_report
from .review_report import ReviewReportError, load_review_report
from .safe_persistence import atomic_write_text
from .storage import runtime_dir


class BatchResultError(RuntimeError):
    pass


class BatchNotFoundError(BatchResultError):
    pass


def _batch_dir() -> Path:
    return runtime_dir() / "batches"


def _batch_path(batch_id: UUID) -> Path:
    return _batch_dir() / f"{batch_id}.json"


def _latest_path() -> Path:
    return _batch_dir() / "latest.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _persist_manifest(manifest: BatchManifest, *, mark_latest: bool) -> None:
    root = _batch_dir()
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_batch_path(manifest.batch_id), manifest.model_dump_json(indent=2))
    # Creating an empty batch must not hide the most recent useful batch. Only
    # a batch that actually owns at least one persisted Job becomes "recent".
    if mark_latest:
        atomic_write_text(
            _latest_path(),
            json.dumps({"batch_id": str(manifest.batch_id)}, ensure_ascii=False, indent=2),
        )


def create_batch() -> BatchManifest:
    manifest = BatchManifest(batch_id=uuid4(), created_at=_now(), job_ids=[])
    _persist_manifest(manifest, mark_latest=False)
    return manifest


def load_batch(batch_id: UUID) -> BatchManifest:
    path = _batch_path(batch_id)
    if not path.exists():
        raise BatchNotFoundError(f"Batch {batch_id} does not exist.")
    try:
        return BatchManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise BatchResultError(f"Persisted batch manifest is invalid for {batch_id}.") from exc


def latest_batch() -> BatchManifest | None:
    path = _latest_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = load_batch(UUID(str(payload["batch_id"])))
        return manifest if manifest.job_ids else None
    except (OSError, ValueError, TypeError, KeyError, BatchResultError):
        return None


def register_batch_job(batch_id: UUID, job_id: UUID) -> BatchManifest:
    manifest = load_batch(batch_id)
    document_path = runtime_dir() / "jobs" / str(job_id) / "document.json"
    if not document_path.exists():
        raise FileNotFoundError(f"Document job {job_id} does not exist.")
    if job_id not in manifest.job_ids:
        manifest.job_ids.append(job_id)
    # Registration is idempotent, but every successful registration refreshes
    # the recent pointer so an older/empty batch can never displace real work.
    _persist_manifest(manifest, mark_latest=True)
    return manifest


def _document(job_id: UUID) -> DocumentInspection:
    # Batch/result reads are strictly non-mutating. Do not call storage helpers
    # that mkdir job directories while inspecting a corrupted/stale manifest.
    job_dir = runtime_dir() / "jobs" / str(job_id)
    document_path = job_dir / "document.json"
    evidence_path = job_dir / "evidence.json"
    try:
        payload = json.loads(document_path.read_text(encoding="utf-8"))
        pages = json.loads(evidence_path.read_text(encoding="utf-8"))
        return DocumentInspection.model_validate({**payload, "pages": pages})
    except Exception as exc:
        raise BatchResultError(f"Document metadata is invalid for job {job_id}.") from exc


def _severity_counts(review) -> SeverityCounts:
    counts = SeverityCounts()
    for finding in review.primary_findings:
        severity = finding.severity.value.lower()
        if hasattr(counts, severity):
            setattr(counts, severity, getattr(counts, severity) + 1)
    return counts


def _priority(counts: SeverityCounts, *, human_review: bool, omissions: int, material: bool) -> int:
    return (
        (1000 if human_review else 0)
        + counts.critical * 200
        + counts.high * 50
        + counts.medium * 10
        + counts.low * 2
        + omissions * 25
        + (100 if material else 0)
    )


def _summarize_job(job_id: UUID) -> BatchJobResult:
    try:
        document = _document(job_id)
    except BatchResultError:
        return BatchJobResult(
            job_id=job_id,
            filename=f"Job {str(job_id)[:8]}",
            state=BatchJobState.INVALID,
            progress_percent=0,
            failure_code="DOCUMENT_METADATA_INVALID",
            failure_detail="本地文档元数据无法安全读取。",
            needs_attention=True,
            priority_rank=5000,
        )

    try:
        pipeline = load_pipeline_report(job_id)
    except (PipelineError, FileNotFoundError):
        return BatchJobResult(
            job_id=job_id,
            filename=document.filename,
            state=BatchJobState.PROCESSING,
            progress_percent=0,
            pipeline_status=None,
            failure_code="PIPELINE_NOT_STARTED",
            failure_detail="文件已接收，但后台审计尚未启动或上次启动未留下有效状态。可从结果页重新启动。",
            needs_attention=True,
            priority_rank=2500,
        )

    status = pipeline.status.value
    if status == "FAILED":
        return BatchJobResult(
            job_id=job_id,
            filename=document.filename,
            state=BatchJobState.FAILED,
            progress_percent=pipeline.progress_percent,
            pipeline_status=status,
            failure_code=pipeline.failure_code,
            failure_detail=pipeline.failure_detail,
            needs_attention=True,
            priority_rank=4000,
        )
    if status == "CANCELLED":
        return BatchJobResult(
            job_id=job_id,
            filename=document.filename,
            state=BatchJobState.CANCELLED,
            progress_percent=pipeline.progress_percent,
            pipeline_status=status,
            failure_code=pipeline.failure_code,
            failure_detail=pipeline.failure_detail,
            needs_attention=False,
            priority_rank=2000,
        )
    if status in {
        "WAITING_CONFIGURATION",
        "WAITING_OPTIONAL_COMPONENT",
        "PAUSED_BEFORE_PROVIDER",
    }:
        return BatchJobResult(
            job_id=job_id,
            filename=document.filename,
            state=BatchJobState.WAITING,
            progress_percent=pipeline.progress_percent,
            pipeline_status=status,
            failure_code=pipeline.failure_code,
            failure_detail=pipeline.failure_detail,
            needs_attention=True,
            priority_rank=3000,
        )
    if status != "COMPLETE":
        return BatchJobResult(
            job_id=job_id,
            filename=document.filename,
            state=BatchJobState.PROCESSING,
            progress_percent=pipeline.progress_percent,
            pipeline_status=status,
        )

    try:
        review = load_review_report(job_id)
    except (FileNotFoundError, ReviewReportError):
        return BatchJobResult(
            job_id=job_id,
            filename=document.filename,
            state=BatchJobState.INVALID,
            progress_percent=100,
            pipeline_status=status,
            failure_code="REVIEW_REPORT_INVALID",
            failure_detail="审计流水线已完成，但复核报告无法安全读取。",
            needs_attention=True,
            priority_rank=4500,
        )

    counts = _severity_counts(review)
    human_review = review.final_state.value == "HUMAN_REVIEW_REQUIRED"
    material = review.comparison.overall_state.value in {
        "MATERIAL_DISAGREEMENT",
        "REQUIRES_MORE_EVIDENCE",
    }
    omissions = len(review.possible_primary_omissions)
    rank = _priority(counts, human_review=human_review, omissions=omissions, material=material)
    attention = bool(human_review or counts.critical or counts.high or material or omissions)
    return BatchJobResult(
        job_id=job_id,
        filename=document.filename,
        state=BatchJobState.COMPLETE,
        progress_percent=100,
        pipeline_status=status,
        final_review_state=review.final_state.value,
        human_review_required=human_review,
        finding_counts=counts,
        possible_omissions=omissions,
        material_disagreement=material,
        needs_attention=attention,
        priority_rank=rank,
    )


def summarize_batch(batch_id: UUID) -> BatchResultSummary:
    manifest = load_batch(batch_id)
    jobs = [_summarize_job(job_id) for job_id in manifest.job_ids]
    jobs.sort(key=lambda item: (-item.priority_rank, item.filename.lower(), str(item.job_id)))
    return BatchResultSummary(
        batch_id=manifest.batch_id,
        created_at=manifest.created_at,
        jobs=jobs,
        total_jobs=len(jobs),
        complete_jobs=sum(item.state == BatchJobState.COMPLETE for item in jobs),
        waiting_jobs=sum(item.state == BatchJobState.WAITING for item in jobs),
        cancelled_jobs=sum(item.state == BatchJobState.CANCELLED for item in jobs),
        failed_jobs=sum(item.state in {BatchJobState.FAILED, BatchJobState.INVALID} for item in jobs),
        human_review_required_jobs=sum(item.human_review_required for item in jobs),
        processing_jobs=sum(item.state == BatchJobState.PROCESSING for item in jobs),
    )


def summarize_latest_batch() -> BatchResultSummary | None:
    manifest = latest_batch()
    return summarize_batch(manifest.batch_id) if manifest is not None else None
