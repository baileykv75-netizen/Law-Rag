from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.evidence_models import SourceEvidenceArtifact
from app.main import DOCX_MEDIA_TYPE, app
from app.storage import job_contract_path, job_evidence_path

client = TestClient(app)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def _paragraph(text: str, *, numbered: bool = False, extra: str = "") -> str:
    num_pr = (
        '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        if numbered
        else ""
    )
    return f"<w:p>{num_pr}<w:r><w:t>{text}</w:t></w:r>{extra}</w:p>"


def _table(rows: list[list[str]]) -> str:
    rendered_rows: list[str] = []
    for row in rows:
        cells = "".join(f"<w:tc>{_paragraph(cell)}</w:tc>" for cell in row)
        rendered_rows.append(f"<w:tr>{cells}</w:tr>")
    return f"<w:tbl>{''.join(rendered_rows)}</w:tbl>"


def _numbering_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{W_NS}">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="第%1条"/>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>
"""


def _content_types(*, macro: bool = False) -> str:
    extra = (
        '<Override PartName="/word/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/>'
        if macro
        else ""
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CONTENT_TYPES_NS}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="{MAIN_CONTENT_TYPE}"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  {extra}
</Types>
"""


def _docx_bytes(
    body_xml: str,
    *,
    relationships_xml: str | None = None,
    include_numbering: bool = True,
    macro: bool = False,
) -> bytes:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}" xmlns:a="{A_NS}">
  <w:body>{body_xml}<w:sectPr/></w:body>
</w:document>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(macro=macro))
        archive.writestr("word/document.xml", document_xml)
        if include_numbering:
            archive.writestr("word/numbering.xml", _numbering_xml())
        if relationships_xml is not None:
            archive.writestr("word/_rels/document.xml.rels", relationships_xml)
        if macro:
            archive.writestr("word/vbaProject.bin", b"fictional-macro-placeholder")
    return buffer.getvalue()


def _upload(
    tmp_path: Path,
    monkeypatch,
    payload: bytes,
    *,
    filename: str = "fictional-contract.docx",
):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    return client.post(
        "/api/documents",
        files={"file": (filename, payload, DOCX_MEDIA_TYPE)},
    )


def test_docx_ingestion_preserves_order_numbering_tables_and_no_fake_pages(
    tmp_path: Path, monkeypatch
) -> None:
    body = "".join(
        [
            _paragraph("设备采购合同"),
            _paragraph("合同价款", numbered=True),
            _paragraph("合同总价为人民币 100,000 元，首付款30%。"),
            _table([["付款节点", "比例"], ["预付款", "20%"]]),
            _paragraph("交付与验收", numbered=True),
            _paragraph("乙方应于2026-09-01交付。"),
        ]
    )
    response = _upload(tmp_path, monkeypatch, _docx_bytes(body))

    assert response.status_code == 201
    summary = response.json()
    assert summary["document_kind"] == "docx"
    assert summary["page_count"] == 0
    assert summary["pages"] == []
    assert summary["status"] == "inspected"
    assert summary["evidence_count"] == 9

    job_id = UUID(summary["job_id"])
    artifact = SourceEvidenceArtifact.model_validate_json(job_evidence_path(job_id).read_bytes())
    assert artifact.schema_version == "2.1.0"
    assert len(artifact.source_document.source_sha256) == 64
    assert [item.text for item in artifact.evidence] == [
        "设备采购合同",
        "第1条 合同价款",
        "合同总价为人民币 100,000 元，首付款30%。",
        "付款节点",
        "比例",
        "预付款",
        "20%",
        "第2条 交付与验收",
        "乙方应于2026-09-01交付。",
    ]
    table_cells = [item for item in artifact.evidence if item.block_kind == "TABLE_CELL"]
    assert len(table_cells) == 4
    assert {item.parent_group_id for item in table_cells} == {"docx-table-0001"}
    assert [item.source_anchor.kind for item in table_cells] == ["DOCX_TABLE_CELL"] * 4

    structured = client.post(f"/api/documents/{job_id}/structure")
    assert structured.status_code == 200
    contract = json.loads(job_contract_path(job_id).read_text(encoding="utf-8"))
    assert contract["status"] == "complete"
    assert [clause["heading_token"] for clause in contract["clauses"]] == ["第1条", "第2条"]
    first_span = contract["clauses"][0]["source_spans"][0]
    assert first_span["page_number"] is None
    assert first_span["source_anchor"]["kind"] == "DOCX_PARAGRAPH"
    assert first_span["evidence_ids"] == [artifact.evidence[1].evidence_id]
    assert contract["clauses"][0]["page_start"] is None
    assert contract["clauses"][0]["page_end"] is None
    assert len(contract["structured_blocks"]) == 1
    assert (
        contract["structured_blocks"][0]["provenance"]["extractor_id"]
        == "structured.docx-table-group"
    )


def test_docx_tracked_changes_remain_visible_and_block_complete_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    body = (
        _paragraph("服务合同")
        + '<w:ins w:id="1"><w:p><w:r><w:t>第一条 修订后的服务内容</w:t></w:r></w:p></w:ins>'
        + '<w:p><w:r><w:t>违约金</w:t></w:r><w:del w:id="2"><w:r><w:delText>5%</w:delText></w:r></w:del><w:ins w:id="3"><w:r><w:t>10%</w:t></w:r></w:ins></w:p>'
    )
    response = _upload(tmp_path, monkeypatch, _docx_bytes(body))

    assert response.status_code == 201
    assert response.json()["status"] == "partial"
    assert any(
        "DOCX_TRACKED_CHANGES_PRESENT" in item
        for item in response.json()["warnings"]
    )

    job_id = UUID(response.json()["job_id"])
    structured = client.post(f"/api/documents/{job_id}/structure")
    assert structured.status_code == 200
    assert structured.json()["status"] == "partial"
    contract = json.loads(job_contract_path(job_id).read_text(encoding="utf-8"))
    assert any(
        warning["code"] == "DOCX_TRACKED_CHANGES_PRESENT"
        for warning in contract["warnings"]
    )
    blocks = contract["unnumbered_blocks"] + [
        {"text": clause["body_text"]} for clause in contract["clauses"]
    ]
    assert any("违约金10%" in block["text"] for block in blocks)


def test_docx_embedded_image_is_inventoried_without_ocr_or_external_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{REL_NS}">
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.invalid/never-fetch.png" TargetMode="External"/>
</Relationships>
"""
    drawing = '<w:drawing><a:blip r:embed="rId5"/></w:drawing>'
    body = _paragraph("图片附件合同", extra=drawing) + _paragraph("第一条 正文")
    response = _upload(
        tmp_path,
        monkeypatch,
        _docx_bytes(body, relationships_xml=relationships),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "partial"
    job_id = UUID(response.json()["job_id"])
    artifact = SourceEvidenceArtifact.model_validate_json(job_evidence_path(job_id).read_bytes())
    images = [item for item in artifact.evidence if item.block_kind == "IMAGE"]
    assert len(images) == 1
    assert images[0].source_anchor.kind == "DOCX_EMBEDDED_IMAGE"
    assert images[0].source_anchor.relationship_id == "rId5"
    codes = {warning.code for warning in artifact.warnings}
    assert "DOCX_EXTERNAL_RELATIONSHIP_PRESENT" in codes
    assert "DOCX_EMBEDDED_IMAGE_REQUIRES_OCR_REVIEW" in codes


def test_generic_zip_named_docx_is_rejected_and_upload_is_removed(
    tmp_path: Path, monkeypatch
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not a docx")

    response = _upload(tmp_path, monkeypatch, buffer.getvalue())

    assert response.status_code == 422
    upload_root = tmp_path / "uploads"
    assert not upload_root.exists() or not list(upload_root.rglob("source.docx"))


def test_macro_bearing_docx_is_rejected(tmp_path: Path, monkeypatch) -> None:
    response = _upload(
        tmp_path,
        monkeypatch,
        _docx_bytes(_paragraph("宏合同"), macro=True),
    )

    assert response.status_code == 422
    assert "Macro/VBA" in response.json()["detail"]


def test_doc_extension_is_not_accepted_as_docx(tmp_path: Path, monkeypatch) -> None:
    response = _upload(
        tmp_path,
        monkeypatch,
        b"fictional legacy doc bytes",
        filename="fictional-contract.doc",
    )

    assert response.status_code == 415
    assert "DOCX" in response.json()["detail"]
