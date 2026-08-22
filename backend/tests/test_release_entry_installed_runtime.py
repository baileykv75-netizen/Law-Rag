from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import release_entry


def _fake_frozen(monkeypatch: pytest.MonkeyPatch, executable: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(executable.parent / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))


def test_portable_frozen_release_keeps_adjacent_runtime_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "portable" / "Law-Rag.exe"
    exe.parent.mkdir(parents=True)
    _fake_frozen(monkeypatch, exe)
    monkeypatch.delenv("LAW_RAG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    layout = release_entry.configure_installed_runtime_default()

    assert layout["installed"] is False
    assert layout["runtime_source"] == "PORTABLE_DEFAULT"
    assert layout["runtime_dir"] == str((exe.parent / "runtime").resolve())
    assert layout["user_data_separated_from_app"] is False
    assert "LAW_RAG_RUNTIME_DIR" not in os.environ
    assert layout["network_used"] is False


def test_installed_marker_moves_default_runtime_to_localappdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "Programs" / "Law-Rag" / "Law-Rag.exe"
    exe.parent.mkdir(parents=True)
    (exe.parent / release_entry._INSTALL_MARKER).write_text("installed-per-user\n", encoding="utf-8")
    _fake_frozen(monkeypatch, exe)
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.delenv("LAW_RAG_RUNTIME_DIR", raising=False)

    layout = release_entry.configure_installed_runtime_default()

    expected = (local_appdata / "Law-Rag" / "runtime").resolve()
    assert layout["installed"] is True
    assert layout["runtime_source"] == "INSTALLED_MARKER"
    assert layout["runtime_dir"] == str(expected)
    assert layout["user_data_separated_from_app"] is True
    assert os.environ["LAW_RAG_RUNTIME_DIR"] == str(expected)
    assert not expected.exists()


def test_explicit_runtime_override_wins_even_for_installed_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "Programs" / "Law-Rag" / "Law-Rag.exe"
    exe.parent.mkdir(parents=True)
    (exe.parent / release_entry._INSTALL_MARKER).write_text("installed-per-user\n", encoding="utf-8")
    _fake_frozen(monkeypatch, exe)
    explicit = tmp_path / "OperatorRuntime"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(explicit))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    layout = release_entry.configure_installed_runtime_default()

    assert layout["installed"] is True
    assert layout["runtime_source"] == "EXPLICIT_ENVIRONMENT"
    assert layout["runtime_dir"] == str(explicit.resolve())
    assert os.environ["LAW_RAG_RUNTIME_DIR"] == str(explicit)


def test_installed_release_fails_closed_without_localappdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "Programs" / "Law-Rag" / "Law-Rag.exe"
    exe.parent.mkdir(parents=True)
    (exe.parent / release_entry._INSTALL_MARKER).write_text("installed-per-user\n", encoding="utf-8")
    _fake_frozen(monkeypatch, exe)
    monkeypatch.delenv("LAW_RAG_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(RuntimeError, match="requires LOCALAPPDATA"):
        release_entry.configure_installed_runtime_default()
