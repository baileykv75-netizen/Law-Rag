from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.batch_results import create_batch, register_batch_job, summarize_batch
from app.batch_results_models import BatchJobState
from app.models import DocumentInspection, DocumentKind, DocumentRoute, PageEvidence, PageRoute, SourceMethod
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStageRecord, PipelineStageState, PipelineStatus
from app.safe_persistence import atomic_write_text

JOB_COUNT = 10
WRITES_PER_JOB = 35
SUMMARY_READS_PER_THREAD = 80
READER_THREADS = 5


def _write_document(root: Path, job_id: UUID, index: int) -> None:
    job_dir = root / "jobs" / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    page = PageEvidence(
        evidence_id=f"evidence:{job_id}:p1",
        page_number=1,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text=f"synthetic tester2 contract {index}",
        character_count=28,
        non_whitespace_count=25,
        meaningful_ratio=1.0,
        suspicious_character_count=0,
        route=PageRoute.NATIVE_TEXT_USABLE,
        route_reason="tester2 stress fixture",
        source_locator="page:1",
    )
    document = DocumentInspection(
        job_id=job_id,
        filename=f"tester2-stress-{index:02d}.pdf",
        media_type="application/pdf",
        document_kind=DocumentKind.PDF,
        page_count=1,
        route=DocumentRoute.NATIVE_TEXT,
        native_text_pages=1,
        ocr_required_pages=0,
        pages=[page],
    )
    payload = document.model_dump(mode="json")
    payload.pop("pages")
    atomic_write_text(job_dir / "document.json", json.dumps(payload, ensure_ascii=False))
    atomic_write_text(
        job_dir / "evidence.json",
        json.dumps([page.model_dump(mode="json")], ensure_ascii=False),
    )


def _pipeline(job_id: UUID, iteration: int) -> PipelineReport:
    now = datetime.now(timezone.utc)
    waiting = iteration % 7 == 3
    status = PipelineStatus.WAITING_WORKER if waiting else PipelineStatus.RUNNING
    current_stage = PipelineStage.RULES if iteration < WRITES_PER_JOB // 2 else PipelineStage.AUDIT_PLAN
    progress = 42 if current_stage == PipelineStage.RULES else 55
    return PipelineReport(
        job_id=job_id,
        status=status,
        current_stage=current_stage,
        progress_percent=progress,
        as_of=date(2026, 8, 24),
        started_at=now,
        updated_at=now,
        stages=[
            PipelineStageRecord(
                stage=PipelineStage.INGEST,
                state=PipelineStageState.COMPLETE,
                label="文件已接收",
                progress_percent=10,
            ),
            PipelineStageRecord(
                stage=PipelineStage.OCR,
                state=PipelineStageState.SKIPPED,
                label="识别扫描文本",
                progress_percent=25,
            ),
            PipelineStageRecord(
                stage=PipelineStage.STRUCTURE,
                state=PipelineStageState.COMPLETE,
                label="整理合同结构",
                progress_percent=38,
            ),
            PipelineStageRecord(
                stage=PipelineStage.RULES,
                state=PipelineStageState.RUNNING if current_stage == PipelineStage.RULES else PipelineStageState.COMPLETE,
                label="执行确定性检查",
                progress_percent=48,
            ),
            PipelineStageRecord(
                stage=PipelineStage.AUDIT_PLAN,
                state=(PipelineStageState.WAITING if waiting else PipelineStageState.RUNNING)
                if current_stage == PipelineStage.AUDIT_PLAN
                else PipelineStageState.PENDING,
                label="制定完整审计计划",
                progress_percent=58,
            ),
        ],
    )


def test_ten_job_batch_survives_concurrent_pipeline_writes_and_result_polling(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    batch = create_batch()
    job_ids = [uuid4() for _ in range(JOB_COUNT)]

    for index, job_id in enumerate(job_ids, start=1):
        _write_document(tmp_path, job_id, index)
        atomic_write_text(
            tmp_path / "jobs" / str(job_id) / "pipeline.json",
            _pipeline(job_id, 0).model_dump_json(),
        )
        register_batch_job(batch.batch_id, job_id)

    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def record_error(exc: BaseException) -> None:
        with errors_lock:
            errors.append(exc)

    def writer(job_id: UUID) -> None:
        try:
            path = tmp_path / "jobs" / str(job_id) / "pipeline.json"
            for iteration in range(1, WRITES_PER_JOB + 1):
                atomic_write_text(path, _pipeline(job_id, iteration).model_dump_json(), base_delay_seconds=0.001)
        except BaseException as exc:  # pragma: no cover - asserted below
            record_error(exc)

    def reader() -> None:
        try:
            for _ in range(SUMMARY_READS_PER_THREAD):
                summary = summarize_batch(batch.batch_id)
                assert summary.total_jobs == JOB_COUNT
                assert len(summary.jobs) == JOB_COUNT
                assert all(item.state in {BatchJobState.PROCESSING, BatchJobState.WAITING} for item in summary.jobs)
                assert all(item.state not in {BatchJobState.FAILED, BatchJobState.INVALID} for item in summary.jobs)
        except BaseException as exc:  # pragma: no cover - asserted below
            record_error(exc)

    threads = [threading.Thread(target=writer, args=(job_id,)) for job_id in job_ids]
    threads += [threading.Thread(target=reader) for _ in range(READER_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []

    final = summarize_batch(batch.batch_id)
    assert final.total_jobs == JOB_COUNT
    assert final.failed_jobs == 0
    assert all(item.state != BatchJobState.INVALID for item in final.jobs)
