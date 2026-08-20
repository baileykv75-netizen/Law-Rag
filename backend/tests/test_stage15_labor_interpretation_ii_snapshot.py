from __future__ import annotations

from datetime import date
from pathlib import Path

from app.legal.corpus_inventory import CatalogEntryState, load_official_corpus_catalog
from app.legal.importer import import_manifest
from app.legal.source_registry import load_source_registry
from app.legal.store import get_evidence, get_summary, resolve_version


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_labor_interpretation_ii_is_complete_without_flattening_interpretation_i(tmp_path: Path) -> None:
    root = _repo_root()
    corpus_root = root / "legal_data"
    registry_path = corpus_root / "source_registry.json"
    manifest = (
        corpus_root
        / "authorities"
        / "spc-labor-dispute-interpretation-2"
        / "effective-2025-09-01"
        / "manifest.json"
    )
    db = tmp_path / "legal.db"

    report = import_manifest(
        manifest,
        db,
        rebuild=True,
        source_registry_path=registry_path,
    )
    assert report.rejected_records == 0
    assert report.imported_records == 1

    summary = get_summary(db)
    assert summary.authority_count == 1
    assert summary.version_count == 1
    assert summary.article_count == 21
    assert summary.excerpt_version_count == 0

    before = resolve_version(db, "spc-labor-dispute-interpretation-2", date(2025, 8, 31))
    assert before.state.value == "NO_APPLICABLE_VERSION"

    current = resolve_version(db, "spc-labor-dispute-interpretation-2", date(2025, 9, 1))
    assert current.state.value == "RESOLVED"
    assert current.version is not None
    assert current.version.version_id == "effective-2025-09-01"

    terminal = get_evidence(
        db,
        "legal:spc-labor-dispute-interpretation-2:effective-2025-09-01:article-21",
    )
    assert "第三十二条第一款同时废止" in terminal.article.text
    assert "2025年9月1日" in terminal.article.text

    registry = load_source_registry(registry_path)
    catalog = load_official_corpus_catalog(
        corpus_root / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=corpus_root,
    )
    interpretation_i = next(
        item
        for item in catalog.entries
        if item.authority.authority_id == "spc-labor-dispute-interpretation-1"
    )
    assert interpretation_i.catalog_state == CatalogEntryState.BLOCKED

    repeat = import_manifest(
        manifest,
        db,
        source_registry_path=registry_path,
    )
    assert repeat.rejected_records == 0
    assert repeat.no_change_records == 1
