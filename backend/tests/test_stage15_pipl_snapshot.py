from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_pipl_snapshot_imports_as_complete_effective_version(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-personal-information-protection-law"
        / "effective-2021-11-01"
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
    assert summary.article_count == 74
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-personal-information-protection-law", date(2021, 10, 31))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-personal-information-protection-law", date(2021, 11, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2021-11-01"

    automated = get_evidence(
        db,
        "legal:prc-personal-information-protection-law:effective-2021-11-01:article-24",
    )
    assert "自动化决策" in automated.article.text

    terminal = get_evidence(
        db,
        "legal:prc-personal-information-protection-law:effective-2021-11-01:article-74",
    )
    assert terminal.article.article_token == "第七十四条"
    assert "2021年11月1日" in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
