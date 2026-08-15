from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.contract_models import (
    CanonicalContract,
    ExtractionConfidence,
    ExtractionProvenance,
    PartyMention,
    ResolutionState,
    SourceSpan,
    TitleCandidate,
)
from app.main import app
from app.models import SourceMethod
from app.storage import job_contract_path

client = TestClient(app)


def _fixture_contract() -> CanonicalContract:
    job_id = uuid4()
    title_span = SourceSpan(
        page_number=1,
        evidence_ids=["fixture-title"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="测试合同",
        char_start=0,
        char_end=4,
    )
    party_a_span = SourceSpan(
        page_number=1,
        evidence_ids=["fixture-a"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="甲方：甲公司",
        char_start=10,
        char_end=16,
    )
    party_b_span = SourceSpan(
        page_number=1,
        evidence_ids=["fixture-b"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="乙方：乙公司",
        char_start=20,
        char_end=26,
    )
    provenance = ExtractionProvenance(extractor_id="fixture", confidence=ExtractionConfidence.HIGH)
    return CanonicalContract(
        job_id=job_id,
        filename="fixture.pdf",
        source_fingerprint="fixture-source",
        evidence_unit_count=3,
        title_candidates=[
            TitleCandidate(
                candidate_id="title-001",
                text="测试合同",
                source_spans=[title_span],
                provenance=provenance,
            )
        ],
        parties=[
            PartyMention(
                mention_id="party-001",
                role_label="甲方",
                raw_name="甲公司",
                normalized_name="甲公司",
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[party_a_span],
                provenance=provenance,
            ),
            PartyMention(
                mention_id="party-002",
                role_label="乙方",
                raw_name="乙公司",
                normalized_name="乙公司",
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[party_b_span],
                provenance=provenance,
            ),
        ],
    )


def test_audit_rules_endpoint_requires_stage4_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()

    response = client.post(f"/api/documents/{job_id}/audit-rules")

    assert response.status_code == 404
    assert "Generate Stage 4 structure first" in response.json()["detail"]


def test_audit_rules_post_persists_and_get_returns_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    contract = _fixture_contract()
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    response = client.post(
        f"/api/documents/{contract.job_id}/audit-rules",
        params={"profile": "basic-bilateral-v1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["profile_id"] == "basic-bilateral-v1"
    assert body["counts"]["total"] > 0
    assert body["counts"]["passed"] >= 1
    assert (tmp_path / "jobs" / str(contract.job_id) / "audit-rules.json").exists()

    fetched = client.get(f"/api/documents/{contract.job_id}/audit-rules")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_unknown_audit_profile_is_explicit_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    contract = _fixture_contract()
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    response = client.post(
        f"/api/documents/{contract.job_id}/audit-rules",
        params={"profile": "does-not-exist"},
    )

    assert response.status_code == 422
    assert "Unknown audit profile" in response.json()["detail"]
