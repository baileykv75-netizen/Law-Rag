from __future__ import annotations

from pathlib import Path

from app.runtime_health_models import RuntimeHealthState
from app.startup_diagnostics import inspect_startup_health


def _check(report, check_id: str):
    return next(item for item in report.checks if item.check_id == check_id)


def test_missing_native_pdf_dependency_blocks_base_startup_without_mutation(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    real_find_spec = __import__("importlib.util", fromlist=["find_spec"]).find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "pypdfium2":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("app.startup_diagnostics.importlib.util.find_spec", fake_find_spec)

    report = inspect_startup_health()

    native = _check(report, "native-pdf-runtime")
    assert native.state == RuntimeHealthState.UNAVAILABLE
    assert native.required_for_base_app is True
    assert report.base_app_ready is False
    assert report.action_required is True
    assert not runtime.exists()
