from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.legal.importer import LegalImportError, import_manifest
from app.legal.parser import normalize_snapshot_text
from app.legal.store import get_summary


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha(text: str) -> str:
    return hashlib.sha256(normalize_snapshot_text(text).encode("utf-8")).hexdigest()


def _snapshot_text() -> str:
    return "第一章 测试\n\n第一条　甲。\n\n第二条　乙。\n"


def _record(source_refs: list[dict]) -> dict:
    text = _snapshot_text()
    return {
        "authority": {
            "authority_id": "stage15-source-policy-fixture",
            "title": "Stage 15 来源策略测试法",
            "authority_type": "LAW",
            "issuing_body": "全国人民代表大会常务委员会",
            "document_number": "TEST-STAGE15-2B",
            "jurisdiction": "中华人民共和国",
        },
        "version_id": "effective-2026-01-01",
        "status": "EFFECTIVE",
        "publication_date": "2025-12-31",
        "effective_date": "2026-01-01",
        "end_date_exclusive": None,
        "repeal_date": None,
        "supersedes_version_id": None,
        "superseded_by_version_id": None,
        "coverage_type": "FULL_TEXT",
        "coverage_note": "Stage 15.2B deterministic source-policy fixture.",
        "source_refs": source_refs,
        "snapshot_path": "fixture.txt",
        "expected_source_sha256": _sha(text),
        "expected_article_count": 2,
        "parser": "chinese-articles-v1",
        "inclusion_reason": "Regression coverage for registry-aware official-source validation.",
        "verified_on": "2026-08-20",
        "verification_note": "Synthetic text; official URLs are used only to exercise source-role policy.",
    }


def _manifest(tmp_path: Path, source_refs: list[dict]) -> Path:
    (tmp_path / "fixture.txt").write_text(_snapshot_text(), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "1.0.0",
                "records": [_record(source_refs)],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def test_registry_aware_import_accepts_npc_primary_and_cnipa_text(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        [
            {
                "name": "中国人大网 PRIMARY",
                "url": "https://www.npc.gov.cn/c2/c30834/202011/t20201119_308800.html",
                "role": "PRIMARY",
            },
            {
                "name": "国家知识产权局 TEXT",
                "url": "https://www.cnipa.gov.cn/art/2020/11/23/art_2197_155169.html",
                "role": "TEXT",
            },
        ],
    )

    db = tmp_path / "legal.db"
    report = import_manifest(
        manifest,
        db,
        rebuild=True,
        source_registry_path=_repo_root() / "legal_data" / "source_registry.json",
    )

    assert report.rejected_records == 0
    assert report.imported_records == 1
    assert report.reports[0].source_recognized is True
    assert get_summary(db).article_count == 2


def test_registry_aware_import_rejects_cnipa_primary(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        [
            {
                "name": "CNIPA must not become PRIMARY",
                "url": "https://www.cnipa.gov.cn/art/2026/6/26/art_3686_206940.html",
                "role": "PRIMARY",
            }
        ],
    )

    db = tmp_path / "legal.db"
    with pytest.raises(LegalImportError) as error:
        import_manifest(
            manifest,
            db,
            rebuild=True,
            source_registry_path=_repo_root() / "legal_data" / "source_registry.json",
        )

    assert error.value.report is not None
    issues = [issue for item in error.value.report.reports for issue in item.issues]
    assert any(issue.code == "INVALID_OFFICIAL_SOURCE_REF" for issue in issues)
    assert any("does not allow role PRIMARY" in issue.message for issue in issues)
    assert not db.exists()


def test_stage6_seed_keeps_legacy_source_validation_when_registry_is_omitted(tmp_path: Path) -> None:
    manifest = _repo_root() / "legal_data" / "seed" / "manifest.json"
    db = tmp_path / "legal.db"

    report = import_manifest(manifest, db, rebuild=True)
    summary = get_summary(db)

    assert report.rejected_records == 0
    assert summary.authority_count == 2
    assert summary.version_count == 2
    assert summary.article_count == 15
    assert summary.excerpt_version_count == 2
