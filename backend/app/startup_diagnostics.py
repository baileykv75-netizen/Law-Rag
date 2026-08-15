from __future__ import annotations

import importlib.util

from .runtime_health import inspect_runtime_health
from .runtime_health_models import (
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthSeverity,
    RuntimeHealthState,
)
from .storage import runtime_dir


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


def _temporary_residue_check() -> RuntimeHealthCheck:
    root = runtime_dir()
    if not root.exists() or not root.is_dir():
        return RuntimeHealthCheck(
            check_id="temporary-artifact-residue",
            label="Interrupted-write temporary artifacts",
            state=RuntimeHealthState.OK,
            severity=RuntimeHealthSeverity.INFO,
            required_for_base_app=False,
            detail="No runtime directory exists yet, so no temporary artifact residue is present.",
            metadata={"count": 0},
        )
    try:
        residues = [path for path in root.rglob("*.tmp") if path.is_file()]
    except OSError:
        return RuntimeHealthCheck(
            check_id="temporary-artifact-residue",
            label="Interrupted-write temporary artifacts",
            state=RuntimeHealthState.UNAVAILABLE,
            severity=RuntimeHealthSeverity.WARNING,
            required_for_base_app=False,
            detail="The runtime directory could not be scanned completely for temporary artifacts.",
            action="Inspect local filesystem permissions before relying on cleanup/recovery decisions.",
        )
    if not residues:
        return RuntimeHealthCheck(
            check_id="temporary-artifact-residue",
            label="Interrupted-write temporary artifacts",
            state=RuntimeHealthState.OK,
            severity=RuntimeHealthSeverity.INFO,
            required_for_base_app=False,
            detail="No *.tmp artifact residue was found under the local runtime directory.",
            metadata={"count": 0},
        )
    return RuntimeHealthCheck(
        check_id="temporary-artifact-residue",
        label="Interrupted-write temporary artifacts",
        state=RuntimeHealthState.ACTION_REQUIRED,
        severity=RuntimeHealthSeverity.WARNING,
        required_for_base_app=False,
        detail=f"Found {len(residues)} temporary artifact file(s), consistent with an interrupted or failed write.",
        action="Do not auto-delete them. Verify the corresponding canonical target files first, preserve evidence needed for diagnosis, then remove stale temp files manually if appropriate.",
        metadata={"count": len(residues)},
    )


def inspect_startup_health() -> RuntimeHealthReport:
    report = inspect_runtime_health()
    native_pdf = _native_pdf_check()
    residue = _temporary_residue_check()
    checks = [report.checks[0], native_pdf, residue, *report.checks[1:]] if report.checks else [native_pdf, residue]
    base_ready = report.base_app_ready and native_pdf.state == RuntimeHealthState.OK
    action_required = (
        report.action_required
        or native_pdf.state != RuntimeHealthState.OK
        or residue.state == RuntimeHealthState.ACTION_REQUIRED
    )
    return report.model_copy(
        update={
            "checks": checks,
            "base_app_ready": base_ready,
            "action_required": action_required,
        }
    )
