from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.release_frontend import _frontend_response, _safe_asset, frontend_dist_path


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "frontend-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>Law-Rag release shell</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('release');", encoding="utf-8")
    return dist


def test_frontend_dist_is_unconfigured_without_env_or_bundle(monkeypatch) -> None:
    monkeypatch.delenv("LAW_RAG_FRONTEND_DIST", raising=False)
    monkeypatch.delattr("app.release_frontend.sys._MEIPASS", raising=False)

    assert frontend_dist_path() is None


def test_release_frontend_serves_real_asset_and_spa_fallback(tmp_path: Path, monkeypatch) -> None:
    dist = _dist(tmp_path)
    monkeypatch.setenv("LAW_RAG_FRONTEND_DIST", str(dist))

    asset = _frontend_response("assets/app.js")
    workspace = _frontend_response("workspace")

    assert isinstance(asset, FileResponse)
    assert Path(asset.path) == dist / "assets" / "app.js"
    assert isinstance(workspace, FileResponse)
    assert Path(workspace.path) == dist / "index.html"


def test_release_frontend_does_not_mask_unknown_api_route(tmp_path: Path, monkeypatch) -> None:
    dist = _dist(tmp_path)
    monkeypatch.setenv("LAW_RAG_FRONTEND_DIST", str(dist))

    with pytest.raises(HTTPException) as exc_info:
        _frontend_response("api/not-a-real-route")

    assert exc_info.value.status_code == 404


def test_release_frontend_rejects_path_escape(tmp_path: Path) -> None:
    dist = _dist(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("private", encoding="utf-8")

    assert _safe_asset(dist, "../secret.txt") is None


def test_missing_release_index_is_explicit(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "frontend-dist"
    dist.mkdir()
    monkeypatch.setenv("LAW_RAG_FRONTEND_DIST", str(dist))

    with pytest.raises(HTTPException) as exc_info:
        _frontend_response("workspace")

    assert exc_info.value.status_code == 503
