from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from app.ai_audit import AiAuditValidationError, validate_model_output
from app.ai_audit_models import AuditContextPackage, AuditIssuePackage, ContractContextItem
from app.contract_models import SourceSpan
from app.legal.importer import import_manifest
from app.legal.parser import normalize_snapshot_text
from app.legal.retrieval_models import RetrievalCandidate, RetrievalResponse, RetrievalState
from app.models import SourceMethod
from app.storage import legal_db_path


def _sha(text: str) -> str:
    return hashlib.sha256(normalize_snapshot_text(text).encode("utf-8")).hexdigest()


def test_model_cannot_cite_retrieved_but_stale_legal_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    old_text = "第一章 测试\n\n第一条　旧版规则。\n"
    new_text = "第一章 测试\n\n第一条　新版规则。\n"
    (tmp_path / "old.txt").write_text(old_text, encoding="utf-8")
    (tmp_path / "new.txt").write_text(new_text, encoding="utf-8")

    authority = {
        "authority_id": "fictional-version-law",
        "title": "虚构版本法",
        "authority_type": "LAW",
        "issuing_body": "虚构机关",
        "document_number": "TEST-VERSION",
        "jurisdiction": "测试辖区",
    }

    def record(snapshot: str, text: str, version: str, effective: str, end: str | None) -> dict:
        return {
            "authority": authority,
            "version_id": version,
            "status": "EFFECTIVE",
            "publication_date": effective,
            "effective_date": effective,
            "end_date_exclusive": end,
            "repeal_date": None,
            "supersedes_version_id": None,
            "superseded_by_version_id": None,
            "coverage_type": "FULL_TEXT",
            "coverage_note": "fictional version guard fixture",
            "source_refs": [{"name": "fictional", "url": "https://example.invalid/version", "role": "PRIMARY"}],
            "snapshot_path": snapshot,
            "expected_source_sha256": _sha(text),
            "expected_article_count": 1,
            "parser": "chinese-articles-v1",
            "inclusion_reason": "version applicability regression fixture",
            "verified_on": "2026-08-15",
            "verification_note": "fictional",
        }

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "1.0.0",
                "records": [
                    record("old.txt", old_text, "v2020", "2020-01-01", "2022-01-01"),
                    record("new.txt", new_text, "v2022", "2022-01-01", None),
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    import_manifest(manifest, legal_db_path(), rebuild=True, allow_non_official_sources=True)

    stale_id = "legal:fictional-version-law:v2020:article-1"
    span = SourceSpan(
        page_number=1,
        evidence_ids=["contract-evidence-1"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="第一条 测试合同条款",
        char_start=0,
        char_end=10,
    )
    issue = AuditIssuePackage(
        issue_id="issue-version-guard",
        topic="版本测试",
        query_method="fixture",
        retrieval_query="版本测试",
        contract_object_ids=["clause-1"],
        contract_evidence_ids=["contract-evidence-1"],
        retrieval=RetrievalResponse(
            query="版本测试",
            as_of=date(2023, 1, 1),
            state=RetrievalState.OK,
            candidates=[
                RetrievalCandidate(
                    legal_evidence_id=stale_id,
                    authority_id="fictional-version-law",
                    authority_title="虚构版本法",
                    version_id="v2020",
                    article_id="article-1",
                    article_token="第一条",
                    article_text="第一条　旧版规则。",
                    coverage_type="FULL_TEXT",
                    effective_date=date(2020, 1, 1),
                    end_date_exclusive=date(2022, 1, 1),
                    exact_hit=True,
                    fused_score=1.0,
                )
            ],
        ),
    )
    context = AuditContextPackage(
        job_id=uuid4(),
        as_of=date(2023, 1, 1),
        contract_schema_version="1.0.0",
        contract_source_fingerprint="source",
        contract_content_fingerprint="content",
        contract_items=[
            ContractContextItem(
                canonical_object_id="clause-1",
                object_type="CLAUSE",
                text="第一条 测试合同条款",
                source_spans=[span],
                evidence_ids=["contract-evidence-1"],
            )
        ],
        issues=[issue],
        context_fingerprint="version-guard-context",
    )
    model_json = json.dumps(
        {
            "findings": [
                {
                    "client_finding_id": "STALE-1",
                    "state": "SUPPORTED_FINDING",
                    "risk_category": "版本测试",
                    "severity": "HIGH",
                    "title": "错误引用旧版本",
                    "reasoning_summary": "测试旧版本必须被后置校验拒绝。",
                    "suggestion": "测试。",
                    "issue_ids": ["issue-version-guard"],
                    "canonical_object_ids": ["clause-1"],
                    "contract_evidence_ids": ["contract-evidence-1"],
                    "legal_evidence_ids": [stale_id],
                    "review_reasons": [],
                }
            ]
        },
        ensure_ascii=False,
    )

    with pytest.raises(AiAuditValidationError, match="but v2022 applies"):
        validate_model_output(model_json, context)
