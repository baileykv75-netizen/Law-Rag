from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.legal.importer import LegalImportError, import_manifest
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_company_law_snapshot_imports_as_complete_current_version(tmp_path: Path) -> None:
    root = _repo_root()
    manifest = (
        root
        / "legal_data"
        / "authorities"
        / "prc-company-law"
        / "effective-2024-07-01"
        / "manifest.json"
    )
    db = tmp_path / "legal.db"

    try:
        report = import_manifest(
            manifest,
            db,
            rebuild=True,
            source_registry_path=root / "legal_data" / "source_registry.json",
        )
    except LegalImportError as exc:
        details = exc.report.model_dump_json(indent=2) if exc.report is not None else str(exc)
        pytest.fail(f"Company Law checked-in manifest failed deterministic validation:\n{details}")

    assert report.rejected_records == 0
    assert report.imported_records == 1

    summary = get_summary(db)
    assert summary.authority_count == 1
    assert summary.version_count == 1
    assert summary.article_count == 266
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "prc-company-law", date(2024, 6, 30))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "prc-company-law", date(2024, 7, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2024-07-01"

    contribution = get_evidence(
        db,
        "legal:prc-company-law:effective-2024-07-01:article-47",
    )
    assert "五年内缴足" in contribution.article.text

    terminal = get_evidence(
        db,
        "legal:prc-company-law:effective-2024-07-01:article-266",
    )
    assert terminal.article.article_token == "第二百六十六条"
    assert "2024年7月1日" in terminal.article.text

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=root / "legal_data" / "source_registry.json",
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
    assert get_summary(db).article_count == 266
