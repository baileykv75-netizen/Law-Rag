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


def job_rendered_dir(job_id: UUID) -> Path:
    path = runtime_dir() / "rendered" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def legal_runtime_dir() -> Path:
    path = runtime_dir() / "legal"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legal_db_path() -> Path:
    configured = os.getenv("LAW_RAG_LEGAL_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    return legal_runtime_dir() / "legal.db"


def legal_import_reports_dir() -> Path:
    path = legal_runtime_dir() / "import_reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legal_last_import_report_path() -> Path:
    return legal_import_reports_dir() / "last-import-report.json"


def job_document_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "document.json"


def job_evidence_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "evidence.json"


def job_ocr_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "ocr.json"


def job_contract_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "contract.json"


def job_audit_rules_path(job_id: UUID) -> Path:
    return job_output_dir(job_id) / "audit-rules.json"


def find_source_path(job_id: UUID) -> Path:
    upload_dir = runtime_dir() / "uploads" / str(job_id)
    candidates = sorted(upload_dir.glob("source.*"))
    if len(candidates) != 1:
        raise FileNotFoundError(f"Expected one source file for job {job_id}.")
    return candidates[0]
