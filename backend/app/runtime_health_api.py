from __future__ import annotations

from fastapi import APIRouter

from .runtime_health import inspect_runtime_health
from .runtime_health_models import RuntimeHealthReport

router = APIRouter(prefix="/api/runtime", tags=["runtime-health"])


@router.get("/health", response_model=RuntimeHealthReport)
def runtime_health() -> RuntimeHealthReport:
    """Return local, non-mutating runtime diagnostics without provider/network calls."""

    return inspect_runtime_health()
