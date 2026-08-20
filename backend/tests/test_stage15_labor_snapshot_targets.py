from __future__ import annotations

from pathlib import Path

from app.legal.corpus_inventory import load_official_corpus_catalog
from app.legal.snapshot_targets import SnapshotTargetState, load_snapshot_targets
from app.legal.source_registry import load_source_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_checked_in_labor_targets_are_explicit_about_full_text_blocks() -> None:
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

    assert by_identity[("prc-labor-law", "effective-2018-12-29")].expected_article_count == 107
    assert by_identity[("prc-labor-dispute-mediation-arbitration-law", "effective-2008-05-01")].expected_article_count == 54
    assert by_identity[("prc-social-insurance-law", "effective-2018-12-29")].expected_article_count == 98
    assert by_identity[("spc-labor-dispute-interpretation-2", "effective-2025-09-01")].expected_article_count == 21

    labor_contract = by_identity[("prc-labor-contract-law", "effective-2013-07-01")]
    assert labor_contract.state == SnapshotTargetState.SOURCE_POLICY_BLOCKED
    assert labor_contract.expected_article_count == 98
    assert labor_contract.snapshot_source_url is None
    assert labor_contract.blocking_issue


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
