from __future__ import annotations

from pathlib import Path

from app.legal.corpus_inventory import load_official_corpus_catalog
from app.legal.snapshot_targets import SnapshotTargetState, load_snapshot_targets
from app.legal.source_registry import load_source_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_labor_targets_are_all_ready_for_exact_full_text_freeze() -> None:
    root = _repo_root()
    registry = load_source_registry(root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=root / "legal_data",
    )
    targets = load_snapshot_targets(
        root / "legal_data" / "catalog" / "cn-labor-dispute-core.snapshot-targets.json",
        catalog=catalog,
        registry=registry,
    )

    by_identity = {(item.authority_id, item.version_id): item for item in targets.targets}
    assert set(by_identity) == {
        ("prc-labor-law", "effective-2018-12-29"),
        ("prc-labor-contract-law", "effective-2013-07-01"),
        ("prc-labor-dispute-mediation-arbitration-law", "effective-2008-05-01"),
        ("prc-social-insurance-law", "effective-2018-12-29"),
        ("spc-labor-dispute-interpretation-2", "effective-2025-09-01"),
    }
    assert all(item.state == SnapshotTargetState.READY_FOR_FREEZE for item in targets.targets)

    assert by_identity[("prc-labor-law", "effective-2018-12-29")].expected_article_count == 107
    assert by_identity[("prc-labor-dispute-mediation-arbitration-law", "effective-2008-05-01")].expected_article_count == 54
    assert by_identity[("prc-social-insurance-law", "effective-2018-12-29")].expected_article_count == 98
    assert by_identity[("spc-labor-dispute-interpretation-2", "effective-2025-09-01")].expected_article_count == 21

    labor_contract = by_identity[("prc-labor-contract-law", "effective-2013-07-01")]
    assert labor_contract.expected_article_count == 98
    assert str(labor_contract.snapshot_source_url) == (
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html"
    )
    assert labor_contract.supplemental_source_ref is not None
    assert labor_contract.supplemental_source_ref.role.value == "TEXT"


def test_partially_repealed_interpretation_one_stays_outside_snapshot_targets() -> None:
    root = _repo_root()
    registry = load_source_registry(root / "legal_data" / "source_registry.json")
    catalog = load_official_corpus_catalog(
        root / "legal_data" / "catalog" / "three-domain-core.json",
        registry=registry,
        corpus_root=root / "legal_data",
    )
    targets = load_snapshot_targets(
        root / "legal_data" / "catalog" / "cn-labor-dispute-core.snapshot-targets.json",
        catalog=catalog,
        registry=registry,
    )

    identities = {(item.authority_id, item.version_id) for item in targets.targets}
    assert ("spc-labor-dispute-interpretation-1", "effective-2021-01-01") not in identities
    interpretation_two = next(
        item for item in targets.targets if item.authority_id == "spc-labor-dispute-interpretation-2"
    )
    assert interpretation_two.state == SnapshotTargetState.READY_FOR_FREEZE
    assert interpretation_two.expected_article_count == 21
