from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from app.agent_tools import execute_agent_action
from app.contract_models import (
    CanonicalContract,
    Clause,
    ExtractionConfidence,
    ExtractionProvenance,
    SourceSpan,
)
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.models import SourceMethod
from app.review_comparison_models import (
    AgentActionRecord,
    AgentActionState,
    AgentToolName,
)
from app.storage import job_contract_path, legal_db_path, legal_retrieval_index_path


def _contract() -> CanonicalContract:
    job_id = uuid4()
    provenance = ExtractionProvenance(
        extractor_id="test",
        confidence=ExtractionConfidence.HIGH,
    )
    clause_1 = Clause(
        clause_id="clause-001",
        heading_token="第一条",
        heading_text="违约责任",
        body_text="逾期履行承担违约责任。",
        level=1,
        page_start=1,
        page_end=1,
        source_spans=[
            SourceSpan(
                page_number=1,
                evidence_ids=["E-NATIVE-1"],
                source_method=SourceMethod.NATIVE_PDF_TEXT,
                quote="逾期履行承担违约责任。",
                char_start=0,
                char_end=12,
            )
        ],
        provenance=provenance,
    )
    clause_2 = Clause(
        clause_id="clause-002",
        heading_token="第二条",
        heading_text="违约金",
        body_text="每日按合同价款百分之一支付违约金。",
        level=1,
        page_start=2,
        page_end=2,
        source_spans=[
            SourceSpan(
                page_number=2,
                evidence_ids=["E-OCR-2"],
                source_method=SourceMethod.OCR,
                quote="每日按合同价款百分之一支付违约金。",
                bbox=[10, 20, 300, 70],
                confidence=0.86,
            )
        ],
        provenance=provenance,
    )
    return CanonicalContract(
        job_id=job_id,
        filename="fictional-contract.pdf",
        source_fingerprint="source-fingerprint",
        evidence_unit_count=2,
        clauses=[clause_1, clause_2],
    )


def _write_contract(tmp_path: Path, monkeypatch) -> CanonicalContract:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    contract = _contract()
    path = job_contract_path(contract.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    return contract


def _action(tool: AgentToolName, *, input_ids=None, arguments=None, cycle: int = 1) -> AgentActionRecord:
    return AgentActionRecord(
        action_id=f"action-{tool.value}",
        cycle=cycle,
        tool_name=tool,
        state=AgentActionState.REQUESTED,
        reason="test",
        input_evidence_ids=input_ids or [],
        normalized_arguments=arguments or {},
    )


def test_inspect_contract_evidence_returns_only_known_canonical_spans(tmp_path: Path, monkeypatch) -> None:
    contract = _write_contract(tmp_path, monkeypatch)
    result = execute_agent_action(
        contract.job_id,
        _action(AgentToolName.INSPECT_CONTRACT_EVIDENCE, input_ids=["E-NATIVE-1"]),
        as_of=date(2026, 8, 15),
    )

    assert result.state == AgentActionState.COMPLETED
    assert result.output_evidence_ids == ["E-NATIVE-1"]
    assert result.result_payload["hits"][0]["object_id"] == "clause-001"
    assert result.provider_call_occurred is False
    assert result.private_contract_evidence_left_machine is False


def test_unknown_contract_evidence_fails_closed(tmp_path: Path, monkeypatch) -> None:
    contract = _write_contract(tmp_path, monkeypatch)
    result = execute_agent_action(
        contract.job_id,
        _action(AgentToolName.INSPECT_CONTRACT_EVIDENCE, input_ids=["E-FAKE"]),
        as_of=date(2026, 8, 15),
    )

    assert result.state == AgentActionState.REJECTED
    assert "Unknown canonical contract Evidence IDs" in (result.validation_or_error or "")


def test_get_clause_context_returns_target_and_neighbor(tmp_path: Path, monkeypatch) -> None:
    contract = _write_contract(tmp_path, monkeypatch)
    result = execute_agent_action(
        contract.job_id,
        _action(AgentToolName.GET_CLAUSE_CONTEXT, arguments={"clause_id": "clause-002"}),
        as_of=date(2026, 8, 15),
    )

    assert result.state == AgentActionState.COMPLETED
    returned = {item["clause_id"] for item in result.result_payload["clauses"]}
    assert returned == {"clause-001", "clause-002"}
    assert set(result.output_evidence_ids) == {"E-NATIVE-1", "E-OCR-2"}


def test_ocr_retry_request_is_explicitly_unavailable_but_only_for_ocr_evidence(tmp_path: Path, monkeypatch) -> None:
    contract = _write_contract(tmp_path, monkeypatch)
    native = execute_agent_action(
        contract.job_id,
        _action(AgentToolName.REQUEST_OCR_RETRY, input_ids=["E-NATIVE-1"]),
        as_of=date(2026, 8, 15),
    )
    ocr = execute_agent_action(
        contract.job_id,
        _action(AgentToolName.REQUEST_OCR_RETRY, input_ids=["E-OCR-2"]),
        as_of=date(2026, 8, 15),
    )

    assert native.state == AgentActionState.REJECTED
    assert ocr.state == AgentActionState.UNAVAILABLE
    assert ocr.output_evidence_ids == ["E-OCR-2"]


def test_inspect_legal_evidence_rechecks_as_of_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(repo_root / "legal_data" / "seed" / "manifest.json", legal_db_path(), rebuild=True)

    legal_id = "legal:prc-civil-code:effective-2021-01-01:article-585"
    result = execute_agent_action(
        uuid4(),
        _action(
            AgentToolName.INSPECT_LEGAL_EVIDENCE,
            input_ids=[legal_id],
            arguments={"legal_evidence_ids": [legal_id]},
        ),
        as_of=date(2026, 8, 15),
    )

    assert result.state == AgentActionState.COMPLETED
    assert result.output_evidence_ids == [legal_id]
    assert result.result_payload["records"][0]["article"]["article_token"] == "第五百八十五条"


def test_retrieve_more_legal_stays_local_and_version_aware(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(repo_root / "legal_data" / "seed" / "manifest.json", legal_db_path(), rebuild=True)
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())

    result = execute_agent_action(
        uuid4(),
        _action(
            AgentToolName.RETRIEVE_MORE_LEGAL,
            arguments={"query": "违约金 过分高于损失 调整"},
        ),
        as_of=date(2026, 8, 15),
    )

    assert result.state == AgentActionState.COMPLETED
    assert "legal:prc-civil-code:effective-2021-01-01:article-585" in result.output_evidence_ids
    assert result.provider_call_occurred is False
    assert result.private_contract_evidence_left_machine is False
