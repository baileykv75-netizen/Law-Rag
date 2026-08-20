from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.legal.corpus_packs import (
    CorpusPackError,
    CorpusPackStatus,
    discover_corpus_packs,
    load_corpus_pack,
)
from app.legal.importer import import_manifest
from app.legal.store import get_summary


def _legal_manifest(authority_id: str = "fictional-shared-law", version_id: str = "v1") -> dict:
    return {
        "manifest_version": "1.0.0",
        "records": [
            {
                "authority": {
                    "authority_id": authority_id,
                    "title": "虚构共享测试法",
                    "authority_type": "LAW",
                    "issuing_body": "虚构测试机关",
                    "document_number": "TEST-SHARED-001",
                    "jurisdiction": "测试辖区",
                },
                "version_id": version_id,
                "status": "EFFECTIVE",
                "publication_date": "2020-01-01",
                "effective_date": "2020-01-01",
                "end_date_exclusive": None,
                "repeal_date": None,
                "supersedes_version_id": None,
                "superseded_by_version_id": None,
                "coverage_type": "FULL_TEXT",
                "coverage_note": "fictional Stage 15.1 fixture",
                "source_refs": [
                    {
                        "name": "fictional source",
                        "url": "https://example.invalid/law",
                        "role": "PRIMARY",
                    }
                ],
                "snapshot_path": "source.txt",
                "expected_source_sha256": "0" * 64,
                "expected_article_count": 1,
                "parser": "chinese-articles-v1",
                "inclusion_reason": "fictional Stage 15.1 fixture",
                "verified_on": "2026-08-20",
                "verification_note": "fictional",
            }
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_pack(
    root: Path,
    pack_id: str,
    *,
    domain_tag: str,
    status: str = "DRAFT",
    authority_manifest_paths: list[str] | None = None,
) -> Path:
    path = root / "packs" / pack_id / "pack.json"
    _write_json(
        path,
        {
            "pack_schema_version": "1.0.0",
            "pack_id": pack_id,
            "pack_version": "0.1.0",
            "display_name": pack_id,
            "jurisdiction": "中华人民共和国",
            "description": "fictional Stage 15.1 pack",
            "domain_tags": [domain_tag],
            "status": status,
            "authority_manifest_paths": authority_manifest_paths or [],
        },
    )
    return path


def test_checked_in_stage15_pack_skeletons_are_discoverable_and_draft() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    packs = discover_corpus_packs(repo_root / "legal_data")
    assert {item.manifest.pack_id for item in packs} == {
        "cn-enterprise-compliance-core",
        "cn-intellectual-property-core",
        "cn-labor-dispute-core",
    }
    assert all(item.manifest.status == CorpusPackStatus.DRAFT for item in packs)
    assert all(item.members == [] for item in packs)


def test_future_domain_slug_does_not_require_a_python_enum_change(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path,
        "cn-construction-core",
        domain_tag="construction",
    )
    loaded = load_corpus_pack(pack_path, tmp_path)
    assert loaded.manifest.domain_tags == ["construction"]
    assert loaded.manifest.status == CorpusPackStatus.DRAFT


@pytest.mark.parametrize("domain_tag", ["Construction", "知识产权", "δοκιμή"])
def test_domain_slug_is_lowercase_ascii_and_fail_closed(tmp_path: Path, domain_tag: str) -> None:
    pack_path = _write_pack(
        tmp_path,
        "cn-invalid-domain",
        domain_tag=domain_tag,
    )
    with pytest.raises(CorpusPackError, match="lowercase ASCII slugs"):
        load_corpus_pack(pack_path, tmp_path)


def test_ready_pack_requires_at_least_one_authority_manifest(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path,
        "cn-empty-ready",
        domain_tag="future-domain",
        status="READY",
    )
    with pytest.raises(CorpusPackError, match="READY corpus packs"):
        load_corpus_pack(pack_path, tmp_path)


@pytest.mark.parametrize(
    "configured_path",
    [
        "../outside/manifest.json",
        "/absolute/manifest.json",
        "C:/absolute/manifest.json",
        "authorities\\bad\\manifest.json",
    ],
)
def test_pack_rejects_unsafe_authority_manifest_paths(tmp_path: Path, configured_path: str) -> None:
    pack_path = _write_pack(
        tmp_path,
        "cn-unsafe-pack",
        domain_tag="future-domain",
        authority_manifest_paths=[configured_path],
    )
    with pytest.raises(CorpusPackError):
        load_corpus_pack(pack_path, tmp_path)


def test_same_authority_version_can_belong_to_multiple_packs_without_source_duplication(tmp_path: Path) -> None:
    authority_path = tmp_path / "authorities" / "shared" / "manifest.json"
    _write_json(authority_path, _legal_manifest())
    reference = "authorities/shared/manifest.json"

    first_path = _write_pack(
        tmp_path,
        "cn-intellectual-property-core",
        domain_tag="intellectual-property",
        status="READY",
        authority_manifest_paths=[reference],
    )
    second_path = _write_pack(
        tmp_path,
        "cn-enterprise-compliance-core",
        domain_tag="enterprise-compliance",
        status="READY",
        authority_manifest_paths=[reference],
    )

    first = load_corpus_pack(first_path, tmp_path)
    second = load_corpus_pack(second_path, tmp_path)
    assert [(item.authority_id, item.version_id) for item in first.members] == [
        ("fictional-shared-law", "v1")
    ]
    assert [(item.authority_id, item.version_id) for item in second.members] == [
        ("fictional-shared-law", "v1")
    ]
    assert first.members[0].authority_manifest_path == second.members[0].authority_manifest_path


def test_duplicate_authority_version_inside_one_pack_fails_closed(tmp_path: Path) -> None:
    _write_json(tmp_path / "authorities" / "a" / "manifest.json", _legal_manifest())
    _write_json(tmp_path / "authorities" / "b" / "manifest.json", _legal_manifest())
    pack_path = _write_pack(
        tmp_path,
        "cn-duplicate-pack",
        domain_tag="future-domain",
        status="READY",
        authority_manifest_paths=[
            "authorities/a/manifest.json",
            "authorities/b/manifest.json",
        ],
    )
    with pytest.raises(CorpusPackError, match="duplicate authority/version identity"):
        load_corpus_pack(pack_path, tmp_path)


def test_legacy_stage6_seed_import_remains_compatible(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    db = tmp_path / "legal.db"
    report = import_manifest(manifest, db, rebuild=True)
    summary = get_summary(db)
    assert report.rejected_records == 0
    assert summary.authority_count == 2
    assert summary.version_count == 2
    assert summary.article_count == 15
