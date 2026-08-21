from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from .batch_results_models import BatchManifest
from .job_history import get_job_history, list_job_history
from .safe_persistence import atomic_write_text
from .storage import runtime_dir
from .storage_management_models import (
    CleanupTransaction,
    CleanupTransactionState,
    JobCleanupResult,
    StorageSummary,
)


class StorageManagementError(RuntimeError):
    pass


class JobCleanupNotAllowed(StorageManagementError):
    pass


# Stage 18.2 report exports are job-private data and must move through the same
# tombstone transaction as jobs/uploads/rendered. Shared runtime/legal is
# deliberately absent from this list.
_JOB_CATEGORIES = ("jobs", "uploads", "rendered", "exports")


def _root() -> Path:
    return runtime_dir()


def _cleanup_root(root: Path) -> Path:
    return root / "cleanup"


def _transactions_root(root: Path) -> Path:
    return _cleanup_root(root) / "transactions"


def _trash_root(root: Path) -> Path:
    return _cleanup_root(root) / "trash"


def _transaction_path(root: Path, cleanup_id: UUID) -> Path:
    return _transactions_root(root) / f"{cleanup_id}.json"


def _transaction_trash(root: Path, cleanup_id: UUID) -> Path:
    return _trash_root(root) / str(cleanup_id)


def _job_roots(root: Path, job_id: UUID) -> dict[str, Path]:
    value = str(job_id)
    return {category: root / category / value for category in _JOB_CATEGORIES}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_bytes(path: Path) -> int:
    if not path.exists() or path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
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


def _persist_transaction(root: Path, transaction: CleanupTransaction) -> None:
    path = _transaction_path(root, transaction.cleanup_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, transaction.model_dump_json(indent=2))


def _load_transaction(path: Path) -> CleanupTransaction:
    if path.is_symlink():
        raise StorageManagementError(f"Cleanup transaction manifest must not be a symlink: {path}")
    try:
        return CleanupTransaction.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise StorageManagementError(f"Cleanup transaction is invalid: {path.name}") from exc


def _load_batch_manifests(root: Path) -> list[tuple[Path, BatchManifest]]:
    batches_root = root / "batches"
    if not batches_root.exists():
        return []
    if batches_root.is_symlink():
        raise StorageManagementError("runtime/batches must not be a symlink.")
    manifests: list[tuple[Path, BatchManifest]] = []
    for path in sorted(batches_root.glob("*.json")):
        if path.name == "latest.json":
            continue
        if path.is_symlink():
            raise StorageManagementError(f"Batch manifest must not be a symlink: {path.name}")
        try:
            manifest = BatchManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise StorageManagementError(
                f"Batch manifest {path.name} is invalid; refusing cleanup until batch history is repaired."
            ) from exc
        if path.stem != str(manifest.batch_id):
            raise StorageManagementError(
                f"Batch manifest filename does not match batch_id: {path.name}"
            )
        manifests.append((path, manifest))
    return manifests


def _validate_live_job_for_new_cleanup(root: Path, job_id: UUID) -> tuple[int, str]:
    item = get_job_history(job_id)
    if not item.can_delete or not item.terminal:
        raise JobCleanupNotAllowed(
            f"Job {job_id} is not a safely deletable terminal job (status={item.pipeline_status}, integrity={item.integrity.value})."
        )

    roots = _job_roots(root, job_id)
    for category, path in roots.items():
        if path.is_symlink():
            raise JobCleanupNotAllowed(
                f"Job-owned {category} root is a symlink; refusing cleanup for {job_id}."
            )

    pipeline_path = roots["jobs"] / "pipeline.json"
    if not pipeline_path.is_file() or pipeline_path.is_symlink():
        raise JobCleanupNotAllowed("A safely deletable job must retain a regular pipeline.json until cleanup begins.")

    _load_batch_manifests(root)
    return item.storage_bytes, _sha256(pipeline_path)


def _transaction_has_started(root: Path, transaction: CleanupTransaction) -> bool:
    trash = _transaction_trash(root, transaction.cleanup_id)
    if transaction.moved_roots:
        return True
    return any((trash / category).exists() for category in _JOB_CATEGORIES)


def _move_job_roots(root: Path, transaction: CleanupTransaction) -> CleanupTransaction:
    roots = _job_roots(root, transaction.job_id)
    trash = _transaction_trash(root, transaction.cleanup_id)
    trash.mkdir(parents=True, exist_ok=True)

    started = _transaction_has_started(root, transaction)
    if not started:
        _load_batch_manifests(root)
        item = get_job_history(transaction.job_id)
        if not item.can_delete or not item.terminal:
            raise JobCleanupNotAllowed(
                f"Job {transaction.job_id} changed state before cleanup started; transaction will not proceed."
            )
        pipeline = roots["jobs"] / "pipeline.json"
        if not pipeline.is_file() or pipeline.is_symlink() or _sha256(pipeline) != transaction.pipeline_sha256:
            raise JobCleanupNotAllowed(
                f"Job {transaction.job_id} pipeline changed before cleanup started; transaction will not proceed."
            )

    moved = set(transaction.moved_roots)
    for category, live in roots.items():
        destination = trash / category
        if live.is_symlink():
            raise StorageManagementError(
                f"Job-owned {category} root became a symlink during cleanup; refusing to follow it."
            )
        if destination.exists() and live.exists():
            raise StorageManagementError(
                f"Cleanup conflict for {transaction.job_id}: both live and tombstoned {category} roots exist."
            )
        if live.exists():
            os.replace(live, destination)
        if destination.exists():
            moved.add(category)

    transaction.moved_roots = sorted(moved)
    transaction.state = CleanupTransactionState.ROOTS_MOVED
    _persist_transaction(root, transaction)
    return transaction


def _persist_batch_manifest(path: Path, manifest: BatchManifest) -> None:
    atomic_write_text(path, manifest.model_dump_json(indent=2))


def _repair_latest_batch(root: Path, manifests: list[tuple[Path, BatchManifest]]) -> bool:
    batches_root = root / "batches"
    latest_path = batches_root / "latest.json"
    nonempty = [(path, manifest) for path, manifest in manifests if manifest.job_ids]

    current_id: UUID | None = None
    if latest_path.exists():
        if latest_path.is_symlink():
            raise StorageManagementError("runtime/batches/latest.json must not be a symlink.")
        try:
            payload = json.loads(latest_path.read_text(encoding="utf-8"))
            current_id = UUID(str(payload["batch_id"]))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            current_id = None

    if current_id is not None and any(manifest.batch_id == current_id for _, manifest in nonempty):
        return False

    if not nonempty:
        if latest_path.exists():
            latest_path.unlink()
            return True
        return current_id is not None

    chosen_path, chosen = max(
        nonempty,
        key=lambda pair: (pair[0].stat().st_mtime, pair[1].created_at, str(pair[1].batch_id)),
    )
    del chosen_path
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        latest_path,
        json.dumps({"batch_id": str(chosen.batch_id)}, ensure_ascii=False, indent=2),
    )
    return True


def _remove_batch_references(root: Path, job_id: UUID) -> tuple[int, bool]:
    manifests = _load_batch_manifests(root)
    updated = 0
    for path, manifest in manifests:
        if job_id not in manifest.job_ids:
            continue
        manifest.job_ids = [value for value in manifest.job_ids if value != job_id]
        _persist_batch_manifest(path, manifest)
        updated += 1

    persisted = _load_batch_manifests(root)
    latest_repaired = _repair_latest_batch(root, persisted)
    return updated, latest_repaired


def _purge_tombstone(root: Path, transaction: CleanupTransaction) -> None:
    trash = _transaction_trash(root, transaction.cleanup_id)
    if trash.is_symlink():
        raise StorageManagementError("Cleanup tombstone root must not be a symlink.")
    if trash.exists():
        shutil.rmtree(trash)
    transaction_path = _transaction_path(root, transaction.cleanup_id)
    if transaction_path.exists():
        if transaction_path.is_symlink():
            raise StorageManagementError("Cleanup transaction manifest must not be a symlink.")
        transaction_path.unlink()


def _finish_transaction(root: Path, transaction: CleanupTransaction) -> JobCleanupResult:
    transaction = _move_job_roots(root, transaction)
    updated, latest_repaired = _remove_batch_references(root, transaction.job_id)
    transaction.state = CleanupTransactionState.REFERENCES_UPDATED
    _persist_transaction(root, transaction)
    _purge_tombstone(root, transaction)
    return JobCleanupResult(
        job_id=transaction.job_id,
        deleted=True,
        reclaimed_bytes=transaction.original_storage_bytes,
        batch_manifests_updated=updated,
        latest_batch_repaired=latest_repaired,
    )


def delete_job_storage(job_id: UUID, *, confirm_job_id: UUID) -> JobCleanupResult:
    if confirm_job_id != job_id:
        raise JobCleanupNotAllowed("Cleanup confirmation job_id does not match the requested job.")

    root = _root()
    storage_bytes, pipeline_sha256 = _validate_live_job_for_new_cleanup(root, job_id)
    transaction = CleanupTransaction(
        cleanup_id=uuid4(),
        job_id=job_id,
        created_at=datetime.now(timezone.utc),
        original_storage_bytes=storage_bytes,
        pipeline_sha256=pipeline_sha256,
    )
    _persist_transaction(root, transaction)
    return _finish_transaction(root, transaction)


def reconcile_storage_cleanup_transactions() -> tuple[int, list[str]]:
    root = _root()
    transaction_root = _transactions_root(root)
    if not transaction_root.exists():
        return 0, []
    if transaction_root.is_symlink():
        return 0, ["runtime/cleanup/transactions is a symlink; automatic cleanup recovery was skipped."]

    completed = 0
    warnings: list[str] = []
    for path in sorted(transaction_root.glob("*.json")):
        try:
            transaction = _load_transaction(path)
            _finish_transaction(root, transaction)
        except (StorageManagementError, JobCleanupNotAllowed, FileNotFoundError) as exc:
            warnings.append(f"Cleanup recovery {path.name} requires attention: {exc}")
        else:
            completed += 1
    return completed, warnings


def storage_summary() -> StorageSummary:
    root = _root()
    history = list_job_history(offset=0, limit=200)
    items = list(history.items)
    offset = len(items)
    while offset < history.total_count:
        page = list_job_history(offset=offset, limit=200)
        items.extend(page.items)
        offset += len(page.items)
        if not page.items:
            break

    # Job history storage includes reports under runtime/exports/<job_id>.
    jobs_bytes = sum(item.storage_bytes for item in items)
    batches_bytes = _tree_bytes(root / "batches")
    shared_legal_bytes = _tree_bytes(root / "legal")
    cleanup_bytes = _tree_bytes(root / "cleanup")
    total_runtime_bytes = _tree_bytes(root)
    known = jobs_bytes + batches_bytes + shared_legal_bytes + cleanup_bytes
    other_runtime_bytes = max(0, total_runtime_bytes - known)
    warnings: list[str] = []
    if cleanup_bytes:
        warnings.append(
            "Cleanup transaction/tombstone bytes are present; startup recovery will retry incomplete safe cleanup transactions."
        )
    if other_runtime_bytes and (root / "exports").exists():
        warnings.append(
            "Some runtime bytes are not attached to discoverable Jobs; orphaned exports or other runtime data may require inspection."
        )

    return StorageSummary(
        job_count=len(items),
        terminal_deletable_job_count=sum(1 for item in items if item.can_delete),
        active_or_protected_job_count=sum(1 for item in items if not item.can_delete),
        jobs_bytes=jobs_bytes,
        batches_bytes=batches_bytes,
        shared_legal_bytes=shared_legal_bytes,
        cleanup_bytes=cleanup_bytes,
        other_runtime_bytes=other_runtime_bytes,
        total_runtime_bytes=total_runtime_bytes,
        warnings=warnings,
    )
