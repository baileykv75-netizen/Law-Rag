from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"


def runtime_dir() -> Path:
    configured = os.getenv("LAW_RAG_RUNTIME_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_RUNTIME_DIR


def job_upload_dir(job_id: UUID) -> Path:
    path = runtime_dir() / "uploads" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_output_dir(job_id: UUID) -> Path:
    path = runtime_dir() / "jobs" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_document_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "document.json"


def job_evidence_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "evidence.json"
