from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_social_insurance_snapshot_preserves_historical_commencement_but_uses_2018_version_date(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-social-insurance-law"
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
    assert summary.article_count == 98
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-social-insurance-law", date(2018, 12, 28))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-social-insurance-law", date(2018, 12, 29))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2018-12-29"
    assert str(current.version.effective_date) == "2018-12-29"

    amended_registration = get_evidence(
        db,
        "legal:prc-social-insurance-law:effective-2018-12-29:article-57",
    )
    assert "市场监督管理部门" in amended_registration.article.text

    terminal = get_evidence(
        db,
        "legal:prc-social-insurance-law:effective-2018-12-29:article-98",
    )
    assert terminal.article.article_token == "第九十八条"
    assert "2011年7月1日" in terminal.article.text
    assert "2018年12月29日" not in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
