from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .document_ingestion import DocumentProcessingError, inspect_document
from .models import IngestResponse, OcrRunResult, PageEvidenceSummary
from .ocr import OcrProcessingError, OcrProviderUnavailable, run_ocr_for_job
from .storage import job_upload_dir

APP_NAME = "Law-Rag Local API"
CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
EXPECTED_MEDIA_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
}

app = FastAPI(title=APP_NAME, version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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
            detail="Unsupported file type. Use PDF, JPG, JPEG, or PNG.",
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
    return False


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=APP_NAME)


@app.post("/api/documents", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    file: Annotated[UploadFile, File(description="One PDF/JPG/JPEG/PNG test document")],
) -> IngestResponse:
    original_filename = file.filename or ""
    extension = _extension(original_filename)
    _validate_declared_media_type(extension, file.content_type)

    job_id = uuid4()
    upload_dir = job_upload_dir(job_id)
    stored_path = upload_dir / f"source{extension}"
    size_bytes = 0
    header = b""

    try:
        with stored_path.open("wb") as destination:
            while chunk := await file.read(CHUNK_SIZE):
                if not header:
                    header = chunk[:16]
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File exceeds the current 50 MiB limit.",
                    )
                destination.write(chunk)
    except Exception:
        if stored_path.exists():
            stored_path.unlink()
        try:
            upload_dir.rmdir()
        except OSError:
            pass
        raise
    finally:
        await file.close()

    if size_bytes == 0:
        stored_path.unlink(missing_ok=True)
        try:
            upload_dir.rmdir()
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if not _signature_matches(extension, header):
        stored_path.unlink(missing_ok=True)
        try:
            upload_dir.rmdir()
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File contents do not match the selected file type.",
        )

    media_type = (
        file.content_type
        or mimetypes.guess_type(original_filename)[0]
        or "application/octet-stream"
    )

    try:
        inspection = inspect_document(
            job_id=job_id,
            filename=original_filename,
            media_type=media_type,
            source_path=stored_path,
        )
    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
