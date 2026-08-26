from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .job_architecture import JobArchitectureError, resolve_job_architecture
from .job_history_models import JobDeleteState, JobHistoryIntegrity, JobHistoryItem, JobHistoryPage
from .pipeline_models import PipelineReport, PipelineStatus
from .storage import runtime_dir

_TERMINAL_STATUSES = {
    PipelineStatus.COMPLETE,
    PipelineStatus.FAILED,
    PipelineStatus.CANCELLED,
}


class JobHistoryError(RuntimeError):
    pass


def _job_roots(root: Path, job_id: UUID) -> tuple[Path, ...]:
    value = str(job_id)
    return (
        root / "jobs" / value,
        root / "uploads" / value,
        root / "rendered" / value,
        root / "exports" / value,
    )


def _safe_tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_symlink():
        raise JobHistoryError(f"Job storage root must not be a symlink: {path}")
    if path.is_file():
        return path.stat().st_size

    total = 0
    for current, dirs, files in os.walk(path, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
        for name in files:
            item = current_path / name
            if item.is_symlink():
                continue
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
    return total


def _latest_mtime(paths: tuple[Path, ...]) -> datetime | None:
    latest: float | None = None
    for root in paths:
        if not root.exists() or root.is_symlink():
            continue
        candidates = [root]
        if root.is_dir():
            for current, dirs, files in os.walk(root, followlinks=False):
                current_path = Path(current)
                dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
                candidates.extend(current_path / name for name in files)
        for item in candidates:
            try:
                stamp = item.stat().st_mtime
            except OSError:
                continue
            latest = stamp if latest is None else max(latest, stamp)
    return None if latest is None else datetime.fromtimestamp(latest, tz=timezone.utc)


def _document_metadata(job_dir: Path) -> tuple[str | None, str | None, str | None]:
    path = job_dir / "document.json"
    if not path.is_file():
        return None, None, "document.json is missing."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None, "document.json is invalid."
    filename = payload.get("filename")
    document_kind = payload.get("document_kind")
    if not isinstance(filename, str) or not filename.strip():
        filename = None
    if not isinstance(document_kind, str) or not document_kind.strip():
        document_kind = None
    return filename, document_kind, None


def _pipeline(job_id: UUID, job_dir: Path) -> tuple[PipelineReport | None, str | None]:
    path = job_dir / "pipeline.json"
    if not path.is_file():
        return None, "pipeline.json is missing."
    try:
        report = PipelineReport.model_validate_json(path.read_bytes())
    except (OSError, ValidationError):
        return None, "pipeline.json is invalid."
    if report.job_id != job_id:
        return None, "pipeline.json belongs to a different job ID."
    return report, None


def _history_item(root: Path, job_id: UUID) -> JobHistoryItem:
    roots = _job_roots(root, job_id)
    job_dir = roots[0]
    warning_parts: list[str] = []
    integrity = JobHistoryIntegrity.OK

    try:
        storage_bytes = sum(_safe_tree_bytes(path) for path in roots)
    except JobHistoryError as exc:
        storage_bytes = 0
        integrity = JobHistoryIntegrity.INVALID
        warning_parts.append(str(exc))

    filename, document_kind, document_warning = _document_metadata(job_dir)
    if document_warning:
        integrity = JobHistoryIntegrity.PARTIAL if integrity == JobHistoryIntegrity.OK else integrity
        warning_parts.append(document_warning)

    pipeline, pipeline_warning = _pipeline(job_id, job_dir)
    if pipeline_warning:
        integrity = JobHistoryIntegrity.PARTIAL if integrity == JobHistoryIntegrity.OK else integrity
        warning_parts.append(pipeline_warning)

    architecture: str | None = None
    try:
        architecture = resolve_job_architecture(job_id).architecture.value
    except (FileNotFoundError, JobArchitectureError) as exc:
        integrity = JobHistoryIntegrity.INVALID if pipeline is not None else JobHistoryIntegrity.PARTIAL
        warning_parts.append(str(exc))

    if pipeline is not None:
        terminal = pipeline.status in _TERMINAL_STATUSES
        pipeline_status = pipeline.status.value
        progress_percent = pipeline.progress_percent
        started_at = pipeline.started_at
        updated_at = max(
            [value for value in (pipeline.updated_at, _latest_mtime(roots)) if value is not None],
            default=None,
        )
        completed_at = pipeline.completed_at
    else:
        terminal = False
        pipeline_status = None
        progress_percent = None
        started_at = None
        updated_at = _latest_mtime(roots)
        completed_at = None

    if integrity == JobHistoryIntegrity.INVALID:
        delete_state = JobDeleteState.INVALID
        delete_reason = "任务目录或关键产物异常，需要先人工检查。"
        can_delete = False
    elif pipeline is None:
        delete_state = JobDeleteState.READY
        delete_reason = "未形成流水线的上传残留，可直接清理。"
        can_delete = True
    elif terminal:
        delete_state = JobDeleteState.READY
        delete_reason = "任务已结束，可直接清理。"
        can_delete = True
    else:
        delete_state = JobDeleteState.NEEDS_CANCEL
        delete_reason = "任务尚未结束，删除前会先请求停止流水线。"
        can_delete = True

    return JobHistoryItem(
        job_id=job_id,
        filename=filename,
        document_kind=document_kind,
        architecture=architecture,
        pipeline_status=pipeline_status,
        progress_percent=progress_percent,
        started_at=started_at,
        updated_at=updated_at,
        completed_at=completed_at,
        integrity=integrity,
        terminal=terminal,
        can_delete=can_delete,
        delete_state=delete_state,
        delete_reason=delete_reason,
        selected_delete_hint="删除将清理该合同的本机任务、上传、渲染和导出文件；共享法律库不会被删除。",
        storage_bytes=storage_bytes,
        warning=" ".join(warning_parts) if warning_parts else None,
    )


def _discover_job_ids(root: Path) -> set[UUID]:
    result: set[UUID] = set()
    # Exports are job-owned but are not an authoritative source of job identity.
    # A stray export without jobs/uploads/rendered must not resurrect a deleted Job.
    for category in ("jobs", "uploads", "rendered"):
        parent = root / category
        if not parent.is_dir() or parent.is_symlink():
            continue
        for child in parent.iterdir():
            if not child.is_dir() or child.is_symlink():
                continue
            try:
                result.add(UUID(child.name))
            except ValueError:
                continue
    return result


def list_job_history(*, offset: int = 0, limit: int = 50) -> JobHistoryPage:
    if offset < 0:
        raise JobHistoryError("History offset must be non-negative.")
    if not 1 <= limit <= 200:
        raise JobHistoryError("History limit must be between 1 and 200.")

    root = runtime_dir()
    items = [_history_item(root, job_id) for job_id in _discover_job_ids(root)]
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda item: (item.updated_at or item.started_at or minimum, str(item.job_id)), reverse=True)
    return JobHistoryPage(
        total_count=len(items),
        offset=offset,
        limit=limit,
        items=items[offset : offset + limit],
    )


def get_job_history(job_id: UUID) -> JobHistoryItem:
    root = runtime_dir()
    if job_id not in _discover_job_ids(root):
        raise FileNotFoundError(f"No local Law-Rag job exists for {job_id}.")
    return _history_item(root, job_id)
