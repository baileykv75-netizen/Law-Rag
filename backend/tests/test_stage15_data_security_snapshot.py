from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_data_security_snapshot_imports_as_complete_effective_version(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-data-security-law"
        / "effective-2021-09-01"
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
    assert summary.article_count == 55
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-data-security-law", date(2021, 8, 31))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-data-security-law", date(2021, 9, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2021-09-01"

    terminal = get_evidence(
        db,
        "legal:prc-data-security-law:effective-2021-09-01:article-55",
    )
    assert terminal.article.article_token == "第五十五条"
    assert "2021年9月1日" in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
