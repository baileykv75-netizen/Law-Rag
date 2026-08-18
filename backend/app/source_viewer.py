from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from .contract_models import CanonicalContract, SourceSpan
from .evidence_models import (
    DocxEmbeddedImageAnchor,
    DocxParagraphAnchor,
    DocxTableCellAnchor,
    SourceEvidenceArtifact,
)
from .models import OcrRunResult, PageEvidence
from .rendering import PdfRenderError, PdfiumPageRenderer
from .source_viewer_models import (
    CanonicalEvidenceReference,
    DocxLogicalCellParagraph,
    DocxLogicalImage,
    DocxLogicalParagraph,
    DocxLogicalTable,
    DocxLogicalTableCell,
    DocxLogicalTableRow,
    DocxSourceView,
    SourceEvidenceDetail,
)
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

    if document_kind == "docx":
        raise SourceViewerError(
            "DOCX has no stable source pagination. Use the logical DOCX source endpoint instead."
        )

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


def _evidence_path(job_id: UUID) -> Path:
    path = _job_dir(job_id) / "evidence.json"
    if not path.exists():
        raise FileNotFoundError(f"evidence.json does not exist for job {job_id}.")
    return path


def _load_page_evidence(job_id: UUID) -> list[PageEvidence]:
    path = _evidence_path(job_id)
    try:
        return _PAGE_EVIDENCE_ADAPTER.validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceViewerError(f"evidence.json is invalid: {exc}") from exc


def _load_source_evidence(job_id: UUID) -> SourceEvidenceArtifact:
    path = _evidence_path(job_id)
    try:
        artifact = SourceEvidenceArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise SourceViewerError(f"DOCX evidence.json is invalid: {exc}") from exc
    if artifact.job_id != job_id:
        raise SourceViewerError("DOCX evidence.json belongs to a different job.")
    if artifact.source_document.document_kind.value != "docx":
        raise SourceViewerError("Logical DOCX source requires a DOCX SourceEvidence artifact.")
    return artifact


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


def _canonical_matches(
    contract: CanonicalContract | None,
    evidence_id: str,
) -> tuple[list[CanonicalEvidenceReference], list[SourceSpan]]:
    references: list[CanonicalEvidenceReference] = []
    spans: list[SourceSpan] = []
    if contract is None:
        return references, spans
    seen: set[tuple[str, str]] = set()
    for object_type, object_id, span in _canonical_spans(contract):
        if evidence_id not in span.evidence_ids:
            continue
        key = (object_type, object_id)
        if key not in seen:
            references.append(CanonicalEvidenceReference(object_type=object_type, object_id=object_id))
            seen.add(key)
        spans.append(span)
    return references, spans


def _resolve_docx_evidence(job_id: UUID, evidence_id: str) -> SourceEvidenceDetail:
    artifact = _load_source_evidence(job_id)
    source = next((item for item in artifact.evidence if item.evidence_id == evidence_id), None)
    if source is None:
        raise FileNotFoundError(f"Evidence ID {evidence_id} cannot be resolved for job {job_id}.")

    contract = _load_contract(job_id)
    canonical_references, matching_spans = _canonical_matches(contract, evidence_id)
    selected_span = matching_spans[0] if matching_spans else None
    selected_anchor = (
        selected_span.source_anchor
        if selected_span is not None and selected_span.source_anchor is not None
        else source.source_anchor
    )
    return SourceEvidenceDetail(
        evidence_id=evidence_id,
        page_number=None,
        source_method=(selected_span.source_method if selected_span is not None else source.source_method),
        text=(selected_span.quote if selected_span is not None else source.text),
        source_anchor=selected_anchor,
        confidence=(
            selected_span.confidence
            if selected_span is not None and selected_span.confidence is not None
            else source.confidence
        ),
        char_start=selected_span.char_start if selected_span is not None else None,
        char_end=selected_span.char_end if selected_span is not None else None,
        source_locator=source.source_locator,
        canonical_references=canonical_references,
    )


def resolve_contract_evidence(job_id: UUID, evidence_id: str) -> SourceEvidenceDetail:
    normalized_id = evidence_id.strip()
    if not normalized_id:
        raise SourceViewerError("Evidence ID must not be empty.")

    metadata = _document_metadata(job_id)
    if str(metadata.get("document_kind")) == "docx":
        return _resolve_docx_evidence(job_id, normalized_id)

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

    canonical_references, matching_spans = _canonical_matches(contract, normalized_id)
    selected_span = matching_spans[0] if matching_spans else None
    if ocr_block is not None:
        return SourceEvidenceDetail(
            evidence_id=normalized_id,
            page_number=ocr_block.page_number,
            source_method=ocr_block.source_method,
            text=selected_span.quote if selected_span is not None else ocr_block.text,
            source_anchor=selected_span.source_anchor if selected_span is not None else None,
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
        source_anchor=selected_span.source_anchor if selected_span is not None else None,
        confidence=selected_span.confidence if selected_span is not None else None,
        bbox=selected_span.bbox if selected_span is not None else None,
        polygon=selected_span.polygon if selected_span is not None else None,
        char_start=selected_span.char_start if selected_span is not None else None,
        char_end=selected_span.char_end if selected_span is not None else None,
        source_locator=base_page.source_locator,
        canonical_references=canonical_references,
    )


def docx_source_view(job_id: UUID) -> DocxSourceView:
    metadata = _document_metadata(job_id)
    if str(metadata.get("document_kind")) != "docx":
        raise SourceViewerError("Logical DOCX source is available only for DOCX jobs.")

    artifact = _load_source_evidence(job_id)
    ordered = sorted(artifact.evidence, key=lambda item: item.order_index)
    blocks: list[tuple[int, object]] = []
    table_items: dict[int, list] = {}

    for item in ordered:
        anchor = item.source_anchor
        if isinstance(anchor, DocxParagraphAnchor):
            blocks.append(
                (
                    item.order_index,
                    DocxLogicalParagraph(
                        order_index=item.order_index,
                        evidence_id=item.evidence_id,
                        text=item.text,
                        source_locator=item.source_locator or "",
                        source_anchor=anchor,
                    ),
                )
            )
        elif isinstance(anchor, DocxTableCellAnchor):
            table_items.setdefault(anchor.table_index, []).append(item)
        elif isinstance(anchor, DocxEmbeddedImageAnchor):
            blocks.append(
                (
                    item.order_index,
                    DocxLogicalImage(
                        order_index=item.order_index,
                        evidence_id=item.evidence_id,
                        source_locator=item.source_locator or "",
                        source_anchor=anchor,
                    ),
                )
            )

    for table_index, items in table_items.items():
        rows: dict[int, dict[int, list[DocxLogicalCellParagraph]]] = {}
        for item in sorted(items, key=lambda value: value.order_index):
            anchor = item.source_anchor
            assert isinstance(anchor, DocxTableCellAnchor)
            paragraph = DocxLogicalCellParagraph(
                order_index=item.order_index,
                evidence_id=item.evidence_id,
                text=item.text,
                source_locator=item.source_locator or "",
                source_anchor=anchor,
            )
            rows.setdefault(anchor.row_index, {}).setdefault(anchor.cell_index, []).append(paragraph)

        rendered_rows: list[DocxLogicalTableRow] = []
        for row_index in sorted(rows):
            rendered_cells = [
                DocxLogicalTableCell(
                    row_index=row_index,
                    cell_index=cell_index,
                    paragraphs=rows[row_index][cell_index],
                )
                for cell_index in sorted(rows[row_index])
            ]
            rendered_rows.append(DocxLogicalTableRow(row_index=row_index, cells=rendered_cells))

        first_order = min(item.order_index for item in items)
        group_id = next((item.parent_group_id for item in items if item.parent_group_id), None)
        blocks.append(
            (
                first_order,
                DocxLogicalTable(
                    order_index=first_order,
                    table_index=table_index,
                    group_id=group_id or f"docx-table-{table_index:04d}",
                    rows=rendered_rows,
                ),
            )
        )

    return DocxSourceView(
        job_id=job_id,
        filename=artifact.source_document.filename,
        evidence_count=len(artifact.evidence),
        coverage_complete=not any(warning.blocks_complete_coverage for warning in artifact.warnings),
        warnings=artifact.warnings,
        blocks=[block for _, block in sorted(blocks, key=lambda pair: pair[0])],
    )
