from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.legal.corpus_inventory import CatalogEntryState, PlannedLegalVersion
from app.legal.fulltext_snapshot import FullTextSnapshotError, build_full_text_manifest_record
from app.legal.models import CoverageType, LegalAuthority, OfficialSourceRef, SourceRole, VersionStatus
from app.legal.source_registry import LegalSourceRegistryError, load_source_registry, validate_official_source_ref


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _registry():
    return load_source_registry(_repo_root() / "legal_data" / "source_registry.json")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm",
        "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/fl/202011/t20201102_394622.html",
        "https://www.ncac.gov.cn/xxfb/flfg/flfg_532/202103/t20210309_50530.html",
    ],
)
def test_new_official_text_carriers_are_text_allowed_but_primary_forbidden(url: str) -> None:
    registry = _registry()
    text_ref = OfficialSourceRef(name="official text carrier", url=url, role=SourceRole.TEXT)
    assert validate_official_source_ref(text_ref, registry).primary_normative_source_allowed is False

    primary_ref = OfficialSourceRef(name="invalid primary", url=url, role=SourceRole.PRIMARY)
    with pytest.raises(LegalSourceRegistryError, match="does not allow role PRIMARY"):
        validate_official_source_ref(primary_ref, registry)


def _entry() -> PlannedLegalVersion:
    return PlannedLegalVersion(
        authority=LegalAuthority(
            authority_id="supplemental-text-fixture",
            title="补充全文来源测试法",
            authority_type="LAW",
            issuing_body="全国人民代表大会常务委员会",
            document_number="TEST-SUPPLEMENTAL",
        ),
        version_id="effective-2026-01-01",
        status=VersionStatus.EFFECTIVE,
        publication_date=date(2025, 12, 31),
        effective_date=date(2026, 1, 1),
        pack_ids=["cn-enterprise-compliance-core"],
        source_refs=[
            OfficialSourceRef(
                name="人大规范性来源",
                url="https://www.npc.gov.cn/c2/c30834/source.html",
                role=SourceRole.PRIMARY,
            )
        ],
        target_coverage=CoverageType.FULL_TEXT,
        catalog_state=CatalogEntryState.VETTED_FOR_SNAPSHOT,
        notes="Synthetic supplemental TEXT-source fixture.",
    )


def test_manifest_record_keeps_primary_and_adds_supplemental_text_carrier() -> None:
    supplemental = OfficialSourceRef(
        name="中央网信办全文承载",
        url="https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm",
        role=SourceRole.TEXT,
    )
    record = build_full_text_manifest_record(
        _entry(),
        snapshot_text="第一条　甲。\n第二条　乙。\n",
        snapshot_path="snapshot.txt",
        snapshot_source_url=str(supplemental.url),
        supplemental_source_ref=supplemental,
        expected_article_count=2,
        registry=_registry(),
        verified_on=date(2026, 8, 20),
    )

    assert [ref.role for ref in record.source_refs] == [SourceRole.PRIMARY, SourceRole.TEXT]
    assert str(record.source_refs[-1].url) == str(supplemental.url)


def test_manifest_record_rejects_supplemental_primary_even_on_registered_host() -> None:
    supplemental = OfficialSourceRef(
        name="不允许的新 PRIMARY",
        url="https://www.cac.gov.cn/2025-12/29/c_1768735112911946.htm",
        role=SourceRole.PRIMARY,
    )
    with pytest.raises(FullTextSnapshotError, match="Supplemental full-text sources may use TEXT only"):
        build_full_text_manifest_record(
            _entry(),
            snapshot_text="第一条　甲。\n第二条　乙。\n",
            snapshot_path="snapshot.txt",
            snapshot_source_url=str(supplemental.url),
            supplemental_source_ref=supplemental,
            expected_article_count=2,
            registry=_registry(),
            verified_on=date(2026, 8, 20),
        )
