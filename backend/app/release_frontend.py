from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, Response

from .tester_license import (
    TesterLicenseActivationRequest,
    TesterLicenseError,
    TesterLicenseStatus,
    activate_tester_license,
    current_tester_license_status,
)

router = APIRouter(include_in_schema=False)


def frontend_dist_path() -> Path | None:
    """Resolve production frontend assets without creating or mutating files."""

    configured = os.getenv("LAW_RAG_FRONTEND_DIST", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return (Path(bundle_root) / "frontend-dist").resolve()
    return None


def _safe_asset(dist: Path, requested_path: str) -> Path | None:
    if not requested_path:
        return None
    candidate = (dist / requested_path).resolve()
    try:
        candidate.relative_to(dist)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _frontend_response(requested_path: str) -> Response:
    dist = frontend_dist_path()
    if dist is None or not dist.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Production frontend assets are not configured in this runtime.",
        )

    index = dist / "index.html"
    if not index.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production frontend index.html is missing from the configured asset directory.",
        )

    asset = _safe_asset(dist, requested_path)
    if asset is not None:
        return FileResponse(asset)

    # Browser routes such as /workspace must resolve to the SPA shell. API paths
    # are never allowed to fall through to HTML, because that would hide a
    # missing/incorrect backend endpoint behind a successful 200 response.
    if requested_path == "api" or requested_path.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API route not found.")
    return FileResponse(index, media_type="text/html")


@router.get("/api/tester-license/status", response_model=TesterLicenseStatus)
def tester_license_status() -> TesterLicenseStatus:
    return current_tester_license_status()


@router.post("/api/tester-license/activate", response_model=TesterLicenseStatus)
def tester_license_activate(request: TesterLicenseActivationRequest) -> TesterLicenseStatus:
    try:
        return activate_tester_license(request.token)
    except TesterLicenseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.detail) from exc


@router.get("/")
def release_frontend_root() -> Response:
    return _frontend_response("")


@router.get("/{frontend_path:path}")
def release_frontend_path(frontend_path: str) -> Response:
    return _frontend_response(frontend_path)
