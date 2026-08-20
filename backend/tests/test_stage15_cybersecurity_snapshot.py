from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_cybersecurity_snapshot_preserves_text_but_uses_amendment_effective_date(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-cybersecurity-law"
        / "effective-2026-01-01"
        / "manifest.json"
    )
    db = tmp_path / "legal.db"

    report = import_manifest(
        manifest,
        db,
        rebuild=True,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert report.rejected_records == 0
    assert report.imported_records == 1

    summary = get_summary(db)
    assert summary.authority_count == 1
    assert summary.version_count == 1
    assert summary.article_count == 81

    before = resolve_version(db, "prc-cybersecurity-law", date(2025, 12, 31))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-cybersecurity-law", date(2026, 1, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2026-01-01"
    assert str(current.version.effective_date) == "2026-01-01"

    article_20 = get_evidence(
        db,
        "legal:prc-cybersecurity-law:effective-2026-01-01:article-20",
    )
    assert "人工智能" in article_20.article.text

    terminal = get_evidence(
        db,
        "legal:prc-cybersecurity-law:effective-2026-01-01:article-81",
    )
    assert terminal.article.article_token == "第八十一条"
    assert "2017年6月1日" in terminal.article.text
    assert "2026年1月1日" not in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
