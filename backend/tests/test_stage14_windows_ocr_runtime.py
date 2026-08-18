from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import ocr_runtime


def _versions(**overrides: str | None):
    values = {
        "paddlepaddle": "3.3.0",
        "paddleocr": "3.7.0",
        **overrides,
    }

    def fake_version(name: str) -> str:
        value = values.get(name)
        if value is None:
            raise ocr_runtime.metadata.PackageNotFoundError(name)
        return value

    return fake_version


def test_ocr_runtime_probe_reports_missing_distribution(monkeypatch) -> None:
    monkeypatch.setattr(
        ocr_runtime.metadata,
        "version",
        _versions(paddleocr=None),
    )

    probe = ocr_runtime.probe_ocr_runtime()

    assert probe.ready is False
    assert probe.state == "MISSING"
    assert probe.paddle_version == "3.3.0"
    assert probe.paddleocr_version is None
    assert probe.modules_imported is False


def test_ocr_runtime_probe_rejects_version_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        ocr_runtime.metadata,
        "version",
        _versions(paddlepaddle="3.3.1"),
    )

    probe = ocr_runtime.probe_ocr_runtime()

    assert probe.ready is False
    assert probe.state == "VERSION_MISMATCH"
    assert "expected 3.3.0" in probe.detail


def test_deep_ocr_runtime_probe_imports_and_runs_native_check_without_model_init(monkeypatch) -> None:
    monkeypatch.setattr(ocr_runtime.metadata, "version", _versions())
    calls: list[str] = []

    class FakeUtils:
        @staticmethod
        def run_check() -> None:
            calls.append("native-check")

    fake_paddle = SimpleNamespace(utils=FakeUtils())

    def fake_import(name: str):
        calls.append(name)
        if name == "paddle":
            return fake_paddle
        if name == "paddleocr":
            # The runtime probe must only import the module. It must not create
            # a PaddleOCR pipeline, which could select/download model weights.
            return SimpleNamespace(PaddleOCR=lambda **_: pytest.fail("model initialization is forbidden"))
        raise AssertionError(name)

    monkeypatch.setattr(ocr_runtime.importlib, "import_module", fake_import)

    probe = ocr_runtime.probe_ocr_runtime(import_modules=True, run_native_check=True)

    assert probe.ready is True
    assert probe.state == "READY"
    assert probe.modules_imported is True
    assert probe.native_check_run is True
    assert calls == ["paddle", "paddleocr", "native-check"]


def test_deep_ocr_runtime_probe_surfaces_broken_native_runtime(monkeypatch) -> None:
    monkeypatch.setattr(ocr_runtime.metadata, "version", _versions())

    def broken_import(name: str):
        raise OSError("missing native DLL")

    monkeypatch.setattr(ocr_runtime.importlib, "import_module", broken_import)

    probe = ocr_runtime.probe_ocr_runtime(import_modules=True)

    assert probe.ready is False
    assert probe.state == "BROKEN"
    assert probe.error_type == "OSError"


def test_native_check_requires_module_import() -> None:
    with pytest.raises(ValueError, match="requires import_modules"):
        ocr_runtime.probe_ocr_runtime(run_native_check=True)
