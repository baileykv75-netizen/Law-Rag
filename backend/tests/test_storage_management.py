from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.storage_management as storage_management
from app.batch_results_models import BatchManifest
from app.main import app
from app.storage_management import (
    JobCleanupNotAllowed,
    delete_jobs_storage_bulk,
    delete_job_storage,
    reconcile_storage_cleanup_transactions,
    storage_summary,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pipeline(job_id: UUID, *, status: str, progress: int = 100) -> dict:
    terminal = status in {"COMPLETE", "FAILED", "CANCELLED"}
    updated = "2026-08-21T09:00:00+00:00"
    return {
        "schema_version": "1.3.0",
        "engine_version": "stage13g-4-1.0.0",
        "job_id": str(job_id),
        "status": status,
        "current_stage": "COMPLETE" if status == "COMPLETE" else "ISSUE_PRIMARY_AUDIT",
        "progress_percent": progress,
        "as_of": "2026-08-21",
        "use_semantic": False,
        "started_at": "2026-08-21T08:00:00+00:00",
        "updated_at": updated,
        "completed_at": updated if terminal else None,
        "failure_code": "TEST_FAILURE" if status == "FAILED" else None,
        "failure_detail": None,
        "stages": [
            {
                "stage": "AUDIT_PLAN",
                "state": "COMPLETE",
                "label": "Audit plan",
                "progress_percent": 40,
                "detail": "",
                "reused_existing_artifact": False,
                "started_at": "2026-08-21T08:01:00+00:00",
                "finished_at": "2026-08-21T08:02:00+00:00",
            },
            {
                "stage": "ISSUE_PRIMARY_AUDIT",
                "state": "COMPLETE" if terminal else "RUNNING",
                "label": "Issue primary audit",
                "progress_percent": progress,
                "detail": "",
                "reused_existing_artifact": False,
                "started_at": "2026-08-21T08:03:00+00:00",
                "finished_at": updated if terminal else None,
            },
        ],
    }


def _job(root: Path, job_id: UUID, *, status: str = "COMPLETE") -> None:
    job_dir = root / "jobs" / str(job_id)
    _write_json(
        job_dir / "document.json",
        {"job_id": str(job_id), "filename": f"{job_id}.pdf", "document_kind": "pdf"},
    )
    _write_json(job_dir / "pipeline.json", _pipeline(job_id, status=status, progress=100 if status != "RUNNING" else 50))
    upload = root / "uploads" / str(job_id) / "source.pdf"
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"PDF-DATA")
    rendered = root / "rendered" / str(job_id) / "page-1.png"
    rendered.parent.mkdir(parents=True, exist_ok=True)
    rendered.write_bytes(b"PNG-DATA")


def _batch(root: Path, batch_id: UUID, job_ids: list[UUID], *, latest: bool = False) -> None:
    manifest = BatchManifest(batch_id=batch_id, created_at=datetime.now(timezone.utc), job_ids=job_ids)
    path = root / "batches" / f"{batch_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    if latest:
        _write_json(root / "batches" / "latest.json", {"batch_id": str(batch_id)})


def test_delete_terminal_job_moves_all_private_roots_and_repairs_batch_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    retained = uuid4()
    batch_id = uuid4()
    _job(tmp_path, job_id)
    _job(tmp_path, retained)
    _batch(tmp_path, batch_id, [job_id, retained], latest=True)
    legal = tmp_path / "legal" / "legal.db"
    legal.parent.mkdir(parents=True)
    legal.write_bytes(b"SHARED-LEGAL")

    before = storage_summary()
    result = delete_job_storage(job_id, confirm_job_id=job_id)
    after = storage_summary()

    assert result.deleted is True
    assert result.reclaimed_bytes > 0
    assert result.batch_manifests_updated == 1
    assert result.shared_legal_untouched is True
    assert not (tmp_path / "jobs" / str(job_id)).exists()
    assert not (tmp_path / "uploads" / str(job_id)).exists()
    assert not (tmp_path / "rendered" / str(job_id)).exists()
    assert legal.read_bytes() == b"SHARED-LEGAL"
    manifest = BatchManifest.model_validate_json((tmp_path / "batches" / f"{batch_id}.json").read_text(encoding="utf-8"))
    assert manifest.job_ids == [retained]
    assert before.job_count == 2
    assert after.job_count == 1
    assert after.jobs_bytes < before.jobs_bytes
    assert not (tmp_path / "cleanup" / "trash").exists() or not any((tmp_path / "cleanup" / "trash").iterdir())


def test_delete_requires_exact_job_id_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _job(tmp_path, job_id)

    with pytest.raises(JobCleanupNotAllowed, match="confirmation job_id"):
        delete_job_storage(job_id, confirm_job_id=uuid4())

    assert (tmp_path / "jobs" / str(job_id) / "pipeline.json").exists()


def test_running_job_requires_force_safe_cleanup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _job(tmp_path, job_id, status="RUNNING")

    with pytest.raises(JobCleanupNotAllowed, match="not terminal"):
        delete_job_storage(job_id, confirm_job_id=job_id)

    assert (tmp_path / "jobs" / str(job_id)).exists()


def test_bulk_delete_cancels_and_deletes_running_jobs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    complete = uuid4()
    running = uuid4()
    batch_id = uuid4()
    _job(tmp_path, complete)
    _job(tmp_path, running, status="RUNNING")
    _batch(tmp_path, batch_id, [complete, running], latest=True)

    result = delete_jobs_storage_bulk([complete, running], confirm=True)

    assert len(result.deleted) == 2
    assert result.skipped == []
    assert result.reclaimed_bytes > 0
    assert not (tmp_path / "jobs" / str(complete)).exists()
    assert not (tmp_path / "jobs" / str(running)).exists()
    manifest = BatchManifest.model_validate_json((tmp_path / "batches" / f"{batch_id}.json").read_text(encoding="utf-8"))
    assert manifest.job_ids == []


def test_cleanup_recovery_finishes_after_crash_between_tombstone_and_reference_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    batch_id = uuid4()
    _job(tmp_path, job_id)
    _batch(tmp_path, batch_id, [job_id], latest=True)

    original = storage_management._remove_batch_references

    def crash_once(root: Path, cleanup_job_id: UUID):
        del root, cleanup_job_id
        raise storage_management.StorageManagementError("simulated crash")

    monkeypatch.setattr(storage_management, "_remove_batch_references", crash_once)
    with pytest.raises(storage_management.StorageManagementError, match="simulated crash"):
        delete_job_storage(job_id, confirm_job_id=job_id)

    assert not (tmp_path / "jobs" / str(job_id)).exists()
    transaction_files = list((tmp_path / "cleanup" / "transactions").glob("*.json"))
    assert len(transaction_files) == 1
    assert list((tmp_path / "cleanup" / "trash").iterdir())

    monkeypatch.setattr(storage_management, "_remove_batch_references", original)
    completed, warnings = reconcile_storage_cleanup_transactions()

    assert completed == 1
    assert warnings == []
    manifest = BatchManifest.model_validate_json((tmp_path / "batches" / f"{batch_id}.json").read_text(encoding="utf-8"))
    assert manifest.job_ids == []
    assert not (tmp_path / "batches" / "latest.json").exists()
    assert not list((tmp_path / "cleanup" / "transactions").glob("*.json"))


def test_symlink_job_root_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _job(tmp_path, job_id)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("KEEP", encoding="utf-8")
    upload_root = tmp_path / "uploads" / str(job_id)
    for child in upload_root.iterdir():
        child.unlink()
    upload_root.rmdir()
    try:
        upload_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable in this session.")
        raise

    with pytest.raises(JobCleanupNotAllowed):
        delete_job_storage(job_id, confirm_job_id=job_id)

    assert (outside / "keep.txt").read_text(encoding="utf-8") == "KEEP"
    assert (tmp_path / "jobs" / str(job_id) / "pipeline.json").exists()


def test_storage_api_and_delete_api_use_explicit_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _job(tmp_path, job_id)
    client = TestClient(app)

    summary = client.get("/api/batches/history/storage")
    mismatch = client.request(
        "DELETE",
        f"/api/batches/history/jobs/{job_id}",
        json={"confirm_job_id": str(uuid4())},
    )
    deleted = client.request(
        "DELETE",
        f"/api/batches/history/jobs/{job_id}",
        json={"confirm_job_id": str(job_id)},
    )

    assert summary.status_code == 200
    assert summary.json()["job_count"] == 1
    assert mismatch.status_code == 409
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_bulk_delete_api_does_not_require_typed_job_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    first = uuid4()
    second = uuid4()
    _job(tmp_path, first)
    _job(tmp_path, second, status="RUNNING")
    client = TestClient(app)

    deleted = client.post(
        "/api/batches/history/jobs/delete",
        json={"job_ids": [str(first), str(second)], "mode": "force_safe", "confirm": True},
    )

    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert len(body["deleted"]) == 2
    assert body["skipped"] == []
