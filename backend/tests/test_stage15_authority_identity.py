from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from app.legal.corpus_inventory import load_official_corpus_catalog
from app.legal.source_registry import load_source_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_catalog_authority_metadata_is_stable_across_versions() -> None:
    root = _repo_root()
    registry = load_source_registry(root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=root / "legal_data",
    )

    identities: dict[str, set[tuple[str, str, str, str | None, str]]] = defaultdict(set)
    for entry in catalog.entries:
        authority = entry.authority
        identities[authority.authority_id].add(
            (
                authority.title,
                authority.authority_type.value,
                authority.issuing_body,
                authority.document_number,
                authority.jurisdiction,
            )
        )

    unstable = {
        authority_id: values
        for authority_id, values in identities.items()
        if len(values) != 1
    }
    assert unstable == {}


def test_trademark_presidential_order_is_version_provenance_not_authority_identity() -> None:
    root = _repo_root()
    registry = load_source_registry(root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=root / "legal_data",
    )

    versions = [
        entry for entry in catalog.entries if entry.authority.authority_id == "prc-trademark-law"
    ]
    assert {entry.version_id for entry in versions} == {
        "effective-2019-11-01",
        "effective-2027-01-01",
    }
    assert all(entry.authority.document_number is None for entry in versions)

    future = next(entry for entry in versions if entry.version_id == "effective-2027-01-01")
    assert any("第七十七号" in source.name for source in future.source_refs)
