from __future__ import annotations

from pathlib import Path

from app.runtime_health_models import RuntimeHealthState
from app.startup_diagnostics import inspect_startup_health


def _check(report, check_id: str):
    return next(item for item in report.checks if item.check_id == check_id)


def test_missing_ocr_and_semantic_dependencies_do_not_block_base_app(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    real_runtime_find_spec = __import__("importlib.util", fromlist=["find_spec"]).find_spec

    def fake_runtime_find_spec(name: str, *args, **kwargs):
        if name in {"paddle", "paddleocr", "sentence_transformers"}:
            return None
        return real_runtime_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("app.runtime_health.importlib.util.find_spec", fake_runtime_find_spec)

    report = inspect_startup_health()

    assert _check(report, "native-pdf-runtime").state == RuntimeHealthState.OK
    assert _check(report, "ocr-runtime").state == RuntimeHealthState.OPTIONAL_NOT_CONFIGURED
    assert _check(report, "semantic-runtime").state == RuntimeHealthState.OPTIONAL_NOT_CONFIGURED
    assert report.base_app_ready is True
    assert not runtime.exists()
