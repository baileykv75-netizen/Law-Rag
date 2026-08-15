from __future__ import annotations

import json
from pathlib import Path

from app.release_launcher import configure_release_environment, main


_RELEASE_KEYS = (
    "LAW_RAG_RUNTIME_DIR",
    "LAW_RAG_LEGAL_DB",
    "LAW_RAG_RETRIEVAL_DB",
    "LAW_RAG_FRONTEND_DIST",
)


def _clear_release_env(monkeypatch) -> None:
    for key in _RELEASE_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_release_environment_uses_asset_root_and_separate_writable_runtime(tmp_path: Path, monkeypatch) -> None:
    _clear_release_env(monkeypatch)
    asset_root = tmp_path / "bundle-assets"
    runtime = tmp_path / "custom-runtime"
    monkeypatch.setenv("LAW_RAG_RELEASE_ASSET_ROOT", str(asset_root))
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    configured = configure_release_environment()

    assert configured["LAW_RAG_RUNTIME_DIR"] == str(runtime)
    assert configured["LAW_RAG_LEGAL_DB"] == str(asset_root / "public-assets" / "legal" / "legal.db")
    assert configured["LAW_RAG_RETRIEVAL_DB"] == str(asset_root / "public-assets" / "legal" / "retrieval.db")
    assert configured["LAW_RAG_FRONTEND_DIST"] == str(asset_root / "frontend-dist")
    assert not runtime.exists()


def test_release_environment_never_overwrites_explicit_asset_paths(tmp_path: Path, monkeypatch) -> None:
    _clear_release_env(monkeypatch)
    custom_legal = tmp_path / "legal-custom.db"
    monkeypatch.setenv("LAW_RAG_LEGAL_DB", str(custom_legal))

    configured = configure_release_environment()

    assert configured["LAW_RAG_LEGAL_DB"] == str(custom_legal)


def test_release_diagnose_is_non_mutating_and_does_not_require_provider_keys(tmp_path: Path, monkeypatch, capsys) -> None:
    _clear_release_env(monkeypatch)
    runtime = tmp_path / "runtime"
    asset_root = tmp_path / "assets"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("LAW_RAG_RELEASE_ASSET_ROOT", str(asset_root))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    code = main(["--diagnose", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert code in {0, 2}
    assert "checks" in payload
    assert "DEEPSEEK_API_KEY" not in output
    assert "MOONSHOT_API_KEY" not in output
    assert not runtime.exists()


def test_release_launcher_rejects_non_loopback_host_without_starting_server(tmp_path: Path, monkeypatch, capsys) -> None:
    _clear_release_env(monkeypatch)
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))

    class ReadyReport:
        base_app_ready = True
        action_required = False
        checks = []

    monkeypatch.setattr("app.startup_diagnostics.inspect_startup_health", lambda: ReadyReport())

    code = main(["--host", "0.0.0.0", "--no-browser"])

    assert code == 2
    assert "only permits loopback" in capsys.readouterr().out
