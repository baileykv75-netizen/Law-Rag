from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.legal.fulltext_snapshot_cli import FullTextSnapshotFreezeError, freeze_full_text_snapshot


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _numbered_text(count: int, *, changed_first: bool = False) -> str:
    lines = []
    for index in range(1, count + 1):
        body = "改变后的测试内容。" if changed_first and index == 1 else f"测试内容{index}。"
        lines.append(f"第{index}条　{body}")
    return "\n".join(lines) + "\n"


def _freeze(
    tmp_path: Path,
    *,
    target_set_name: str,
    authority_id: str,
    version_id: str,
    article_count: int,
    changed_first: bool = False,
):
    root = _repo_root()
    source = tmp_path / "official.txt"
    source.write_text(_numbered_text(article_count, changed_first=changed_first), encoding="utf-8")
    output = tmp_path / "frozen"
    return freeze_full_text_snapshot(
        catalog_path=root / "legal_data" / "catalog" / "three-domain-core.json",
        source_registry_path=root / "legal_data" / "source_registry.json",
        target_set_path=root / "legal_data" / "catalog" / target_set_name,
        authority_id=authority_id,
        version_id=version_id,
        source_file=source,
        output_dir=output,
    )


def test_freeze_writes_normalized_snapshot_and_stage6_manifest_idempotently(tmp_path: Path) -> None:
    first = _freeze(
        tmp_path,
        target_set_name="cn-intellectual-property-core.snapshot-targets.json",
        authority_id="prc-patent-law",
        version_id="effective-2021-06-01",
        article_count=82,
    )
    second = _freeze(
        tmp_path,
        target_set_name="cn-intellectual-property-core.snapshot-targets.json",
        authority_id="prc-patent-law",
        version_id="effective-2021-06-01",
        article_count=82,
    )

    assert first == second
    snapshot = Path(first["snapshot_path"])
    manifest_path = Path(first["manifest_path"])
    assert snapshot.read_text(encoding="utf-8").endswith("\n")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(payload["records"]) == 1
    record = payload["records"][0]
    assert record["authority"]["authority_id"] == "prc-patent-law"
    assert record["coverage_type"] == "FULL_TEXT"
    assert record["expected_article_count"] == 82
    assert record["expected_source_sha256"] == first["source_sha256"]


def test_freeze_refuses_to_overwrite_changed_snapshot_under_same_identity(tmp_path: Path) -> None:
    _freeze(
        tmp_path,
        target_set_name="cn-intellectual-property-core.snapshot-targets.json",
        authority_id="prc-patent-law",
        version_id="effective-2021-06-01",
        article_count=82,
    )
    with pytest.raises(FullTextSnapshotFreezeError, match="Refusing to overwrite different frozen corpus"):
        _freeze(
            tmp_path,
            target_set_name="cn-intellectual-property-core.snapshot-targets.json",
            authority_id="prc-patent-law",
            version_id="effective-2021-06-01",
            article_count=82,
            changed_first=True,
        )


def test_freeze_carries_supplemental_mohrss_text_source_into_manifest(tmp_path: Path) -> None:
    result = _freeze(
        tmp_path,
        target_set_name="cn-labor-dispute-core.snapshot-targets.json",
        authority_id="prc-labor-contract-law",
        version_id="effective-2013-07-01",
        article_count=98,
    )

    assert result["supplemental_text_source"] is True
    payload = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    refs = payload["records"][0]["source_refs"]
    assert [item["role"] for item in refs] == ["PRIMARY", "TEXT"]
    assert refs[-1]["url"].startswith("https://www.mohrss.gov.cn/")


def test_freeze_rejects_noncontiguous_article_sequence(tmp_path: Path) -> None:
    root = _repo_root()
    source = tmp_path / "bad.txt"
    source.write_text("第1条　甲。\n第3条　丙。\n", encoding="utf-8")
    with pytest.raises(FullTextSnapshotFreezeError, match="exactly contiguous"):
        freeze_full_text_snapshot(
            catalog_path=root / "legal_data" / "catalog" / "three-domain-core.json",
            source_registry_path=root / "legal_data" / "source_registry.json",
            target_set_path=root
            / "legal_data"
            / "catalog"
            / "cn-intellectual-property-core.snapshot-targets.json",
            authority_id="prc-patent-law",
            version_id="effective-2021-06-01",
            source_file=source,
            output_dir=tmp_path / "frozen",
        )
