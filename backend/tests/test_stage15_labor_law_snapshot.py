from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_labor_law_snapshot_uses_2018_amendment_date_and_preserves_original_commencement(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-labor-law"
        / "effective-2018-12-29"
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
    assert summary.article_count == 107
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-labor-law", date(2018, 12, 28))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-labor-law", date(2018, 12, 29))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2018-12-29"
    assert str(current.version.effective_date) == "2018-12-29"

    amended = get_evidence(
        db,
        "legal:prc-labor-law:effective-2018-12-29:article-94",
    )
    assert "市场监督管理部门吊销营业执照" in amended.article.text

    terminal = get_evidence(
        db,
        "legal:prc-labor-law:effective-2018-12-29:article-107",
    )
    assert terminal.article.article_token == "第一百零七条"
    assert "1995年1月1日" in terminal.article.text
    assert "2018年12月29日" not in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
