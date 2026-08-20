from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_labor_mediation_arbitration_snapshot_is_complete_and_idempotent(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-labor-dispute-mediation-arbitration-law"
        / "effective-2008-05-01"
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
    assert summary.article_count == 54
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-labor-dispute-mediation-arbitration-law", date(2008, 4, 30))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-labor-dispute-mediation-arbitration-law", date(2008, 5, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2008-05-01"

    limitation = get_evidence(
        db,
        "legal:prc-labor-dispute-mediation-arbitration-law:effective-2008-05-01:article-27",
    )
    assert "时效期间为一年" in limitation.article.text

    final_award = get_evidence(
        db,
        "legal:prc-labor-dispute-mediation-arbitration-law:effective-2008-05-01:article-47",
    )
    assert "仲裁裁决为终局裁决" in final_award.article.text
    assert "月最低工资标准十二个月金额" in final_award.article.text

    terminal = get_evidence(
        db,
        "legal:prc-labor-dispute-mediation-arbitration-law:effective-2008-05-01:article-54",
    )
    assert terminal.article.article_token == "第五十四条"
    assert "2008年5月1日" in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
