from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.artifact_integrity import inspect_job_artifact_integrity
from app.artifact_integrity_models import ArtifactIntegrityState
from app.contract_models import CanonicalContract
from app.main import app

client = TestClient(app)


def _job_dir(root: Path, job_id) -> Path:
    path = root / "jobs" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _source(root: Path, job_id) -> Path:
    path = root / "uploads" / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    source = path / "source.pdf"
    source.write_bytes(b"%PDF-1.4 fictional integrity fixture")
    return source


def _artifact(report, name: str):
    return next(item for item in report.artifacts if item.artifact == name)


def test_corrupt_json_is_explicit_and_inspection_does_not_rewrite_it(tmp_path: Path, monkeypatch) -> None:
    job_id = uuid4()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    _source(tmp_path, job_id)
    job_dir = _job_dir(tmp_path, job_id)
    broken = job_dir / "ai-audit.json"
    broken.write_bytes(b'{"private":"unterminated"')
    before = broken.read_bytes()

    report = inspect_job_artifact_integrity(job_id)

    assert _artifact(report, "ai-audit.json").state == ArtifactIntegrityState.CORRUPT
    assert report.all_present_artifacts_valid is False
    assert report.action_required is True
    assert broken.read_bytes() == before
    assert "unterminated" not in report.model_dump_json(), "diagnostics must not echo artifact payloads"


def test_artifact_job_id_mismatch_is_rejected_without_renaming_or_repair(tmp_path: Path, monkeypatch) -> None:
    requested_job = uuid4()
    wrong_job = uuid4()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    _source(tmp_path, requested_job)
    job_dir = _job_dir(tmp_path, requested_job)
    contract_path = job_dir / "contract.json"
    contract = CanonicalContract(
        job_id=wrong_job,
        filename="fictional.pdf",
        source_fingerprint="source-fingerprint",
        evidence_unit_count=0,
    )
    contract_path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    before = contract_path.read_bytes()

    report = inspect_job_artifact_integrity(requested_job)

    assert _artifact(report, "contract.json").state == ArtifactIntegrityState.MISMATCH
    assert report.action_required is True
    assert contract_path.read_bytes() == before


def test_missing_source_for_existing_artifact_is_action_required_not_success(tmp_path: Path, monkeypatch) -> None:
    job_id = uuid4()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_dir = _job_dir(tmp_path, job_id)
    contract = CanonicalContract(
        job_id=job_id,
        filename="missing-source.pdf",
        source_fingerprint="source-fingerprint",
        evidence_unit_count=0,
    )
    (job_dir / "contract.json").write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    report = inspect_job_artifact_integrity(job_id)

    assert report.source_available is False
    assert _artifact(report, "source.*").state == ArtifactIntegrityState.MISSING
    assert _artifact(report, "contract.json").state == ArtifactIntegrityState.READY
    assert report.action_required is True


def test_integrity_api_unknown_job_returns_404_without_creating_directories(tmp_path: Path, monkeypatch) -> None:
    job_id = uuid4()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))

    response = client.get(f"/api/runtime/jobs/{job_id}/integrity")

    assert response.status_code == 404
    assert not (tmp_path / "jobs" / str(job_id)).exists()
    assert not (tmp_path / "uploads" / str(job_id)).exists()
