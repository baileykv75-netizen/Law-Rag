from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.contract_models import ResolutionState
from app.contract_structure import (
    StructureIncompleteError,
    StructureProcessingError,
    build_contract_structure,
    build_evidence_stream,
)
from app.main import app
from app.models import (
    DocumentInspection,
    DocumentKind,
    DocumentRoute,
    OcrBlockEvidence,
    OcrPageEvidence,
    OcrPageState,
    OcrRunResult,
    PageEvidence,
    PageRoute,
    SourceMethod,
)
from app.storage import job_contract_path, job_document_path, job_evidence_path, job_ocr_path

client = TestClient(app)


def _page(job_id: UUID, page_number: int, text: str, route: PageRoute = PageRoute.NATIVE_TEXT_USABLE) -> PageEvidence:
    non_ws = len([char for char in text if not char.isspace()])
    return PageEvidence(
        evidence_id=f"ev-{job_id}-p{page_number:04d}",
        page_number=page_number,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text=text,
        character_count=len(text),
        non_whitespace_count=non_ws,
        meaningful_ratio=1.0 if non_ws else 0.0,
        suspicious_character_count=0,
        route=route,
        route_reason="synthetic Stage 4 fixture",
        source_locator=f"page:{page_number}",
    )


def _persist_job(tmp_path: Path, monkeypatch, pages: list[PageEvidence], *, filename: str = "fictional-contract.pdf") -> UUID:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = UUID(pages[0].evidence_id.split("-")[1]) if False else uuid4()
    raise AssertionError("Use _persist_text_job so evidence IDs and job IDs cannot diverge.")


def _persist_text_job(tmp_path: Path, monkeypatch, page_texts: list[str], *, ocr_pages: set[int] | None = None) -> UUID:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    ocr_pages = ocr_pages or set()
    pages = [
        _page(
            job_id,
            index,
            text if index not in ocr_pages else "",
            PageRoute.OCR_REQUIRED if index in ocr_pages else PageRoute.NATIVE_TEXT_USABLE,
        )
        for index, text in enumerate(page_texts, start=1)
    ]
    native_count = sum(page.route == PageRoute.NATIVE_TEXT_USABLE for page in pages)
    ocr_count = len(pages) - native_count
    route = DocumentRoute.MIXED if native_count and ocr_count else (DocumentRoute.OCR_REQUIRED if ocr_count else DocumentRoute.NATIVE_TEXT)
    inspection = DocumentInspection(
        job_id=job_id,
        filename="fictional-contract.pdf",
        media_type="application/pdf",
        document_kind=DocumentKind.PDF,
        page_count=len(pages),
        route=route,
        native_text_pages=native_count,
        ocr_required_pages=ocr_count,
        pages=pages,
    )
    job_document_path(job_id).write_text(
        json.dumps(inspection.model_dump(mode="json", exclude={"pages"}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    job_evidence_path(job_id).write_text(
        json.dumps([page.model_dump(mode="json") for page in pages], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return job_id


def _persist_mixed_ocr(tmp_path: Path, monkeypatch) -> UUID:
    job_id = _persist_text_job(
        tmp_path,
        monkeypatch,
        ["混合来源合同\n甲方：甲测试有限公司\n第一条 原生条款\n原生页正文。", ""],
        ocr_pages={2},
    )
    block = OcrBlockEvidence(
        evidence_id=f"ocr-{job_id}-p0002-b0001",
        page_number=2,
        block_index=1,
        text="乙方：乙测试有限公司",
        confidence=0.96,
        bbox=[10, 20, 300, 60],
        polygon=[[10, 20], [300, 20], [300, 60], [10, 60]],
        provider="fake-ocr",
        model="fixture",
        provider_version="1",
        low_confidence=False,
        source_locator="page:2;pixel_bbox:10,20,300,60",
    )
    ocr = OcrRunResult(
        job_id=job_id,
        provider="fake-ocr",
        model="fixture",
        provider_version="1",
        status="complete",
        page_count=2,
        native_pages=1,
        ocr_pages_attempted=1,
        ocr_pages_complete=1,
        low_confidence_pages=0,
        failed_pages=0,
        no_text_pages=0,
        pages=[
            OcrPageEvidence(
                page_number=1,
                state=OcrPageState.NATIVE_RETAINED,
                source_method=SourceMethod.NATIVE_PDF_TEXT,
                text="混合来源合同\n甲方：甲测试有限公司\n第一条 原生条款\n原生页正文。",
                native_evidence_id=f"ev-{job_id}-p0001",
            ),
            OcrPageEvidence(
                page_number=2,
                state=OcrPageState.OCR_COMPLETE,
                source_method=SourceMethod.OCR,
                text=block.text,
                source_image_locator="rendered/page-0002.png",
                width_px=1200,
                height_px=1600,
                blocks=[block],
                mean_confidence=0.96,
            ),
        ],
    )
    job_ocr_path(job_id).write_text(ocr.model_dump_json(indent=2), encoding="utf-8")
    return job_id


def test_extracts_core_contract_mentions_and_resolves_clause_reference(tmp_path: Path, monkeypatch) -> None:
    text = """设备采购合同
合同编号：HT-2026-001
甲方：甲测试有限公司
乙方：乙测试有限公司
签订日期：2026年8月15日
第一条 合同价款
合同总价为人民币 100,000 元，首付款30%，尾款百分之七十。
第二条 交付
乙方应于2026-09-01交付。具体要求见附件1，并按照第一条执行。
"""
    job_id = _persist_text_job(tmp_path, monkeypatch, [text])

    contract = build_contract_structure(job_id)

    assert contract.title_candidates[0].text == "设备采购合同"
    assert [clause.heading_token for clause in contract.clauses] == ["第一条", "第二条"]
    assert [(party.role_label, party.raw_name) for party in contract.parties] == [
        ("甲方", "甲测试有限公司"),
        ("乙方", "乙测试有限公司"),
    ]
    assert [mention.iso_date for mention in contract.dates] == ["2026-08-15", "2026-09-01"]
    assert contract.money_mentions[0].numeric_value == "100000"
    assert [item.numeric_value for item in contract.percentages] == ["30", "70"]
    assert contract.identifiers[0].raw_value == "HT-2026-001"

    attachment = next(ref for ref in contract.references if ref.reference_type.value == "ATTACHMENT")
    article = next(ref for ref in contract.references if ref.raw_text == "第一条")
    assert attachment.resolution_state == ResolutionState.UNRESOLVED
    assert article.resolution_state == ResolutionState.RESOLVED
    assert article.resolved_target_id == contract.clauses[0].clause_id
    assert job_contract_path(job_id).exists()


def test_cross_page_clause_continuation_keeps_page_range_and_evidence(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(
        tmp_path,
        monkeypatch,
        [
            "服务合同\n第一条 服务内容\n甲方提供测试资料。",
            "乙方继续完成本条约定的工作。",
            "第二条 验收\n双方完成虚构验收。",
        ],
    )

    contract = build_contract_structure(job_id)

    first = contract.clauses[0]
    assert first.page_start == 1
    assert first.page_end == 2
    assert "乙方继续完成" in first.body_text
    assert {span.page_number for span in first.source_spans} == {1, 2}


def test_nested_chinese_and_arabic_clause_hierarchy(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(
        tmp_path,
        monkeypatch,
        [
            "测试协议\n一、总则\n（一）适用范围\n1. 一般要求\n1.1 子项要求\n1.1.1 细项要求\n具体内容。"
        ],
    )

    contract = build_contract_structure(job_id)
    tokens = [clause.heading_token for clause in contract.clauses]
    assert tokens == ["一、", "（一）", "1.", "1.1", "1.1.1"]
    assert contract.clauses[1].parent_clause_id == contract.clauses[0].clause_id
    assert contract.clauses[3].parent_clause_id == contract.clauses[2].clause_id
    assert contract.clauses[4].parent_clause_id == contract.clauses[3].clause_id


def test_mixed_native_and_ocr_evidence_remain_distinct(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_mixed_ocr(tmp_path, monkeypatch)
    contract = build_contract_structure(job_id)

    party_by_role = {party.role_label: party for party in contract.parties}
    assert party_by_role["甲方"].source_spans[0].source_method == SourceMethod.NATIVE_PDF_TEXT
    assert party_by_role["乙方"].source_spans[0].source_method == SourceMethod.OCR
    assert party_by_role["乙方"].source_spans[0].evidence_ids == [f"ocr-{job_id}-p0002-b0001"]
    assert party_by_role["乙方"].source_spans[0].bbox == [10, 20, 300, 60]


def test_evidence_stream_never_substitutes_ocr_for_native_page(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_mixed_ocr(tmp_path, monkeypatch)
    document_payload = json.loads(job_document_path(job_id).read_text(encoding="utf-8"))
    evidence_payload = json.loads(job_evidence_path(job_id).read_text(encoding="utf-8"))
    inspection = DocumentInspection.model_validate({**document_payload, "pages": evidence_payload})
    ocr = OcrRunResult.model_validate_json(job_ocr_path(job_id).read_bytes())

    units = build_evidence_stream(inspection, ocr)

    assert any(unit.source_method == SourceMethod.NATIVE_PDF_TEXT and unit.page_number == 1 for unit in units)
    assert any(unit.source_method == SourceMethod.OCR and unit.page_number == 2 for unit in units)
    assert not any(unit.source_method == SourceMethod.OCR and unit.page_number == 1 for unit in units)


def test_invalid_explicit_date_is_preserved_as_unresolved(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(tmp_path, monkeypatch, ["测试合同\n签订日期：2026年2月30日\n第一条 内容\n测试。"])
    contract = build_contract_structure(job_id)

    assert contract.dates[0].raw_text == "2026年2月30日"
    assert contract.dates[0].iso_date is None
    assert contract.dates[0].resolution_state == ResolutionState.UNRESOLVED
    assert any(warning.code == "INVALID_DATE" for warning in contract.warnings)


def test_duplicate_clause_labels_make_reference_ambiguous(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(
        tmp_path,
        monkeypatch,
        ["测试合同\n第一条 A\n内容。\n第一条 B\n内容。\n第三条 C\n按照第一条执行。"],
    )
    contract = build_contract_structure(job_id)

    reference = next(ref for ref in contract.references if ref.raw_text == "第一条")
    assert reference.resolution_state == ResolutionState.AMBIGUOUS
    assert reference.resolved_target_id is None


def test_structure_generation_is_deterministic_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(tmp_path, monkeypatch, ["测试合同\n第一条 内容\n人民币10万元，比例10%。"])

    first = build_contract_structure(job_id)
    first_bytes = job_contract_path(job_id).read_bytes()
    second = build_contract_structure(job_id)
    second_bytes = job_contract_path(job_id).read_bytes()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first_bytes == second_bytes


def test_missing_ocr_is_explicit_incomplete_state(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(tmp_path, monkeypatch, [""], ocr_pages={1})

    with pytest.raises(StructureIncompleteError, match="Run local OCR"):
        build_contract_structure(job_id)

    response = client.post(f"/api/documents/{job_id}/structure")
    assert response.status_code == 409
    assert "OCR" in response.json()["detail"]


def test_malformed_evidence_fails_without_crashing(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(tmp_path, monkeypatch, ["测试合同\n第一条 内容\n测试。"])
    job_evidence_path(job_id).write_text("{not-json", encoding="utf-8")

    with pytest.raises(StructureProcessingError, match="malformed"):
        build_contract_structure(job_id)


def test_structure_api_generates_summary_and_get_returns_full_contract(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_text_job(tmp_path, monkeypatch, ["测试合同\n甲方：A测试公司\n第一条 内容\n金额为¥1000.00。"])

    generated = client.post(f"/api/documents/{job_id}/structure")
    assert generated.status_code == 200
    summary = generated.json()
    assert summary["title"] == "测试合同"
    assert summary["clause_count"] == 1
    assert summary["party_count"] == 1
    assert summary["money_count"] == 1

    fetched = client.get(f"/api/documents/{job_id}/structure")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["schema_version"] == "1.1.0"
    assert body["job_id"] == str(job_id)
    assert body["clauses"][0]["source_spans"][0]["evidence_ids"] == [f"ev-{job_id}-p0001"]
