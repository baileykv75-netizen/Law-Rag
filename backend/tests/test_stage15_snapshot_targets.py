from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.legal.corpus_inventory import load_official_corpus_catalog
from app.legal.snapshot_targets import SnapshotTargetsError, load_snapshot_targets
from app.legal.source_registry import load_source_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _inputs():
    root = _repo_root()
    registry = load_source_registry(root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=root / "legal_data",
    )
    return root, registry, catalog


def test_checked_in_ip_snapshot_targets_cover_pack_exactly() -> None:
    root, registry, catalog = _inputs()
    targets = load_snapshot_targets(
        root / "legal_data" / "catalog" / "cn-intellectual-property-core.snapshot-targets.json",
        catalog=catalog,
        registry=registry,
    )

    counts = {
        (item.authority_id, item.version_id): item.expected_article_count for item in targets.targets
    }
    assert counts == {
        ("prc-patent-law", "effective-2021-06-01"): 82,
        ("prc-copyright-law", "effective-2021-06-01"): 67,
        ("prc-trademark-law", "effective-2019-11-01"): 73,
        ("prc-trademark-law", "effective-2027-01-01"): 87,
        ("prc-anti-unfair-competition-law", "effective-2025-10-15"): 41,
    }


def test_future_trademark_snapshot_target_does_not_change_version_status() -> None:
    root, registry, catalog = _inputs()
    load_snapshot_targets(
        root / "legal_data" / "catalog" / "cn-intellectual-property-core.snapshot-targets.json",
        catalog=catalog,
        registry=registry,
    )
    future = next(
        item
        for item in catalog.entries
        if item.authority.authority_id == "prc-trademark-law"
        and item.version_id == "effective-2027-01-01"
    )
    assert future.status.value == "NOT_YET_EFFECTIVE"
    assert str(future.effective_date) == "2027-01-01"


def test_snapshot_target_source_must_already_be_vetted_in_catalog(tmp_path: Path) -> None:
    root, registry, catalog = _inputs()
    source = root / "legal_data" / "catalog" / "cn-intellectual-property-core.snapshot-targets.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["targets"][0]["snapshot_source_url"] = "https://www.npc.gov.cn/not-the-vetted-source.html"
    bad = tmp_path / "targets.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SnapshotTargetsError, match="match exactly one catalog source_ref"):
        load_snapshot_targets(bad, catalog=catalog, registry=registry)


def test_snapshot_target_set_cannot_silently_drop_one_pack_member(tmp_path: Path) -> None:
    root, registry, catalog = _inputs()
    source = root / "legal_data" / "catalog" / "cn-intellectual-property-core.snapshot-targets.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["targets"] = payload["targets"][:-1]
    bad = tmp_path / "targets.json"
    bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SnapshotTargetsError, match="cover exactly"):
        load_snapshot_targets(bad, catalog=catalog, registry=registry)
