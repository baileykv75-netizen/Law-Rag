from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.legal.corpus_inventory import CatalogEntryState, PlannedLegalVersion
from app.legal.fulltext_snapshot import FullTextSnapshotError, build_full_text_manifest_record
from app.legal.models import CoverageType, LegalAuthority, OfficialSourceRef, SourceRole, VersionStatus
from app.legal.parser import normalize_snapshot_text, sha256_text
from app.legal.source_registry import load_source_registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _registry():
    return load_source_registry(_repo_root() / "legal_data" / "source_registry.json")


def _entry(
    *,
    catalog_state: CatalogEntryState = CatalogEntryState.VETTED_FOR_SNAPSHOT,
    source_refs: list[OfficialSourceRef] | None = None,
) -> PlannedLegalVersion:
    blocked = catalog_state == CatalogEntryState.BLOCKED
    return PlannedLegalVersion(
        authority=LegalAuthority(
            authority_id="stage15-fulltext-fixture",
            title="Stage 15 全文冻结测试法",
            authority_type="LAW",
            issuing_body="全国人民代表大会常务委员会",
            document_number="TEST-STAGE15-FULLTEXT",
        ),
        version_id="effective-2026-01-01",
        status=VersionStatus.EFFECTIVE,
        publication_date=date(2025, 12, 31),
        effective_date=date(2026, 1, 1),
        end_date_exclusive=None,
        pack_ids=["cn-enterprise-compliance-core"],
        source_refs=source_refs
        or [
            OfficialSourceRef(
                name="中国人大网测试来源",
                url="https://www.npc.gov.cn/c2/c30834/example.html",
                role=SourceRole.PRIMARY,
            )
        ],
        target_coverage=CoverageType.FULL_TEXT,
        catalog_state=catalog_state,
        notes="Synthetic Stage 15.2B full-text freezing fixture.",
        blocking_issue="Synthetic paragraph-level partial repeal." if blocked else None,
    )


def _text() -> str:
    return "第一章 测试\n\n第一条　甲。\n\n第二条　乙。\n\n第三条　丙。\n"


def test_build_full_text_record_pins_hash_count_and_stage6_manifest_shape() -> None:
    entry = _entry()
    record = build_full_text_manifest_record(
        entry,
        snapshot_text=_text(),
        snapshot_path="snapshots/stage15-fulltext-fixture.txt",
        snapshot_source_url=str(entry.source_refs[0].url),
        expected_article_count=3,
        registry=_registry(),
        verified_on=date(2026, 8, 20),
    )

    assert record.coverage_type == CoverageType.FULL_TEXT
    assert record.expected_article_count == 3
    assert record.expected_source_sha256 == sha256_text(normalize_snapshot_text(_text()))
    assert record.snapshot_path == "snapshots/stage15-fulltext-fixture.txt"
    assert record.status == VersionStatus.EFFECTIVE
    assert "contiguous article ordinals 1-3" in (record.verification_note or "")


def test_full_text_record_rejects_missing_article_ordinal() -> None:
    entry = _entry()
    text = "第一条　甲。\n第三条　丙。\n"
    with pytest.raises(FullTextSnapshotError, match="exactly contiguous"):
        build_full_text_manifest_record(
            entry,
            snapshot_text=text,
            snapshot_path="fixture.txt",
            snapshot_source_url=str(entry.source_refs[0].url),
            expected_article_count=3,
            registry=_registry(),
            verified_on=date(2026, 8, 20),
        )


def test_snapshot_source_must_be_vetted_primary_or_text_ref() -> None:
    metadata_ref = OfficialSourceRef(
        name="人大 metadata only",
        url="https://www.npc.gov.cn/c2/c30834/metadata.html",
        role=SourceRole.METADATA,
    )
    primary_ref = OfficialSourceRef(
        name="人大 primary",
        url="https://www.npc.gov.cn/c2/c30834/primary.html",
        role=SourceRole.PRIMARY,
    )
    entry = _entry(source_refs=[primary_ref, metadata_ref])

    with pytest.raises(FullTextSnapshotError, match="cannot supply normative full text"):
        build_full_text_manifest_record(
            entry,
            snapshot_text=_text(),
            snapshot_path="fixture.txt",
            snapshot_source_url=str(metadata_ref.url),
            expected_article_count=3,
            registry=_registry(),
            verified_on=date(2026, 8, 20),
        )


def test_blocked_catalog_entry_cannot_be_frozen_as_uniform_full_text() -> None:
    entry = _entry(catalog_state=CatalogEntryState.BLOCKED)

    with pytest.raises(FullTextSnapshotError, match="BLOCKED"):
        build_full_text_manifest_record(
            entry,
            snapshot_text=_text(),
            snapshot_path="fixture.txt",
            snapshot_source_url=str(entry.source_refs[0].url),
            expected_article_count=3,
            registry=_registry(),
            verified_on=date(2026, 8, 20),
        )


def test_snapshot_path_rejects_traversal() -> None:
    entry = _entry()
    with pytest.raises(FullTextSnapshotError, match="relative"):
        build_full_text_manifest_record(
            entry,
            snapshot_text=_text(),
            snapshot_path="../outside.txt",
            snapshot_source_url=str(entry.source_refs[0].url),
            expected_article_count=3,
            registry=_registry(),
            verified_on=date(2026, 8, 20),
        )
