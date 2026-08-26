from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.legal.importer import LegalImportError, import_manifest
from app.legal.parser import normalize_snapshot_text, parse_chinese_articles
from app.legal.store import get_evidence, get_summary, resolve_version
from app.main import app

client = TestClient(app)


def _sha(text: str) -> str:
    return hashlib.sha256(normalize_snapshot_text(text).encode("utf-8")).hexdigest()


def _authority(authority_id: str = "fictional-law", title: str = "虚构测试法") -> dict:
    return {
        "authority_id": authority_id,
        "title": title,
        "authority_type": "LAW",
        "issuing_body": "虚构测试机关",
        "document_number": "TEST-001",
        "jurisdiction": "测试辖区",
    }


def _record(
    *,
    snapshot_name: str,
    snapshot_text: str,
    version_id: str = "v1",
    effective_date: str = "2020-01-01",
    end_date_exclusive: str | None = None,
    authority_id: str = "fictional-law",
    title: str = "虚构测试法",
    expected_hash: str | None = None,
    article_count: int = 2,
) -> dict:
    return {
        "authority": _authority(authority_id, title),
        "version_id": version_id,
        "status": "EFFECTIVE",
        "publication_date": effective_date,
        "effective_date": effective_date,
        "end_date_exclusive": end_date_exclusive,
        "repeal_date": None,
        "supersedes_version_id": None,
        "superseded_by_version_id": None,
        "coverage_type": "FULL_TEXT",
        "coverage_note": "fictional deterministic fixture",
        "source_refs": [
            {
                "name": "fictional source",
                "url": "https://example.invalid/law",
                "role": "PRIMARY",
            }
        ],
        "snapshot_path": snapshot_name,
        "expected_source_sha256": expected_hash or _sha(snapshot_text),
        "expected_article_count": article_count,
        "parser": "chinese-articles-v1",
        "inclusion_reason": "fictional regression fixture",
        "verified_on": "2026-08-15",
        "verification_note": "fictional",
    }


def _write_manifest(tmp_path: Path, records: list[tuple[str, str, dict]]) -> Path:
    manifest_records = []
    for filename, text, record in records:
        (tmp_path / filename).write_text(text, encoding="utf-8")
        manifest_records.append(record)
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"manifest_version": "1.0.0", "records": manifest_records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _two_article_text(first: str = "第一条　甲。", second: str = "第二条　乙。") -> str:
    return f"第一章 测试\n\n{first}\n\n正文中引用第三条但这一行不是条文标题。\n\n{second}\n"


def test_article_parser_preserves_articles_and_does_not_split_inline_reference() -> None:
    parsed = parse_chinese_articles(
        _two_article_text(), authority_id="fictional-law", version_id="v1"
    )
    assert [item.article_token for item in parsed.articles] == ["第一条", "第二条"]
    assert "引用第三条" in parsed.articles[0].text
    assert parsed.articles[0].text.startswith("第一条　甲。")
    assert parsed.articles[0].heading_context[-1] == "第一章 测试"


def test_legal_evidence_ids_are_deterministic() -> None:
    first = parse_chinese_articles(_two_article_text(), authority_id="fictional-law", version_id="v1")
    second = parse_chinese_articles(_two_article_text(), authority_id="fictional-law", version_id="v1")
    assert [a.legal_evidence_id for a in first.articles] == [a.legal_evidence_id for a in second.articles]
    assert first.articles[0].legal_evidence_id == "legal:fictional-law:v1:article-1"


def test_manifest_rebuild_is_idempotent(tmp_path: Path) -> None:
    text = _two_article_text()
    record = _record(snapshot_name="law.txt", snapshot_text=text)
    manifest = _write_manifest(tmp_path, [("law.txt", text, record)])
    db = tmp_path / "legal.db"

    first = import_manifest(manifest, db, rebuild=True, allow_non_official_sources=True)
    evidence_first = get_evidence(db, "legal:fictional-law:v1:article-1")
    second = import_manifest(manifest, db, rebuild=True, allow_non_official_sources=True)
    evidence_second = get_evidence(db, "legal:fictional-law:v1:article-1")

    assert first.rejected_records == 0
    assert second.rejected_records == 0
    assert get_summary(db).article_count == 2
    assert evidence_first.article.model_dump() == evidence_second.article.model_dump()


def test_same_version_changed_source_hash_is_rejected(tmp_path: Path) -> None:
    original = _two_article_text()
    first_record = _record(snapshot_name="law.txt", snapshot_text=original)
    manifest = _write_manifest(tmp_path, [("law.txt", original, first_record)])
    db = tmp_path / "legal.db"
    import_manifest(manifest, db, allow_non_official_sources=True)

    changed = _two_article_text(first="第一条　内容已经改变。")
    changed_record = _record(snapshot_name="law.txt", snapshot_text=changed)
    manifest = _write_manifest(tmp_path, [("law.txt", changed, changed_record)])

    with pytest.raises(LegalImportError) as error:
        import_manifest(manifest, db, allow_non_official_sources=True)
    assert error.value.report is not None
    assert any(
        issue.code == "SOURCE_VERSION_IDENTITY_CONFLICT"
        for report in error.value.report.reports
        for issue in report.issues
    )
    assert get_evidence(db, "legal:fictional-law:v1:article-1").article.text.startswith("第一条　甲。")


def test_manifest_hash_mismatch_blocks_import(tmp_path: Path) -> None:
    text = _two_article_text()
    record = _record(
        snapshot_name="law.txt",
        snapshot_text=text,
        expected_hash="0" * 64,
    )
    manifest = _write_manifest(tmp_path, [("law.txt", text, record)])
    db = tmp_path / "legal.db"
    with pytest.raises(LegalImportError) as error:
        import_manifest(manifest, db, rebuild=True, allow_non_official_sources=True)
    assert any(
        issue.code == "SOURCE_HASH_MISMATCH"
        for report in error.value.report.reports
        for issue in report.issues
    )
    assert not db.exists()


def test_duplicate_authority_version_identity_fails_explicitly(tmp_path: Path) -> None:
    text = _two_article_text()
    record = _record(snapshot_name="law.txt", snapshot_text=text)
    manifest = _write_manifest(
        tmp_path,
        [("law.txt", text, record), ("law2.txt", text, {**record, "snapshot_path": "law2.txt"})],
    )
    with pytest.raises(LegalImportError, match="duplicate authority/version"):
        import_manifest(manifest, tmp_path / "legal.db", allow_non_official_sources=True)


def test_missing_required_version_metadata_is_rejected(tmp_path: Path) -> None:
    text = _two_article_text()
    record = _record(snapshot_name="law.txt", snapshot_text=text)
    record.pop("effective_date")
    manifest = _write_manifest(tmp_path, [("law.txt", text, record)])
    with pytest.raises(LegalImportError, match="Malformed legal manifest"):
        import_manifest(manifest, tmp_path / "legal.db", allow_non_official_sources=True)


def test_version_resolution_effective_no_applicable_and_historical(tmp_path: Path) -> None:
    old_text = _two_article_text(first="第一条　旧版。")
    new_text = _two_article_text(first="第一条　新版。")
    old = _record(
        snapshot_name="old.txt",
        snapshot_text=old_text,
        version_id="v2020",
        effective_date="2020-01-01",
        end_date_exclusive="2022-01-01",
    )
    new = _record(
        snapshot_name="new.txt",
        snapshot_text=new_text,
        version_id="v2022",
        effective_date="2022-01-01",
    )
    manifest = _write_manifest(tmp_path, [("old.txt", old_text, old), ("new.txt", new_text, new)])
    db = tmp_path / "legal.db"
    import_manifest(manifest, db, rebuild=True, allow_non_official_sources=True)

    assert resolve_version(db, "fictional-law", __import__("datetime").date(2019, 1, 1)).state.value == "NO_APPLICABLE_VERSION"
    resolved_old = resolve_version(db, "fictional-law", __import__("datetime").date(2021, 1, 1))
    resolved_new = resolve_version(db, "fictional-law", __import__("datetime").date(2023, 1, 1))
    assert resolved_old.version and resolved_old.version.version_id == "v2020"
    assert resolved_new.version and resolved_new.version.version_id == "v2022"
    assert get_evidence(db, "legal:fictional-law:v2020:article-1").article.text.startswith("第一条　旧版。")


def test_overlapping_versions_return_ambiguous(tmp_path: Path) -> None:
    first_text = _two_article_text(first="第一条　甲版。")
    second_text = _two_article_text(first="第一条　乙版。")
    first = _record(
        snapshot_name="a.txt",
        snapshot_text=first_text,
        version_id="v1",
        effective_date="2020-01-01",
        end_date_exclusive="2025-01-01",
    )
    second = _record(
        snapshot_name="b.txt",
        snapshot_text=second_text,
        version_id="v2",
        effective_date="2024-01-01",
    )
    manifest = _write_manifest(tmp_path, [("a.txt", first_text, first), ("b.txt", second_text, second)])
    db = tmp_path / "legal.db"
    report = import_manifest(manifest, db, rebuild=True, allow_non_official_sources=True)
    resolution = resolve_version(db, "fictional-law", __import__("datetime").date(2024, 6, 1))
    assert resolution.state.value == "AMBIGUOUS"
    assert set(resolution.candidate_version_ids) == {"v1", "v2"}
    assert any(item.interval_conflicts for item in report.reports)


def test_transaction_rolls_back_when_later_record_conflicts(tmp_path: Path) -> None:
    text_a = _two_article_text(first="第一条　A。")
    text_b = _two_article_text(first="第一条　B。")
    first = _record(snapshot_name="a.txt", snapshot_text=text_a, version_id="v1")
    second = _record(
        snapshot_name="b.txt",
        snapshot_text=text_b,
        version_id="v2",
        effective_date="2021-01-01",
        title="同一ID却不同标题",
    )
    manifest = _write_manifest(tmp_path, [("a.txt", text_a, first), ("b.txt", text_b, second)])
    db = tmp_path / "legal.db"
    with pytest.raises(LegalImportError):
        import_manifest(manifest, db, allow_non_official_sources=True)
    assert get_summary(db).authority_count == 0
    assert get_summary(db).article_count == 0


def test_malformed_snapshot_fails_explicitly(tmp_path: Path) -> None:
    text = "这不是带有条文标题的法源文本。"
    record = _record(snapshot_name="bad.txt", snapshot_text=text, article_count=1)
    manifest = _write_manifest(tmp_path, [("bad.txt", text, record)])
    with pytest.raises(LegalImportError) as error:
        import_manifest(manifest, tmp_path / "legal.db", rebuild=True, allow_non_official_sources=True)
    assert any(
        issue.code == "ARTICLE_PARSE_FAILED"
        for report in error.value.report.reports
        for issue in report.issues
    )


def test_real_curated_seed_manifest_validates_and_rebuilds(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    db = tmp_path / "legal.db"
    report = import_manifest(manifest, db, rebuild=True)
    summary = get_summary(db)
    assert report.rejected_records == 0
    assert summary.authority_count == 2
    assert summary.version_count == 2
    assert summary.article_count == 15
    assert summary.excerpt_version_count == 2
    evidence = get_evidence(db, "legal:prc-civil-code:effective-2021-01-01:article-585")
    assert evidence.article.article_token == "第五百八十五条"
    assert "违约金" in evidence.article.text


def test_legal_api_summary_evidence_and_as_of_resolution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    db = tmp_path / "legal" / "legal.db"
    import_manifest(manifest, db, rebuild=True)

    summary = client.get("/api/legal/summary")
    assert summary.status_code == 200
    assert summary.json()["article_count"] == 15

    authorities = client.get("/api/legal/authorities")
    assert authorities.status_code == 200
    assert len(authorities.json()) == 2

    articles = client.get("/api/legal/articles", params={"query": "违约金", "limit": 5})
    assert articles.status_code == 200, articles.text
    assert articles.json()
    assert any("违约金" in item["article"]["text"] for item in articles.json())

    evidence_id = "legal:prc-civil-code:effective-2021-01-01:article-586"
    evidence = client.get(f"/api/legal/evidence/{evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["article"]["article_token"] == "第五百八十六条"

    resolved = client.get(
        "/api/legal/resolve/prc-civil-code",
        params={"as_of": "2026-08-15", "article_token": "第五百八十五条"},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["resolution"]["state"] == "RESOLVED"
    assert body["resolution"]["version"]["version_id"] == "effective-2021-01-01"
    assert body["article"]["legal_evidence_id"].endswith(":article-585")
