from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.audit_planner import build_planner_input
from app.audit_planner_provider import AuditPlannerProviderError, FakeAuditPlannerProvider
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
from app.models import SourceMethod
from app.storage import job_contract_path


def _prepare(tmp_path: Path, monkeypatch) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    provenance = ExtractionProvenance(extractor_id="planner-hardening", confidence=ExtractionConfidence.HIGH)
    title_span = SourceSpan(
        page_number=1,
        evidence_ids=["evidence-title"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="技术服务合同",
        char_start=0,
        char_end=6,
    )
    party_span = SourceSpan(
        page_number=1,
        evidence_ids=["evidence-party"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote="甲方：甲公司",
        char_start=10,
        char_end=16,
    )
    clause_text = "乙方提供软件开发和技术服务，项目成果归属按本合同约定执行。"
    clause_span = SourceSpan(
        page_number=2,
        evidence_ids=["evidence-service"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=f"第一条 服务内容\n{clause_text}",
        char_start=0,
        char_end=len(clause_text) + 8,
    )
    contract = CanonicalContract(
        job_id=uuid4(),
        filename="planner-hardening.pdf",
        source_fingerprint="planner-hardening-source",
        evidence_unit_count=3,
        title_candidates=[
            TitleCandidate(
                candidate_id="title-001",
                text="技术服务合同",
                source_spans=[title_span],
                provenance=provenance,
            )
        ],
        clauses=[
            Clause(
                clause_id="clause-001",
                heading_token="第一条",
                heading_text="服务内容",
                body_text=clause_text,
                level=1,
                page_start=2,
                page_end=2,
                source_spans=[clause_span],
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
                source_spans=[party_span],
                provenance=provenance,
            )
        ],
    )
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(contract.job_id)
    return contract


def test_planner_input_contains_canonical_global_facts(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    planner_input = build_planner_input(contract.job_id)
    facts = {item.fact_id: item for item in planner_input.global_facts}

    assert facts["title-001"].fact_type == "TITLE"
    assert facts["title-001"].value == "技术服务合同"
    assert facts["title-001"].evidence_ids == ["evidence-title"]
    assert facts["party-001"].fact_type == "PARTY"
    assert facts["party-001"].label == "甲方"
    assert facts["party-001"].value == "甲公司"
    assert facts["party-001"].evidence_ids == ["evidence-party"]


def test_fake_planner_is_disabled_unless_explicitly_enabled(tmp_path: Path, monkeypatch) -> None:
    contract = _prepare(tmp_path, monkeypatch)
    planner_input = build_planner_input(contract.job_id)
    monkeypatch.delenv("LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER", raising=False)

    with pytest.raises(AuditPlannerProviderError, match="Fake Audit Planner is disabled"):
        FakeAuditPlannerProvider().generate(planner_input)

    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER", "1")
    result = FakeAuditPlannerProvider().generate(planner_input)
    assert result.provider == "fake"
    assert result.model == "deterministic-stage13b-planner-v1"
