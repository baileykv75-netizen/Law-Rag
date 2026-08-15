from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from .contract_models import CanonicalContract, SourceSpan
from .models import OcrRunResult, PageEvidence
from .rendering import PdfRenderError, PdfiumPageRenderer
from .source_viewer_models import CanonicalEvidenceReference, SourceEvidenceDetail
from .storage import runtime_dir


class SourceViewerError(RuntimeError):
    pass


_PAGE_EVIDENCE_ADAPTER = TypeAdapter(list[PageEvidence])


@dataclass(frozen=True)
class SourcePageAsset:
    path: Path
    media_type: str


def _job_dir(job_id: UUID) -> Path:
    return runtime_dir() / "jobs" / str(job_id)


def _source_path(job_id: UUID) -> Path:
    candidates = sorted((runtime_dir() / "uploads" / str(job_id)).glob("source.*"))
    if len(candidates) != 1:
        raise FileNotFoundError(f"Expected exactly one local source file for job {job_id}.")
    return candidates[0]


def _document_metadata(job_id: UUID) -> dict:
    path = _job_dir(job_id) / "document.json"
    if not path.exists():
        raise FileNotFoundError(f"document.json does not exist for job {job_id}.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceViewerError(f"document.json is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceViewerError("document.json is invalid: expected an object.")
    return payload


def source_page_asset(job_id: UUID, page_number: int) -> SourcePageAsset:
    if page_number < 1:
        raise SourceViewerError("Page numbers are 1-based and must be positive.")

    metadata = _document_metadata(job_id)
    try:
        page_count = int(metadata["page_count"])
        document_kind = str(metadata["document_kind"])
        media_type = str(metadata["media_type"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceViewerError("document.json is missing required source-viewer metadata.") from exc

    if page_number > page_count:
        raise FileNotFoundError(
            f"Page {page_number} does not exist for job {job_id}; document has {page_count} page(s)."
        )

    source = _source_path(job_id)
    if document_kind == "image":
        if page_number != 1:
            raise FileNotFoundError("Image documents contain exactly one source page.")
        return SourcePageAsset(path=source, media_type=media_type)

    if document_kind != "pdf":
        raise SourceViewerError(f"Unsupported source document kind: {document_kind}.")

    output = runtime_dir() / "viewer" / str(job_id) / f"page-{page_number:04d}.png"
    if not output.exists():
        try:
            PdfiumPageRenderer(scale=2.0).render_page(source, page_number, output)
        except PdfRenderError as exc:
            raise SourceViewerError(str(exc)) from exc
    return SourcePageAsset(path=output, media_type="image/png")


def _load_page_evidence(job_id: UUID) -> list[PageEvidence]:
    path = _job_dir(job_id) / "evidence.json"
    if not path.exists():
        raise FileNotFoundError(f"evidence.json does not exist for job {job_id}.")
    try:
        return _PAGE_EVIDENCE_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceViewerError(f"evidence.json is invalid: {exc}") from exc


def _load_ocr(job_id: UUID) -> OcrRunResult | None:
    path = _job_dir(job_id) / "ocr.json"
    if not path.exists():
        return None
    try:
        return OcrRunResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceViewerError(f"ocr.json is invalid: {exc}") from exc


def _load_contract(job_id: UUID) -> CanonicalContract | None:
    path = _job_dir(job_id) / "contract.json"
    if not path.exists():
        return None
    try:
        return CanonicalContract.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceViewerError(f"contract.json is invalid: {exc}") from exc


def _canonical_spans(contract: CanonicalContract) -> list[tuple[str, str, SourceSpan]]:
    rows: list[tuple[str, str, SourceSpan]] = []
    collections = [
        ("title", contract.title_candidates, "candidate_id"),
        ("clause", contract.clauses, "clause_id"),
        ("unnumbered_block", contract.unnumbered_blocks, "block_id"),
        ("party", contract.parties, "mention_id"),
        ("date", contract.dates, "mention_id"),
        ("money", contract.money_mentions, "mention_id"),
        ("percentage", contract.percentages, "mention_id"),
        ("identifier", contract.identifiers, "mention_id"),
        ("reference", contract.references, "reference_id"),
        ("structured_block", contract.structured_blocks, "block_id"),
    ]
    for object_type, items, id_field in collections:
        for item in items:
            object_id = str(getattr(item, id_field))
            for span in item.source_spans:
                rows.append((object_type, object_id, span))
    return rows


def resolve_contract_evidence(job_id: UUID, evidence_id: str) -> SourceEvidenceDetail:
    normalized_id = evidence_id.strip()
    if not normalized_id:
        raise SourceViewerError("Evidence ID must not be empty.")

    page_evidence = _load_page_evidence(job_id)
    ocr = _load_ocr(job_id)
    contract = _load_contract(job_id)

    base_page: PageEvidence | None = next(
        (item for item in page_evidence if item.evidence_id == normalized_id),
        None,
    )
    ocr_block = None
    ocr_page = None
    if ocr is not None:
        for page in ocr.pages:
            for block in page.blocks:
                if block.evidence_id == normalized_id:
                    ocr_block = block
                    ocr_page = page
                    break
            if ocr_block is not None:
                break

    if base_page is None and ocr_block is None:
        raise FileNotFoundError(f"Evidence ID {normalized_id} cannot be resolved for job {job_id}.")

    canonical_references: list[CanonicalEvidenceReference] = []
    matching_spans: list[SourceSpan] = []
    if contract is not None:
        for object_type, object_id, span in _canonical_spans(contract):
            if normalized_id in span.evidence_ids:
                canonical_references.append(
                    CanonicalEvidenceReference(object_type=object_type, object_id=object_id)
                )
                matching_spans.append(span)

    selected_span = matching_spans[0] if matching_spans else None
    if ocr_block is not None:
        return SourceEvidenceDetail(
            evidence_id=normalized_id,
            page_number=ocr_block.page_number,
            source_method=ocr_block.source_method,
            text=selected_span.quote if selected_span is not None else ocr_block.text,
            confidence=(selected_span.confidence if selected_span and selected_span.confidence is not None else ocr_block.confidence),
            bbox=selected_span.bbox if selected_span and selected_span.bbox is not None else ocr_block.bbox,
            polygon=selected_span.polygon if selected_span and selected_span.polygon is not None else ocr_block.polygon,
            char_start=selected_span.char_start if selected_span else None,
            char_end=selected_span.char_end if selected_span else None,
            source_locator=ocr_block.source_locator,
            coordinate_space_width_px=ocr_page.width_px if ocr_page else None,
            coordinate_space_height_px=ocr_page.height_px if ocr_page else None,
            canonical_references=canonical_references,
        )

    assert base_page is not None
    return SourceEvidenceDetail(
        evidence_id=normalized_id,
        page_number=selected_span.page_number if selected_span is not None else base_page.page_number,
        source_method=selected_span.source_method if selected_span is not None else base_page.source_method,
        text=selected_span.quote if selected_span is not None else base_page.text,
        confidence=selected_span.confidence if selected_span is not None else None,
        bbox=selected_span.bbox if selected_span is not None else None,
        polygon=selected_span.polygon if selected_span is not None else None,
        char_start=selected_span.char_start if selected_span is not None else None,
        char_end=selected_span.char_end if selected_span is not None else None,
        source_locator=base_page.source_locator,
        canonical_references=canonical_references,
    )
