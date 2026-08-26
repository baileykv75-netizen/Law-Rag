from __future__ import annotations

import json
import socket
from pathlib import Path

from app.release_assets_cli import DEFAULT_CORPUS_RELEASE, build_public_release_assets
from app.release_launcher import _select_launch_port, configure_release_environment, main


_RELEASE_KEYS = (
    "LAW_RAG_RUNTIME_DIR",
    "LAW_RAG_LEGAL_DB",
    "LAW_RAG_LEGAL_DB_DEFAULT_RUNTIME",
    "LAW_RAG_RETRIEVAL_DB",
    "LAW_RAG_RETRIEVAL_DB_DEFAULT_RUNTIME",
    "LAW_RAG_FRONTEND_DIST",
    "LAW_RAG_RELEASE_ASSET_ROOT",
)


def _clear_release_env(monkeypatch) -> None:
    for key in _RELEASE_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_release_environment_uses_writable_runtime_for_legal_assets(tmp_path: Path, monkeypatch) -> None:
    _clear_release_env(monkeypatch)
    asset_root = tmp_path / "bundle-assets"
    runtime = tmp_path / "custom-runtime"
    monkeypatch.setenv("LAW_RAG_RELEASE_ASSET_ROOT", str(asset_root))
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    configured = configure_release_environment()

    assert configured["LAW_RAG_RUNTIME_DIR"] == str(runtime)
    assert configured["LAW_RAG_LEGAL_DB"] == str(runtime / "legal" / "legal.db")
    assert configured["LAW_RAG_RETRIEVAL_DB"] == str(runtime / "legal" / "retrieval.db")
    assert configured["LAW_RAG_FRONTEND_DIST"] == str(asset_root / "frontend-dist")
    assert not runtime.exists()


def test_release_diagnostic_environment_can_read_immutable_packaged_legal_assets(
    tmp_path: Path, monkeypatch
) -> None:
    _clear_release_env(monkeypatch)
    asset_root = tmp_path / "bundle-assets"
    runtime = tmp_path / "custom-runtime"
    monkeypatch.setenv("LAW_RAG_RELEASE_ASSET_ROOT", str(asset_root))
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    configured = configure_release_environment(use_packaged_legal=True)

    assert configured["LAW_RAG_LEGAL_DB"] == str(asset_root / "public-assets" / "legal" / "legal.db")
    assert configured["LAW_RAG_RETRIEVAL_DB"] == str(asset_root / "public-assets" / "legal" / "retrieval.db")
    assert not runtime.exists()


def test_release_environment_never_overwrites_explicit_asset_paths(tmp_path: Path, monkeypatch) -> None:
    _clear_release_env(monkeypatch)
    custom_legal = tmp_path / "legal-custom.db"
    monkeypatch.setenv("LAW_RAG_LEGAL_DB", str(custom_legal))

    configured = configure_release_environment()

    assert configured["LAW_RAG_LEGAL_DB"] == str(custom_legal)


def test_release_diagnose_is_non_mutating_and_never_prints_provider_secret_values(tmp_path: Path, monkeypatch, capsys) -> None:
    _clear_release_env(monkeypatch)
    runtime = tmp_path / "runtime"
    asset_root = tmp_path / "assets"
    deepseek_secret = "stage11d-deepseek-secret-sentinel"
    kimi_secret = "stage11d-kimi-secret-sentinel"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("LAW_RAG_RELEASE_ASSET_ROOT", str(asset_root))
    monkeypatch.setenv("DEEPSEEK_API_KEY", deepseek_secret)
    monkeypatch.setenv("MOONSHOT_API_KEY", kimi_secret)

    code = main(["--diagnose", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert code in {0, 2}
    assert "checks" in payload
    assert deepseek_secret not in output
    assert kimi_secret not in output
    assert not runtime.exists()


def test_release_corpus_diagnostic_uses_packaged_baseline_without_creating_runtime(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _clear_release_env(monkeypatch)
    asset_root = tmp_path / "assets"
    runtime = tmp_path / "runtime"
    build_public_release_assets(asset_root, DEFAULT_CORPUS_RELEASE)
    monkeypatch.setenv("LAW_RAG_RELEASE_ASSET_ROOT", str(asset_root))
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))

    code = main(["--diagnose-corpus", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ready"] is True
    assert payload["legal"] == {
        "authority_count": 14,
        "version_count": 15,
        "article_count": 1274,
        "excerpt_version_count": 0,
    }
    assert payload["retrieval"]["ready"] is True
    assert payload["retrieval"]["lexical_ready"] is True
    assert payload["retrieval"]["article_count"] == 1274
    assert payload["smoke_query"]["authority_id"] == "prc-labor-contract-law"
    assert payload["smoke_query"]["exact_hit"] is True
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


def test_default_desktop_launch_falls_forward_when_port_8000_is_busy(monkeypatch) -> None:
    def fake_available(host: str, port: int) -> bool:
        return host == "127.0.0.1" and port == 8001

    monkeypatch.setattr("app.release_launcher._port_available", fake_available)

    port, changed = _select_launch_port("127.0.0.1", None, span=3)

    assert port == 8001
    assert changed is True


def test_explicit_port_still_fails_when_busy() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]

        try:
            _select_launch_port("127.0.0.1", port)
        except RuntimeError as exc:
            assert "already in use" in str(exc)
        else:
            raise AssertionError("explicit busy port should fail closed")
