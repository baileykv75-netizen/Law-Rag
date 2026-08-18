from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.contract_models import (
    CanonicalContract,
    Clause,
    ExtractionConfidence,
    ExtractionProvenance,
    SourceSpan,
)
from app.evidence_models import (
    DocxEmbeddedImageAnchor,
    DocxParagraphAnchor,
    DocxTableCellAnchor,
    SourceDocumentIdentity,
    SourceEvidence,
    SourceEvidenceArtifact,
    SourceEvidenceWarning,
)
from app.main import DOCX_MEDIA_TYPE, app
from app.models import DocumentKind, SourceMethod
from app.workspace import load_workspace_summary


client = TestClient(app)


def _persist_docx_viewer_fixture(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    job_dir = tmp_path / "jobs" / str(job_id)
    upload_dir = tmp_path / "uploads" / str(job_id)
    job_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    source_bytes = b"fictional-docx-viewer-source"
    (upload_dir / "source.docx").write_bytes(source_bytes)

    document = {
        "job_id": str(job_id),
        "filename": "fictional-viewer.docx",
        "media_type": DOCX_MEDIA_TYPE,
        "document_kind": "docx",
        "page_count": 0,
        "route": "NATIVE_TEXT",
        "native_text_pages": 0,
        "ocr_required_pages": 0,
        "status": "partial",
        "evidence_count": 7,
        "warnings": ["DOCX_TRACKED_CHANGES_PRESENT"],
    }
    (job_dir / "document.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    paragraph_1 = DocxParagraphAnchor(paragraph_index=1)
    table_11 = DocxTableCellAnchor(table_index=1, row_index=1, cell_index=1, paragraph_index=1)
    table_12 = DocxTableCellAnchor(table_index=1, row_index=1, cell_index=2, paragraph_index=1)
    table_21 = DocxTableCellAnchor(table_index=1, row_index=2, cell_index=1, paragraph_index=1)
    table_22 = DocxTableCellAnchor(table_index=1, row_index=2, cell_index=2, paragraph_index=1)
    paragraph_2 = DocxParagraphAnchor(paragraph_index=2)
    image = DocxEmbeddedImageAnchor(
        image_index=1,
        relationship_id="rId5",
        parent_locator="docx:document:paragraph:000002",
    )

    anchors = [paragraph_1, table_11, table_12, table_21, table_22, paragraph_2, image]
    texts = ["设备采购合同", "付款节点", "比例", "预付款", "20%", "第1条 付款", ""]
    kinds = ["TEXT", "TABLE_CELL", "TABLE_CELL", "TABLE_CELL", "TABLE_CELL", "TEXT", "IMAGE"]
    evidence = []
    for index, (anchor, text, kind) in enumerate(zip(anchors, texts, kinds), start=1):
        evidence.append(
            SourceEvidence(
                evidence_id=f"ev-docx-view-{index:04d}",
                order_index=index,
                text=text,
                source_method=SourceMethod.NATIVE_DOCX_TEXT,
                source_anchor=anchor,
                block_kind=kind,
                parent_group_id="docx-table-0001" if kind == "TABLE_CELL" else None,
            )
        )

    artifact = SourceEvidenceArtifact(
        job_id=job_id,
        source_document=SourceDocumentIdentity(
            job_id=job_id,
            filename="fictional-viewer.docx",
            media_type=DOCX_MEDIA_TYPE,
            document_kind=DocumentKind.DOCX,
            source_sha256="a" * 64,
            size_bytes=len(source_bytes),
        ),
        evidence=evidence,
        warnings=[
            SourceEvidenceWarning(
                code="DOCX_TRACKED_CHANGES_PRESENT",
                message="Tracked changes require source review.",
                blocks_complete_coverage=True,
            )
        ],
    )
    (job_dir / "evidence.json").write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

    contract = CanonicalContract(
        job_id=job_id,
        filename="fictional-viewer.docx",
        source_fingerprint="fixture",
        evidence_unit_count=7,
        clauses=[
            Clause(
                clause_id="clause-docx-view-001",
                heading_token="第1条",
                heading_text="付款",
                body_text="",
                level=1,
                page_start=None,
                page_end=None,
                source_spans=[
                    SourceSpan(
                        evidence_ids=["ev-docx-view-0006"],
                        source_method=SourceMethod.NATIVE_DOCX_TEXT,
                        quote="第1条 付款",
                        source_anchor=paragraph_2,
                    )
                ],
                provenance=ExtractionProvenance(
                    extractor_id="fixture",
                    confidence=ExtractionConfidence.HIGH,
                ),
            )
        ],
    )
    (job_dir / "contract.json").write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    return job_id


def test_docx_evidence_resolves_to_typed_anchor_without_fake_page(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_docx_viewer_fixture(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{job_id}/evidence/ev-docx-view-0006")

    assert response.status_code == 200
    detail = response.json()
    assert detail["page_number"] is None
    assert detail["source_method"] == "native_docx_text"
    assert detail["source_anchor"] == {
        "kind": "DOCX_PARAGRAPH",
        "part": "document",
        "paragraph_index": 2,
        "char_start": None,
        "char_end": None,
    }
    assert detail["source_locator"] == "docx:document:paragraph:000002"
    assert detail["canonical_references"] == [
        {"object_type": "clause", "object_id": "clause-docx-view-001"}
    ]


def test_docx_table_cell_evidence_resolves_exact_structural_coordinates(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_docx_viewer_fixture(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{job_id}/evidence/ev-docx-view-0005")

    assert response.status_code == 200
    detail = response.json()
    assert detail["page_number"] is None
    assert detail["text"] == "20%"
    assert detail["source_anchor"] == {
        "kind": "DOCX_TABLE_CELL",
        "part": "document",
        "table_index": 1,
        "row_index": 2,
        "cell_index": 2,
        "paragraph_index": 1,
        "char_start": None,
        "char_end": None,
    }
    assert detail["source_locator"] == "docx:document:table:0001:row:0002:cell:0002:paragraph:0001"


def test_docx_logical_source_preserves_paragraph_table_order_and_structure(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_docx_viewer_fixture(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{job_id}/source/docx")

    assert response.status_code == 200
    view = response.json()
    assert view["pagination"] == "LOGICAL_NO_STABLE_PAGES"
    assert view["coverage_complete"] is False
    assert view["evidence_count"] == 7
    assert [block["kind"] for block in view["blocks"]] == ["PARAGRAPH", "TABLE", "PARAGRAPH", "IMAGE"]
    table = view["blocks"][1]
    assert table["group_id"] == "docx-table-0001"
    assert [[cell["paragraphs"][0]["text"] for cell in row["cells"]] for row in table["rows"]] == [
        ["付款节点", "比例"],
        ["预付款", "20%"],
    ]
    assert table["rows"][1]["cells"][1]["paragraphs"][0]["evidence_id"] == "ev-docx-view-0005"
    assert view["warnings"][0]["code"] == "DOCX_TRACKED_CHANGES_PRESENT"


def test_docx_page_endpoint_refuses_to_invent_pagination(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_docx_viewer_fixture(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{job_id}/source/pages/1")

    assert response.status_code == 422
    assert "no stable source pagination" in response.json()["detail"]


def test_workspace_accepts_structural_docx_evidence_and_surfaces_source_uncertainty(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_docx_viewer_fixture(tmp_path, monkeypatch)

    summary = load_workspace_summary(job_id)

    assert summary.document is not None
    assert summary.document.document_kind == "docx"
    assert summary.document.page_count == 0
    ingestion = next(stage for stage in summary.stages if stage.stage == "2")
    assert ingestion.state.value == "READY"
    ocr = next(stage for stage in summary.stages if stage.stage == "3")
    assert ocr.state.value == "NOT_REQUIRED"
    assert any("DOCX_TRACKED_CHANGES_PRESENT" in item for item in summary.source_uncertainty)
    assert any("DOCX_TRACKED_CHANGES_PRESENT" in item for item in summary.warnings)


def test_unknown_docx_evidence_fails_explicitly(tmp_path: Path, monkeypatch) -> None:
    job_id = _persist_docx_viewer_fixture(tmp_path, monkeypatch)

    response = client.get(f"/api/documents/{job_id}/evidence/not-real")

    assert response.status_code == 404
    assert "cannot be resolved" in response.json()["detail"]
