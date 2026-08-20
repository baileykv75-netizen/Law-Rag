from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.legal.corpus_inventory import (
    CatalogEntryState,
    OfficialCorpusCatalogError,
    load_official_corpus_catalog,
)
from app.legal.corpus_packs import CorpusPackStatus, discover_corpus_packs
from app.legal.models import OfficialSourceRef, SourceRole, VersionStatus
from app.legal.source_registry import (
    LegalSourceRegistryError,
    load_source_registry,
    validate_official_source_ref,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_checked_in_catalog():
    repo_root = _repo_root()
    registry = load_source_registry(repo_root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        repo_root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=repo_root / "legal_data",
    )
    return registry, catalog


def test_checked_in_source_registry_and_catalog_validate() -> None:
    registry, catalog = _load_checked_in_catalog()
    assert registry.verified_on == "2026-08-20"
    assert str(catalog.verified_on) == "2026-08-20"
    assert len(catalog.entries) == 16
    assert sum(item.catalog_state == CatalogEntryState.BLOCKED for item in catalog.entries) == 1


def test_inventory_represents_exactly_three_stage15_packs_with_only_ip_populated_so_far() -> None:
    _, catalog = _load_checked_in_catalog()
    expected = {
        "cn-intellectual-property-core",
        "cn-enterprise-compliance-core",
        "cn-labor-dispute-core",
    }
    assert {pack_id for item in catalog.entries for pack_id in item.pack_ids} == expected

    packs = discover_corpus_packs(_repo_root() / "legal_data")
    assert {item.manifest.pack_id for item in packs} == expected
    assert all(item.manifest.status == CorpusPackStatus.DRAFT for item in packs)

    by_id = {item.manifest.pack_id: item for item in packs}
    ip = by_id["cn-intellectual-property-core"]
    assert ip.manifest.pack_version == "0.2.0"
    assert len(ip.members) == 5
    assert {(item.authority_id, item.version_id) for item in ip.members} == {
        ("prc-patent-law", "effective-2021-06-01"),
        ("prc-copyright-law", "effective-2021-06-01"),
        ("prc-trademark-law", "effective-2019-11-01"),
        ("prc-trademark-law", "effective-2027-01-01"),
        ("prc-anti-unfair-competition-law", "effective-2025-10-15"),
    }
    assert by_id["cn-enterprise-compliance-core"].members == []
    assert by_id["cn-labor-dispute-core"].members == []


def test_shared_anti_unfair_competition_law_is_one_identity_in_two_packs() -> None:
    _, catalog = _load_checked_in_catalog()
    matches = [
        item for item in catalog.entries if item.authority.authority_id == "prc-anti-unfair-competition-law"
    ]
    assert len(matches) == 1
    assert matches[0].version_id == "effective-2025-10-15"
    assert set(matches[0].pack_ids) == {
        "cn-intellectual-property-core",
        "cn-enterprise-compliance-core",
    }


def test_trademark_transition_tracks_current_and_promulgated_future_versions() -> None:
    _, catalog = _load_checked_in_catalog()
    versions = {
        item.version_id: item
        for item in catalog.entries
        if item.authority.authority_id == "prc-trademark-law"
    }
    assert set(versions) == {"effective-2019-11-01", "effective-2027-01-01"}

    current = versions["effective-2019-11-01"]
    future = versions["effective-2027-01-01"]
    assert current.status == VersionStatus.EFFECTIVE
    assert str(current.end_date_exclusive) == "2027-01-01"
    assert future.status == VersionStatus.NOT_YET_EFFECTIVE
    assert future.catalog_state == CatalogEntryState.PROMULGATED_NOT_YET_EFFECTIVE
    assert str(future.effective_date) == "2027-01-01"
    assert current.authority.document_number is None
    assert future.authority.document_number is None
    assert any("第七十七号" in source.name for source in future.source_refs)


def test_cybersecurity_catalog_uses_2026_effective_revision_not_stale_2016_text() -> None:
    _, catalog = _load_checked_in_catalog()
    [cybersecurity] = [
        item for item in catalog.entries if item.authority.authority_id == "prc-cybersecurity-law"
    ]
    assert cybersecurity.version_id == "effective-2026-01-01"
    assert cybersecurity.status == VersionStatus.EFFECTIVE
    assert str(cybersecurity.publication_date) == "2025-10-28"
    assert str(cybersecurity.effective_date) == "2026-01-01"


def test_labor_interpretation_partial_repeal_is_visible_and_blocks_uniform_full_text_import() -> None:
    _, catalog = _load_checked_in_catalog()
    interpretation_one = next(
        item
        for item in catalog.entries
        if item.authority.authority_id == "spc-labor-dispute-interpretation-1"
    )
    interpretation_two = next(
        item
        for item in catalog.entries
        if item.authority.authority_id == "spc-labor-dispute-interpretation-2"
    )
    assert interpretation_one.catalog_state == CatalogEntryState.BLOCKED
    assert interpretation_one.status == VersionStatus.AMENDED
    assert interpretation_one.blocking_issue
    assert interpretation_two.catalog_state == CatalogEntryState.VETTED_FOR_SNAPSHOT
    assert interpretation_two.status == VersionStatus.EFFECTIVE
    assert str(interpretation_two.effective_date) == "2025-09-01"


def test_every_catalog_source_host_and_role_is_registered() -> None:
    registry, catalog = _load_checked_in_catalog()
    for item in catalog.entries:
        for ref in item.source_refs:
            source = validate_official_source_ref(ref, registry)
            assert source.source_id


def test_cnipa_cannot_be_silently_promoted_to_primary_normative_source() -> None:
    registry = load_source_registry(_repo_root() / "legal_data" / "source_registry.json")
    ref = OfficialSourceRef(
        name="invalid primary use",
        url="https://www.cnipa.gov.cn/art/2026/6/26/art_3686_206940.html",
        role=SourceRole.PRIMARY,
    )
    with pytest.raises(LegalSourceRegistryError, match="does not allow role PRIMARY"):
        validate_official_source_ref(ref, registry)


def test_unregistered_legal_source_host_fails_closed() -> None:
    registry = load_source_registry(_repo_root() / "legal_data" / "source_registry.json")
    ref = OfficialSourceRef(
        name="commercial mirror",
        url="https://example.com/law",
        role=SourceRole.PRIMARY,
    )
    with pytest.raises(LegalSourceRegistryError, match="Unregistered official legal source host"):
        validate_official_source_ref(ref, registry)


def test_catalog_unknown_pack_reference_fails_closed(tmp_path: Path) -> None:
    repo_root = _repo_root()
    registry = load_source_registry(repo_root / "legal_data" / "source_registry.json")
    payload = json.loads(
        (repo_root / "legal_data" / "catalog" / "three-domain-core.json").read_text(encoding="utf-8")
    )
    payload["entries"][0]["pack_ids"] = ["cn-not-a-real-pack"]
    bad_catalog = tmp_path / "catalog.json"
    bad_catalog.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(OfficialCorpusCatalogError, match="unknown packs"):
        load_official_corpus_catalog(
            bad_catalog,
            registry=registry,
            corpus_root=repo_root / "legal_data",
        )


def test_stage6_seed_identities_are_not_duplicated_by_stage15_inventory() -> None:
    _, catalog = _load_checked_in_catalog()
    identities = {(item.authority.authority_id, item.version_id) for item in catalog.entries}
    assert ("prc-civil-code", "effective-2021-01-01") not in identities
    assert (
        "spc-civil-code-contract-general-interpretation",
        "effective-2023-12-05",
    ) not in identities
