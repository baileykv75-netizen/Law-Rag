from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.audit_rules import run_audit_rules
from app.contract_models import (
    CanonicalContract,
    Clause,
    ExtractionConfidence,
    ExtractionProvenance,
    PartyMention,
    ResolutionState,
    SourceSpan,
    TitleCandidate,
)
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.main import app
from app.models import SourceMethod
from app.storage import job_contract_path, legal_db_path, legal_retrieval_index_path

client = TestClient(app)


def _prepare(tmp_path: Path, monkeypatch) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    provenance = ExtractionProvenance(extractor_id="fixture", confidence=ExtractionConfidence.HIGH)
    title_span = SourceSpan(
        page_number=1,
        evidence_ids=["api-title"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="测试服务合同",
        char_start=0,
        char_end=6,
    )
    party_a = SourceSpan(
        page_number=1,
        evidence_ids=["api-party-a"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="甲方：甲公司",
        char_start=10,
        char_end=16,
    )
    party_b = SourceSpan(
        page_number=1,
        evidence_ids=["api-party-b"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="乙方：乙公司",
        char_start=20,
        char_end=26,
    )
    clause_text = "第八条 违约责任\n乙方违约时支付合同金额50%的违约金。"
    clause_span = SourceSpan(
        page_number=2,
        evidence_ids=["api-clause-8"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=clause_text,
        char_start=0,
        char_end=len(clause_text),
    )
    contract = CanonicalContract(
        job_id=job_id,
        filename="api-fixture.pdf",
        source_fingerprint="api-source",
        evidence_unit_count=4,
        title_candidates=[
            TitleCandidate(
                candidate_id="title-api",
                text="测试服务合同",
                source_spans=[title_span],
                provenance=provenance,
            )
        ],
        clauses=[
            Clause(
                clause_id="clause-api-008",
                heading_token="第八条",
                heading_text="违约责任",
                body_text="乙方违约时支付合同金额50%的违约金。",
                level=1,
                page_start=2,
                page_end=2,
                source_spans=[clause_span],
                provenance=provenance,
            )
        ],
        parties=[
            PartyMention(
                mention_id="party-api-1",
                role_label="甲方",
                raw_name="甲公司",
                normalized_name="甲公司",
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[party_a],
                provenance=provenance,
            ),
            PartyMention(
                mention_id="party-api-2",
                role_label="乙方",
                raw_name="乙公司",
                normalized_name="乙公司",
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[party_b],
                provenance=provenance,
            ),
        ],
    )
    job_contract_path(job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(job_id)
    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(repo_root / "legal_data" / "seed" / "manifest.json", legal_db_path(), rebuild=True)
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())
    return contract


def test_deepseek_health_is_configuration_only(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    response = client.get("/api/ai/providers/health", params={"provider": "deepseek"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deepseek"
    assert body["configured"] is False
    assert body["model"] == "deepseek-v4-pro"


def test_unknown_primary_provider_is_explicit_error() -> None:
    response = client.get("/api/ai/providers/health", params={"provider": "unknown"})
    assert response.status_code == 422
    assert "Unknown primary audit provider" in response.json()["detail"]


def test_ai_audit_endpoint_requires_prior_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")
    response = client.post(
        f"/api/documents/{uuid4()}/ai-audit",
        json={"as_of": "2026-08-15", "provider": "fake", "use_semantic": False},
    )
    assert response.status_code == 409
    assert "Stage 4 contract.json" in response.json()["detail"]


def test_fake_ai_audit_api_persists_and_gets_report(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")

    response = client.post(
        f"/api/documents/{contract.job_id}/ai-audit",
        json={"as_of": "2026-08-15", "provider": "fake", "use_semantic": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["findings"]
    assert body["findings"][0]["legal_evidence_ids"]

    fetched = client.get(f"/api/documents/{contract.job_id}/ai-audit")
    assert fetched.status_code == 200
    assert fetched.json() == body
