from __future__ import annotations

import io
import zipfile
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import DOCX_MEDIA_TYPE, OLE_CFB_SIGNATURE, app
from app.storage import find_source_path

client = TestClient(app)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def _minimal_docx() -> bytes:
    content_types = f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CONTENT_TYPES_NS}">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="{MAIN_CONTENT_TYPE}"/>
</Types>
"""
    document = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}"><w:body>
  <w:p><w:r><w:t>虚构完整性测试合同</w:t></w:r></w:p>
  <w:p><w:r><w:t>第一条 测试内容</w:t></w:r></w:p>
</w:body></w:document>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_encrypted_office_container_is_rejected_explicitly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    payload = OLE_CFB_SIGNATURE + b"fictional-encrypted-office-container"

    response = client.post(
        "/api/documents",
        files={"file": ("encrypted.docx", payload, DOCX_MEDIA_TYPE)},
    )

    assert response.status_code == 422
    assert "Password-protected or encrypted DOCX" in response.json()["detail"]


def test_docx_source_hash_mismatch_blocks_canonical_structure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    response = client.post(
        "/api/documents",
        files={"file": ("integrity.docx", _minimal_docx(), DOCX_MEDIA_TYPE)},
    )
    assert response.status_code == 201

    job_id = UUID(response.json()["job_id"])
    source_path = find_source_path(job_id)
    payload = bytearray(source_path.read_bytes())
    payload[-1] ^= 0x01
    source_path.write_bytes(payload)

    structured = client.post(f"/api/documents/{job_id}/structure")

    assert structured.status_code == 422
    assert "SHA-256" in structured.json()["detail"]
