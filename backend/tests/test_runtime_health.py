from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from app.legal.importer import import_manifest
from app.legal.parser import normalize_snapshot_text
from app.legal.retrieval import build_retrieval_index
from app.runtime_health import inspect_runtime_health
from app.runtime_health_models import RuntimeHealthState


def _sha(text: str) -> str:
    return hashlib.sha256(normalize_snapshot_text(text).encode("utf-8")).hexdigest()


def _write_legal_manifest(tmp_path: Path) -> Path:
    text = "第一章 测试\n\n第一条　甲。\n\n第二条　乙。\n"
    (tmp_path / "law.txt").write_text(text, encoding="utf-8")
    payload = {
        "manifest_version": "1.0.0",
        "records": [
            {
                "authority": {
                    "authority_id": "runtime-health-law",
                    "title": "虚构运行时测试法",
                    "authority_type": "LAW",
                    "issuing_body": "虚构测试机关",
                    "document_number": "HEALTH-001",
                    "jurisdiction": "测试辖区",
                },
                "version_id": "v1",
                "status": "EFFECTIVE",
                "publication_date": "2020-01-01",
                "effective_date": "2020-01-01",
                "end_date_exclusive": None,
                "repeal_date": None,
                "supersedes_version_id": None,
                "superseded_by_version_id": None,
                "coverage_type": "FULL_TEXT",
                "coverage_note": "fictional runtime-health fixture",
                "source_refs": [
                    {
                        "name": "fictional source",
                        "url": "https://example.invalid/runtime-health-law",
                        "role": "PRIMARY",
                    }
                ],
                "snapshot_path": "law.txt",
                "expected_source_sha256": _sha(text),
                "expected_article_count": 2,
                "parser": "chinese-articles-v1",
                "inclusion_reason": "fictional runtime-health regression fixture",
                "verified_on": "2026-08-15",
                "verification_note": "fictional",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _check(report, check_id: str):
    return next(item for item in report.checks if item.check_id == check_id)


def test_missing_optional_stores_are_explicit_without_blocking_base_app(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(runtime))
    monkeypatch.delenv("LAW_RAG_LEGAL_DB", raising=False)
    monkeypatch.delenv("LAW_RAG_RETRIEVAL_DB", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    report = inspect_runtime_health()

    assert report.base_app_ready is True
    assert _check(report, "legal-database").state == RuntimeHealthState.MISSING
    assert _check(report, "retrieval-database").state == RuntimeHealthState.MISSING
    assert _check(report, "deepseek-provider").state == RuntimeHealthState.OPTIONAL_NOT_CONFIGURED
    assert _check(report, "kimi-provider").state == RuntimeHealthState.OPTIONAL_NOT_CONFIGURED
    assert not runtime.exists(), "health inspection must not create the runtime directory"


def test_healthy_legal_and_retrieval_stores_are_read_only_and_do_not_leak_keys(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_legal_manifest(tmp_path)
    legal_db = tmp_path / "legal.db"
    retrieval_db = tmp_path / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True, allow_non_official_sources=True)
    build_retrieval_index(legal_db, retrieval_db)
    legal_before = legal_db.read_bytes()
    retrieval_before = retrieval_db.read_bytes()

    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("LAW_RAG_LEGAL_DB", str(legal_db))
    monkeypatch.setenv("LAW_RAG_RETRIEVAL_DB", str(retrieval_db))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-super-secret-value")
    monkeypatch.setenv("MOONSHOT_API_KEY", "kimi-super-secret-value")

    report = inspect_runtime_health()
    rendered = report.model_dump_json()

    assert _check(report, "legal-database").state == RuntimeHealthState.OK
    assert _check(report, "retrieval-database").state == RuntimeHealthState.OK
    assert _check(report, "deepseek-provider").state == RuntimeHealthState.OK
    assert _check(report, "kimi-provider").state == RuntimeHealthState.OK
    assert "deepseek-super-secret-value" not in rendered
    assert "kimi-super-secret-value" not in rendered
    assert legal_db.read_bytes() == legal_before
    assert retrieval_db.read_bytes() == retrieval_before


def test_corrupt_databases_are_reported_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    legal_db = tmp_path / "legal.db"
    retrieval_db = tmp_path / "retrieval.db"
    legal_db.write_bytes(b"not a sqlite database\x00private")
    retrieval_db.write_bytes(b"also broken\x00private")
    legal_before = legal_db.read_bytes()
    retrieval_before = retrieval_db.read_bytes()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("LAW_RAG_LEGAL_DB", str(legal_db))
    monkeypatch.setenv("LAW_RAG_RETRIEVAL_DB", str(retrieval_db))

    report = inspect_runtime_health()

    assert _check(report, "legal-database").state == RuntimeHealthState.CORRUPT
    assert _check(report, "retrieval-database").state == RuntimeHealthState.CORRUPT
    assert legal_db.read_bytes() == legal_before
    assert retrieval_db.read_bytes() == retrieval_before


def test_retrieval_fingerprint_mismatch_is_stale_not_silently_rebuilt(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_legal_manifest(tmp_path)
    legal_db = tmp_path / "legal.db"
    retrieval_db = tmp_path / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True, allow_non_official_sources=True)
    build_retrieval_index(legal_db, retrieval_db)
    retrieval_before = retrieval_db.read_bytes()

    with sqlite3.connect(legal_db) as connection:
        connection.execute(
            "UPDATE legal_articles SET text_sha256 = ? WHERE legal_evidence_id = ?",
            ("f" * 64, "legal:runtime-health-law:v1:article-1"),
        )
        connection.commit()

    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("LAW_RAG_LEGAL_DB", str(legal_db))
    monkeypatch.setenv("LAW_RAG_RETRIEVAL_DB", str(retrieval_db))

    report = inspect_runtime_health()

    assert _check(report, "legal-database").state == RuntimeHealthState.OK
    assert _check(report, "retrieval-database").state == RuntimeHealthState.STALE
    assert retrieval_db.read_bytes() == retrieval_before


def test_invalid_provider_base_url_is_reported_without_network_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "not-a-url")

    report = inspect_runtime_health()

    deepseek = _check(report, "deepseek-provider")
    assert deepseek.state == RuntimeHealthState.MISCONFIGURED
    assert deepseek.metadata["configured"] is True
    assert "secret" not in report.model_dump_json()
