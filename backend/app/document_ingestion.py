from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import (
    DocumentInspection,
    DocumentKind,
    DocumentRoute,
    PageEvidence,
    PageRoute,
    SourceMethod,
)
from .storage import job_document_path, job_evidence_path

MIN_NATIVE_NON_WHITESPACE = 32
MIN_MEANINGFUL_RATIO = 0.45
MAX_SUSPICIOUS_RATIO = 0.02


class DocumentProcessingError(RuntimeError):
    pass


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _routing_metrics(text: str) -> tuple[int, int, float]:
    non_whitespace = [char for char in text if not char.isspace()]
    count = len(non_whitespace)
    if count == 0:
        return 0, 0, 0.0

    meaningful = sum(char.isalnum() for char in non_whitespace)
    suspicious = sum(
        char == "\ufffd" or (not char.isprintable() and not char.isspace())
        for char in non_whitespace
    )
    return count, suspicious, meaningful / count


def classify_native_text(text: str) -> tuple[PageRoute, str, int, int, float]:
    non_whitespace_count, suspicious_count, meaningful_ratio = _routing_metrics(text)

    if non_whitespace_count == 0:
        return (
            PageRoute.OCR_REQUIRED,
            "No native text was extracted from this page.",
            non_whitespace_count,
            suspicious_count,
            meaningful_ratio,
        )

    if non_whitespace_count < MIN_NATIVE_NON_WHITESPACE:
        return (
            PageRoute.OCR_REQUIRED,
            f"Native text is too sparse ({non_whitespace_count} non-whitespace characters).",
            non_whitespace_count,
            suspicious_count,
            meaningful_ratio,
        )

    suspicious_ratio = suspicious_count / non_whitespace_count
    if suspicious_ratio > MAX_SUSPICIOUS_RATIO:
        return (
            PageRoute.OCR_REQUIRED,
            "Native text contains too many suspicious/replacement characters.",
            non_whitespace_count,
            suspicious_count,
            meaningful_ratio,
        )

    if meaningful_ratio < MIN_MEANINGFUL_RATIO:
        return (
            PageRoute.OCR_REQUIRED,
            f"Native text has a low meaningful-character ratio ({meaningful_ratio:.2f}).",
            non_whitespace_count,
            suspicious_count,
            meaningful_ratio,
        )

    return (
        PageRoute.NATIVE_TEXT_USABLE,
        "Native text passed the deterministic Stage 2 routing heuristic.",
        non_whitespace_count,
        suspicious_count,
        meaningful_ratio,
    )


def _evidence_id(job_id: UUID, page_number: int) -> str:
    return f"ev-{job_id}-p{page_number:04d}"


def _overall_route(pages: list[PageEvidence]) -> DocumentRoute:
    native_count = sum(page.route == PageRoute.NATIVE_TEXT_USABLE for page in pages)
    ocr_count = sum(page.route == PageRoute.OCR_REQUIRED for page in pages)
    if native_count and ocr_count:
        return DocumentRoute.MIXED
    if native_count:
        return DocumentRoute.NATIVE_TEXT
    return DocumentRoute.OCR_REQUIRED


def _persist_inspection(inspection: DocumentInspection) -> None:
    document_payload = inspection.model_dump(mode="json", exclude={"pages"})
    evidence_payload = [page.model_dump(mode="json") for page in inspection.pages]

    document_path = job_document_path(inspection.job_id)
    evidence_path = job_evidence_path(inspection.job_id)
    document_path.write_text(
        json.dumps(document_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    evidence_path.write_text(
        json.dumps(evidence_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _inspect_image(
    *,
    job_id: UUID,
    filename: str,
    media_type: str,
) -> DocumentInspection:
    page = PageEvidence(
        evidence_id=_evidence_id(job_id, 1),
        page_number=1,
        source_method=SourceMethod.IMAGE_SOURCE,
        text="",
        character_count=0,
        non_whitespace_count=0,
        meaningful_ratio=0.0,
        suspicious_character_count=0,
        route=PageRoute.OCR_REQUIRED,
        route_reason="Image documents require OCR; OCR is introduced in Stage 3.",
        source_locator="page:1",
    )
    inspection = DocumentInspection(
        job_id=job_id,
        filename=filename,
        media_type=media_type,
        document_kind=DocumentKind.IMAGE,
        page_count=1,
        route=DocumentRoute.OCR_REQUIRED,
        native_text_pages=0,
        ocr_required_pages=1,
        pages=[page],
    )
    _persist_inspection(inspection)
    return inspection


def _inspect_pdf(
    *,
    job_id: UUID,
    filename: str,
    media_type: str,
    source_path: Path,
) -> DocumentInspection:
    try:
        reader = PdfReader(str(source_path), strict=False)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:  # pypdf encryption backends vary by PDF
                raise DocumentProcessingError(
                    "Password-protected PDFs are not supported in Stage 2."
                ) from exc
            if unlocked == 0:
                raise DocumentProcessingError(
                    "Password-protected PDFs are not supported in Stage 2."
                )

        if not reader.pages:
            raise DocumentProcessingError("The PDF contains no readable pages.")

        pages: list[PageEvidence] = []
        for index, pdf_page in enumerate(reader.pages, start=1):
            try:
                extracted = pdf_page.extract_text() or ""
                normalized = _normalize_text(extracted)
                route, reason, non_ws, suspicious, meaningful_ratio = classify_native_text(normalized)
            except Exception:
                normalized = ""
                route = PageRoute.OCR_REQUIRED
                reason = "Native text extraction failed for this page; route it to OCR."
                non_ws = 0
                suspicious = 0
                meaningful_ratio = 0.0

            pages.append(
                PageEvidence(
                    evidence_id=_evidence_id(job_id, index),
                    page_number=index,
                    source_method=SourceMethod.NATIVE_PDF_TEXT,
                    text=normalized,
                    character_count=len(normalized),
                    non_whitespace_count=non_ws,
                    meaningful_ratio=meaningful_ratio,
                    suspicious_character_count=suspicious,
                    route=route,
                    route_reason=reason,
                    source_locator=f"page:{index}",
                )
            )
    except DocumentProcessingError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentProcessingError("The uploaded PDF is corrupt or cannot be parsed.") from exc
    except Exception as exc:
        raise DocumentProcessingError("The uploaded PDF could not be inspected safely.") from exc

    native_count = sum(page.route == PageRoute.NATIVE_TEXT_USABLE for page in pages)
    ocr_count = sum(page.route == PageRoute.OCR_REQUIRED for page in pages)
    inspection = DocumentInspection(
        job_id=job_id,
        filename=filename,
        media_type=media_type,
        document_kind=DocumentKind.PDF,
        page_count=len(pages),
        route=_overall_route(pages),
        native_text_pages=native_count,
        ocr_required_pages=ocr_count,
        pages=pages,
    )
    _persist_inspection(inspection)
    return inspection


def inspect_document(
    *,
    job_id: UUID,
    filename: str,
    media_type: str,
    source_path: Path,
) -> DocumentInspection:
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return _inspect_pdf(
            job_id=job_id,
            filename=filename,
            media_type=media_type,
            source_path=source_path,
        )
    if suffix in {".jpg", ".jpeg", ".png"}:
        return _inspect_image(job_id=job_id, filename=filename, media_type=media_type)
    raise DocumentProcessingError("Unsupported document kind.")
