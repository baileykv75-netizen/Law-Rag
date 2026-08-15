from __future__ import annotations

from pathlib import Path

from app.runtime_health_models import RuntimeHealthState
from app.startup_diagnostics import inspect_startup_health


def _check(report, check_id: str):
    return next(item for item in report.checks if item.check_id == check_id)


def test_temp_artifact_residue_is_action_required_but_not_deleted(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    residue = runtime / "jobs" / "fictional-job" / "ai-audit.json.tmp"
    residue.parent.mkdir(parents=True, exist_ok=True)
    residue.write_bytes(b"fictional interrupted-write residue")
    before = residue.read_bytes()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    report = inspect_startup_health()

    check = _check(report, "temporary-artifact-residue")
    assert check.state == RuntimeHealthState.ACTION_REQUIRED
    assert check.metadata["count"] == 1
    assert report.base_app_ready is True
    assert report.action_required is True
    assert residue.exists()
    assert residue.read_bytes() == before
    assert "fictional interrupted-write residue" not in report.model_dump_json()
