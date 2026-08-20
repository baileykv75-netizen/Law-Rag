from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_labor_contract_snapshot_uses_2013_amendment_date_and_preserves_original_commencement(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-labor-contract-law"
        / "effective-2013-07-01"
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
    assert summary.article_count == 98
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-labor-contract-law", date(2013, 6, 30))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-labor-contract-law", date(2013, 7, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2013-07-01"
    assert str(current.version.effective_date) == "2013-07-01"

    article_57 = get_evidence(
        db,
        "legal:prc-labor-contract-law:effective-2013-07-01:article-57",
    )
    assert "注册资本不得少于人民币二百万元" in article_57.article.text

    article_63 = get_evidence(
        db,
        "legal:prc-labor-contract-law:effective-2013-07-01:article-63",
    )
    assert "同工同酬" in article_63.article.text

    terminal = get_evidence(
        db,
        "legal:prc-labor-contract-law:effective-2013-07-01:article-98",
    )
    assert terminal.article.article_token == "第九十八条"
    assert "2008年1月1日" in terminal.article.text
    assert "2013年7月1日" not in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
