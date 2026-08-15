from __future__ import annotations

import importlib.util

from .runtime_health import inspect_runtime_health
from .runtime_health_models import (
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthSeverity,
    RuntimeHealthState,
)


def _native_pdf_check() -> RuntimeHealthCheck:
    required = ("pypdf", "pypdfium2")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        return RuntimeHealthCheck(
            check_id="native-pdf-runtime",
            label="Native PDF processing runtime",
            state=RuntimeHealthState.UNAVAILABLE,
            severity=RuntimeHealthSeverity.ERROR,
            required_for_base_app=True,
            detail=f"Required native PDF module(s) are unavailable: {', '.join(missing)}.",
            action="Run setup-dev.bat to restore the base backend dependencies before starting Law-Rag.",
            metadata={"missing_modules": ",".join(missing)},
        )
    return RuntimeHealthCheck(
        check_id="native-pdf-runtime",
        label="Native PDF processing runtime",
        state=RuntimeHealthState.OK,
        severity=RuntimeHealthSeverity.INFO,
        required_for_base_app=True,
        detail="pypdf and pypdfium2 are discoverable for native PDF extraction/rendering.",
    )


def inspect_startup_health() -> RuntimeHealthReport:
    report = inspect_runtime_health()
    native_pdf = _native_pdf_check()
    checks = [report.checks[0], native_pdf, *report.checks[1:]] if report.checks else [native_pdf]
    base_ready = report.base_app_ready and native_pdf.state == RuntimeHealthState.OK
    action_required = report.action_required or native_pdf.state != RuntimeHealthState.OK
    return report.model_copy(
        update={
            "checks": checks,
            "base_app_ready": base_ready,
            "action_required": action_required,
        }
    )
