from __future__ import annotations

import mimetypes
from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ai_audit_api import router as ai_audit_router
from .audit_rule_models import DEFAULT_PROFILE_ID, AuditRuleReport
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report, run_audit_rules
from .batch_results_api import router as batch_results_router
from .contract_models import CanonicalContract, StructureSummary
from .contract_structure import (
    StructureIncompleteError,
    StructureProcessingError,
    build_contract_structure,
    load_contract_structure,
    structure_summary,
)
from .document_ingestion import DocumentProcessingError, inspect_document
from .legal.models import (
    ArticleVersionResolution,
    AuthoritySummary,
    LegalArticleBrowserItem,
    LegalEvidenceRecord,
    LegalStoreSummary,
)
from .legal.pack_browser import (
    LegalPackDownloadTask,
    LegalPackTreeNode,
    get_legal_pack_download_task,
    list_legal_pack_tree,
    start_legal_pack_download,
)
from .legal.retrieval import (
    RetrievalIndexError,
    get_retrieval_index_summary,
    retrieve_legal_evidence,
)
from .legal.retrieval_models import RetrievalIndexSummary, RetrievalRequest, RetrievalResponse
from .legal.store import (
    LegalStoreError,
    get_article_for_version,
    get_authority,
    get_evidence,
    get_summary,
    list_articles,
    list_authorities,
    resolve_version,
)
from .models import IngestResponse, OcrRunResult, PageEvidenceSummary
from .ocr import OcrProcessingError, OcrProviderUnavailable, run_ocr_for_job
from .pipeline_api import router as pipeline_router
from .release_frontend import router as release_frontend_router
from .runtime_health_api import router as runtime_health_router
from .storage import legal_db_path, legal_retrieval_index_path, runtime_dir
from .upload_streaming import (
    UploadInsufficientStorageError,
    UploadStreamError,
    UploadTooLargeError,
    declared_upload_size,
    ensure_upload_capacity,
    stream_upload_to_path,
)

APP_NAME = "Law-Rag Local API"
APP_VERSION = "0.8.0"

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OLE_CFB_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".docx"}
EXPECTED_MEDIA_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".docx": {DOCX_MEDIA_TYPE, "application/zip", "application/octet-stream"},
}

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(ai_audit_router)
app.include_router(runtime_health_router)
app.include_router(pipeline_router)
app.include_router(batch_results_router)


class HealthResponse(BaseModel):
    status: str
    service: str


def _extension(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file must have a filename.",
        )
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Use PDF, DOCX, JPG, JPEG, or PNG.",
        )
    return extension


def _validate_declared_media_type(extension: str, media_type: str | None) -> None:
    if not media_type:
        return
    normalized = media_type.lower().split(";", maxsplit=1)[0].strip()
    if normalized not in EXPECTED_MEDIA_TYPES[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File extension {extension} does not match media type {normalized}.",
        )


def _signature_matches(extension: str, header: bytes) -> bool:
    if extension == ".pdf":
        return header.startswith(b"%PDF-")
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".docx":
        return header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    return False


def _cleanup_upload(stored_path: Path) -> None:
    stored_path.unlink(missing_ok=True)
    try:
        stored_path.parent.rmdir()
    except OSError:
        pass


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=APP_NAME)


@app.get("/api/legal/summary", response_model=LegalStoreSummary)
def legal_summary() -> LegalStoreSummary:
    """Inspect whether the local versioned legal store has been built."""

    try:
        return get_summary(legal_db_path())
    except LegalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/authorities", response_model=list[AuthoritySummary])
def legal_authorities() -> list[AuthoritySummary]:
    try:
        return list_authorities(legal_db_path())
    except LegalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/authorities/{authority_id}", response_model=AuthoritySummary)
def legal_authority(authority_id: str) -> AuthoritySummary:
    try:
        return get_authority(legal_db_path(), authority_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LegalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/articles", response_model=list[LegalArticleBrowserItem])
def legal_articles(
    query: str | None = Query(default=None, description="Optional keyword for title, article token or text"),
    authority_id: str | None = Query(default=None, description="Optional exact authority id filter"),
    version_id: str | None = Query(default=None, description="Optional exact legal version id filter"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=80, ge=1, le=1000),
) -> list[LegalArticleBrowserItem]:
    try:
        return list_articles(
            legal_db_path(),
            query=query,
            authority_id=authority_id,
            version_id=version_id,
            offset=offset,
            limit=limit,
        )
    except LegalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/packs", response_model=list[LegalPackTreeNode])
def legal_packs() -> list[LegalPackTreeNode]:
    try:
        return list_legal_pack_tree()
    except (LegalStoreError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.post("/api/legal/packs/{pack_id}/download", response_model=LegalPackDownloadTask)
def legal_pack_download(pack_id: str) -> LegalPackDownloadTask:
    try:
        return start_legal_pack_download(pack_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (LegalStoreError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/packs/tasks/{task_id}", response_model=LegalPackDownloadTask)
def legal_pack_download_task(task_id: UUID) -> LegalPackDownloadTask:
    try:
        return get_legal_pack_download_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get("/api/legal/evidence/{legal_evidence_id}", response_model=LegalEvidenceRecord)
def legal_evidence(legal_evidence_id: str) -> LegalEvidenceRecord:
    try:
        return get_evidence(legal_db_path(), legal_evidence_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LegalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/resolve/{authority_id}", response_model=ArticleVersionResolution)
def legal_resolve(
    authority_id: str,
    as_of: date = Query(description="Date for deterministic legal-version resolution"),
    article_token: str | None = Query(default=None, description="Optional exact article token, e.g. 第五百八十五条"),
) -> ArticleVersionResolution:
    try:
        resolution = resolve_version(legal_db_path(), authority_id, as_of)
        article = None
        if resolution.version is not None and article_token:
            article = get_article_for_version(
                legal_db_path(), authority_id, resolution.version.version_id, article_token
            )
        return ArticleVersionResolution(resolution=resolution, article=article)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LegalStoreError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.get("/api/legal/retrieval/summary", response_model=RetrievalIndexSummary)
def legal_retrieval_summary() -> RetrievalIndexSummary:
    try:
        return get_retrieval_index_summary(legal_retrieval_index_path(), legal_db_path())
    except RetrievalIndexError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.post("/api/legal/retrieve", response_model=RetrievalResponse)
def legal_retrieve(request: RetrievalRequest) -> RetrievalResponse:
    try:
        return retrieve_legal_evidence(
            legal_db_path(),
            legal_retrieval_index_path(),
            request,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (LegalStoreError, RetrievalIndexError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@app.post("/api/documents", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    file: Annotated[UploadFile, File(description="One PDF/DOCX/JPG/JPEG/PNG contract document")],
) -> IngestResponse:
    original_filename = file.filename or ""
    extension = _extension(original_filename)
    _validate_declared_media_type(extension, file.content_type)

    expected_size = declared_upload_size(file)
    try:
        ensure_upload_capacity(runtime_dir(), expected_size)
    except UploadTooLargeError as exc:
        await file.close()
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except UploadInsufficientStorageError as exc:
        await file.close()
        raise HTTPException(status_code=507, detail=str(exc)) from exc

    job_id = uuid4()
    upload_dir = runtime_dir() / "uploads" / str(job_id)
    stored_path = upload_dir / f"source{extension}"

    try:
        size_bytes, header = await stream_upload_to_path(file, stored_path)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except UploadInsufficientStorageError as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from exc
    except UploadStreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The uploaded file could not be stored safely on the local machine.",
        ) from exc
    finally:
        await file.close()

    if size_bytes == 0:
        _cleanup_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    if extension == ".docx" and header.startswith(OLE_CFB_SIGNATURE):
        _cleanup_upload(stored_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Password-protected or encrypted DOCX files are not supported. Save an unencrypted .docx copy before audit.",
        )

    if not _signature_matches(extension, header):
        _cleanup_upload(stored_path)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File contents do not match the selected file type.",
        )

    media_type = file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

    try:
        inspection = inspect_document(
            job_id=job_id,
            filename=original_filename,
            media_type=media_type,
            source_path=stored_path,
        )
    except DocumentProcessingError as exc:
        _cleanup_upload(stored_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return IngestResponse(
        job_id=job_id,
        filename=original_filename,
        media_type=media_type,
        size_bytes=size_bytes,
        status=inspection.status,
        storage_scope="local-runtime-only",
        document_kind=inspection.document_kind,
        page_count=inspection.page_count,
        route=inspection.route,
        native_text_pages=inspection.native_text_pages,
        ocr_required_pages=inspection.ocr_required_pages,
        pages=[
            PageEvidenceSummary(
                evidence_id=page.evidence_id,
                page_number=page.page_number,
                route=page.route,
                character_count=page.character_count,
                route_reason=page.route_reason,
            )
            for page in inspection.pages
        ],
        evidence_count=inspection.evidence_count,
        warnings=inspection.warnings,
    )


@app.post("/api/documents/{job_id}/ocr", response_model=OcrRunResult)
def ocr_document(job_id: UUID) -> OcrRunResult:
    """Run local OCR only for pages Stage 2 marked OCR_REQUIRED."""

    try:
        return run_ocr_for_job(job_id)
    except OcrProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OcrProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@app.post("/api/documents/{job_id}/structure", response_model=StructureSummary)
def generate_structure(job_id: UUID) -> StructureSummary:
    """Generate deterministic canonical contract structure from local evidence."""

    try:
        contract = build_contract_structure(job_id)
        return structure_summary(contract)
    except StructureIncompleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except StructureProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@app.get("/api/documents/{job_id}/structure", response_model=CanonicalContract)
def get_structure(job_id: UUID) -> CanonicalContract:
    """Return the persisted canonical contract structure for a local job."""

    try:
        return load_contract_structure(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except StructureProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@app.post("/api/documents/{job_id}/audit-rules", response_model=AuditRuleReport)
def audit_rules_document(
    job_id: UUID,
    profile: str = Query(default=DEFAULT_PROFILE_ID, description="Explicit deterministic audit profile"),
) -> AuditRuleReport:
    """Run Stage 5 deterministic checks against persisted contract.json only."""

    try:
        return run_audit_rules(job_id, profile_id=profile)
    except AuditRuleProcessingError as exc:
        message = str(exc)
        http_status = status.HTTP_404_NOT_FOUND if "does not exist" in message else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=http_status, detail=message) from exc


@app.get("/api/documents/{job_id}/audit-rules", response_model=AuditRuleReport)
def get_audit_rules(job_id: UUID) -> AuditRuleReport:
    """Return the persisted deterministic audit report for a local job."""

    try:
        return load_audit_rule_report(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AuditRuleProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


# Keep the production frontend catch-all after every API route. In development,
# LAW_RAG_FRONTEND_DIST is unset and these routes return an explicit 404, so the
# existing Vite workflow remains unchanged. In a release bundle they serve the
# compiled SPA from the same localhost origin as the API.
app.include_router(release_frontend_router)
