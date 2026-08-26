from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.job_history import get_job_history, list_job_history
from app.job_history_models import JobHistoryIntegrity
from app.main import app


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pipeline(job_id: UUID, *, status: str, updated_at: str, progress: int) -> dict:
    terminal = status in {"COMPLETE", "FAILED", "CANCELLED"}
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
        "updated_at": updated_at,
        "completed_at": updated_at if terminal else None,
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
                "finished_at": updated_at if terminal else None,
            },
        ],
    }


def _job(root: Path, job_id: UUID, *, filename: str, status: str, updated_at: str, progress: int) -> None:
    job_dir = root / "jobs" / str(job_id)
    _write_json(
        job_dir / "document.json",
        {
            "job_id": str(job_id),
            "filename": filename,
            "document_kind": "pdf",
        },
    )
    _write_json(job_dir / "pipeline.json", _pipeline(job_id, status=status, updated_at=updated_at, progress=progress))
    upload = root / "uploads" / str(job_id) / "source.pdf"
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"PDF-DATA")


def test_history_is_persistent_sorted_and_reports_job_owned_storage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    older = uuid4()
    newer = uuid4()
    _job(
        tmp_path,
        older,
        filename="older.pdf",
        status="COMPLETE",
        updated_at="2026-08-21T08:10:00+00:00",
        progress=100,
    )
    _job(
        tmp_path,
        newer,
        filename="newer.pdf",
        status="FAILED",
        updated_at="2026-08-21T08:20:00+00:00",
        progress=70,
    )
    (tmp_path / "rendered" / str(newer)).mkdir(parents=True)
    (tmp_path / "rendered" / str(newer) / "page-1.png").write_bytes(b"12345")

    page = list_job_history()

    assert page.total_count == 2
    assert [item.job_id for item in page.items] == [newer, older]
    assert page.items[0].filename == "newer.pdf"
    assert page.items[0].architecture == "ISSUE_V1"
    assert page.items[0].pipeline_status == "FAILED"
    assert page.items[0].terminal is True
    assert page.items[0].can_delete is True
    assert page.items[0].storage_bytes > 5


def test_running_job_is_visible_and_marked_for_cancel_before_delete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _job(
        tmp_path,
        job_id,
        filename="running.pdf",
        status="RUNNING",
        updated_at="2026-08-21T08:30:00+00:00",
        progress=55,
    )

    item = get_job_history(job_id)

    assert item.integrity == JobHistoryIntegrity.OK
    assert item.terminal is False
    assert item.can_delete is True
    assert item.delete_state.value == "NEEDS_CANCEL"
    assert item.progress_percent == 55


def test_upload_only_interrupted_job_remains_visible_as_partial(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    source = tmp_path / "uploads" / str(job_id) / "source.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"DOCX")

    item = get_job_history(job_id)

    assert item.job_id == job_id
    assert item.integrity == JobHistoryIntegrity.PARTIAL
    assert item.pipeline_status is None
    assert item.terminal is False
    assert item.can_delete is True
    assert item.delete_state.value == "READY"
    assert item.storage_bytes == 4
    assert "pipeline.json is missing" in (item.warning or "")


def test_history_pagination_and_non_uuid_directories_are_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    ids = [uuid4() for _ in range(3)]
    for index, job_id in enumerate(ids):
        _job(
            tmp_path,
            job_id,
            filename=f"{index}.pdf",
            status="COMPLETE",
            updated_at=f"2026-08-21T08:{10 + index:02d}:00+00:00",
            progress=100,
        )
    (tmp_path / "jobs" / "not-a-job").mkdir(parents=True)

    page = list_job_history(offset=1, limit=1)

    assert page.total_count == 3
    assert page.offset == 1
    assert page.limit == 1
    assert len(page.items) == 1


def test_history_api_reads_existing_jobs_without_provider_side_effects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _job(
        tmp_path,
        job_id,
        filename="api.pdf",
        status="COMPLETE",
        updated_at="2026-08-21T08:40:00+00:00",
        progress=100,
    )

    client = TestClient(app)
    response = client.get("/api/batches/history/jobs?limit=20")
    detail = client.get(f"/api/batches/history/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["total_count"] == 1
    assert response.json()["items"][0]["job_id"] == str(job_id)
    assert detail.status_code == 200
    assert detail.json()["filename"] == "api.pdf"
