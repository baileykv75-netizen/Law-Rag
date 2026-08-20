from __future__ import annotations

import json
from pathlib import Path

from app.legal.corpus_inventory import CatalogEntryState, load_official_corpus_catalog
from app.legal.importer import import_manifest
from app.legal.source_registry import load_source_registry
from app.legal.store import get_summary


PACK_EXPECTATIONS = {
    "cn-intellectual-property-core": (4, 5, 350),
    "cn-enterprise-compliance-core": (6, 6, 587),
    "cn-labor-dispute-core": (5, 5, 378),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pack_manifest_paths(root: Path, pack_id: str) -> list[Path]:
    pack = json.loads(
        (root / "legal_data" / "packs" / pack_id / "pack.json").read_text(encoding="utf-8")
    )
    assert pack["status"] == "DRAFT"
    return [root / "legal_data" / relative for relative in pack["authority_manifest_paths"]]


def _import_paths(root: Path, manifests: list[Path], db: Path):
    registry = root / "legal_data" / "source_registry.json"
    reports = []
    for index, manifest in enumerate(manifests):
        assert manifest.is_file(), manifest
        reports.append(
            import_manifest(
                manifest,
                db,
                rebuild=index == 0,
                source_registry_path=registry,
            )
        )
    return reports


def test_enterprise_and_labor_packs_import_complete_frozen_corpora(tmp_path: Path) -> None:
    root = _repo_root()

    for pack_id in ("cn-enterprise-compliance-core", "cn-labor-dispute-core"):
        manifests = _pack_manifest_paths(root, pack_id)
        expected_authorities, expected_versions, expected_articles = PACK_EXPECTATIONS[pack_id]
        assert len(manifests) == expected_versions

        db = tmp_path / f"{pack_id}.db"
        first = _import_paths(root, manifests, db)
        assert all(report.rejected_records == 0 for report in first)
        assert all(report.imported_records == 1 for report in first)

        summary = get_summary(db)
        assert summary.authority_count == expected_authorities
        assert summary.version_count == expected_versions
        assert summary.article_count == expected_articles
        assert summary.excerpt_version_count == 0

        second = [
            import_manifest(
                manifest,
                db,
                source_registry_path=root / "legal_data" / "source_registry.json",
            )
            for manifest in manifests
        ]
        assert all(report.rejected_records == 0 for report in second)
        assert all(report.no_change_records == 1 for report in second)
        assert get_summary(db).article_count == expected_articles


def test_three_pack_union_deduplicates_shared_authority_version_and_is_idempotent(tmp_path: Path) -> None:
    root = _repo_root()
    ordered: list[Path] = []
    seen: set[str] = set()

    for pack_id in PACK_EXPECTATIONS:
        for manifest in _pack_manifest_paths(root, pack_id):
            relative = manifest.relative_to(root / "legal_data").as_posix()
            if relative not in seen:
                seen.add(relative)
                ordered.append(manifest)

    # 5 IP + 6 enterprise + 5 labor, minus the shared Anti-Unfair Competition manifest.
    assert len(ordered) == 15

    db = tmp_path / "three-domain.db"
    first = _import_paths(root, ordered, db)
    assert all(report.rejected_records == 0 for report in first)
    assert all(report.imported_records == 1 for report in first)

    summary = get_summary(db)
    assert summary.authority_count == 14
    assert summary.version_count == 15
    assert summary.article_count == 1274
    assert summary.effective_version_count == 14
    assert summary.excerpt_version_count == 0

    second = [
        import_manifest(
            manifest,
            db,
            source_registry_path=root / "legal_data" / "source_registry.json",
        )
        for manifest in ordered
    ]
    assert all(report.rejected_records == 0 for report in second)
    assert all(report.no_change_records == 1 for report in second)

    repeated = get_summary(db)
    assert repeated.authority_count == 14
    assert repeated.version_count == 15
    assert repeated.article_count == 1274


def test_blocked_interpretation_one_remains_outside_labor_pack() -> None:
    root = _repo_root()
    registry = load_source_registry(root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=root / "legal_data",
    )
    blocked = next(
        item
        for item in catalog.entries
        if item.authority.authority_id == "spc-labor-dispute-interpretation-1"
    )
    assert blocked.catalog_state == CatalogEntryState.BLOCKED

    labor_paths = {
        path.relative_to(root / "legal_data").as_posix()
        for path in _pack_manifest_paths(root, "cn-labor-dispute-core")
    }
    assert not any("spc-labor-dispute-interpretation-1" in path for path in labor_paths)
