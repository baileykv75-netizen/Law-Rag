from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from .canonical_extraction import build_canonical_contract
from .contract_models import CanonicalContract, EvidenceUnit, ExtractionWarning, StructureSummary
from .evidence_models import (
    PageRegionAnchor,
    PageTextAnchor,
    SourceEvidenceArtifact,
)
from .models import (
    DocumentInspection,
    DocumentKind,
    OcrPageState,
    OcrRunResult,
    PageEvidence,
    PageRoute,
    SourceMethod,
)
from .storage import (
    job_contract_path,
    job_document_path,
    job_evidence_path,
    job_ocr_path,
)


class StructureProcessingError(RuntimeError):
    pass


class StructureIncompleteError(StructureProcessingError):
    pass


def _read_required_inputs(job_id: UUID) -> tuple[bytes, bytes, dict]:
    document_path = job_document_path(job_id)
    evidence_path = job_evidence_path(job_id)
    if not document_path.exists() or not evidence_path.exists():
        raise StructureProcessingError(f"Document job {job_id} does not exist or is incomplete.")

    try:
        document_bytes = document_path.read_bytes()
        evidence_bytes = evidence_path.read_bytes()
        document_payload = json.loads(document_bytes.decode("utf-8"))
    except Exception as exc:
        raise StructureProcessingError(
            "Persisted document evidence is malformed and cannot be structured safely."
        ) from exc
    if not isinstance(document_payload, dict):
        raise StructureProcessingError(
            "Persisted document metadata is malformed and cannot be structured safely."
        )
    return document_bytes, evidence_bytes, document_payload


def _document_kind(document_payload: dict) -> DocumentKind:
    try:
        return DocumentKind(str(document_payload["document_kind"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise StructureProcessingError(
            "Persisted document metadata does not contain a valid document kind."
        ) from exc


def _load_paginated_inputs(
    job_id: UUID,
    *,
    document_bytes: bytes,
    evidence_bytes: bytes,
    document_payload: dict,
) -> tuple[DocumentInspection, OcrRunResult | None, bytes]:
    try:
        evidence_payload = json.loads(evidence_bytes.decode("utf-8"))
        if not isinstance(evidence_payload, list):
            raise ValueError("legacy evidence must be a list")
        inspection = DocumentInspection.model_validate(
            {**document_payload, "pages": evidence_payload}
        )
    except Exception as exc:
        raise StructureProcessingError(
            "Persisted document evidence is malformed and cannot be structured safely."
        ) from exc

    if inspection.document_kind not in {DocumentKind.PDF, DocumentKind.IMAGE}:
        raise StructureProcessingError(
            "Paginated evidence may only be used for PDF/image jobs."
        )

    ocr_result: OcrRunResult | None = None
    ocr_bytes = b""
    if inspection.ocr_required_pages:
        ocr_path = job_ocr_path(job_id)
        if not ocr_path.exists():
            raise StructureIncompleteError(
                "This document still has OCR-required pages. Run local OCR successfully before generating structure."
            )
        try:
            ocr_bytes = ocr_path.read_bytes()
            ocr_result = OcrRunResult.model_validate_json(ocr_bytes)
        except Exception as exc:
            raise StructureProcessingError(
                "Persisted OCR evidence is malformed and cannot be structured safely."
            ) from exc

        if ocr_result.job_id != job_id or ocr_result.page_count != inspection.page_count:
            raise StructureProcessingError(
                "OCR evidence does not match the document job/page count."
            )

        page_states = {page.page_number: page.state for page in ocr_result.pages}
        incomplete_pages: list[int] = []
        for page in inspection.pages:
            if page.route != PageRoute.OCR_REQUIRED:
                continue
            state = page_states.get(page.page_number)
            if state not in {
                OcrPageState.OCR_COMPLETE,
                OcrPageState.OCR_LOW_CONFIDENCE,
            }:
                incomplete_pages.append(page.page_number)
        if incomplete_pages:
            rendered = ", ".join(str(value) for value in incomplete_pages)
            raise StructureIncompleteError(
                f"OCR evidence is incomplete for page(s): {rendered}. Resolve OCR failure/no-text states before structuring."
            )

    fingerprint = hashlib.sha256(
        document_bytes + b"\n" + evidence_bytes + b"\n" + ocr_bytes
    ).digest()
    return inspection, ocr_result, fingerprint


def _load_docx_inputs(
    job_id: UUID,
    *,
    document_bytes: bytes,
    evidence_bytes: bytes,
    document_payload: dict,
) -> tuple[DocumentInspection, SourceEvidenceArtifact, bytes]:
    try:
        inspection = DocumentInspection.model_validate({**document_payload, "pages": []})
        artifact = SourceEvidenceArtifact.model_validate_json(evidence_bytes)
    except Exception as exc:
        raise StructureProcessingError(
            "Persisted DOCX source evidence is malformed and cannot be structured safely."
        ) from exc

    if inspection.document_kind != DocumentKind.DOCX:
        raise StructureProcessingError("DOCX evidence was attached to a non-DOCX job.")
    if inspection.page_count != 0 or inspection.pages:
        raise StructureProcessingError(
            "DOCX metadata must remain non-paginated; synthetic page evidence is not accepted."
        )
    if artifact.job_id != job_id or artifact.source_document.job_id != job_id:
        raise StructureProcessingError("DOCX source evidence does not match the document job.")
    if artifact.source_document.document_kind != DocumentKind.DOCX:
        raise StructureProcessingError("DOCX source evidence declares an incompatible source kind.")
    if artifact.source_document.filename != inspection.filename:
        raise StructureProcessingError("DOCX source evidence filename does not match document metadata.")

    fingerprint = hashlib.sha256(document_bytes + b"\n" + evidence_bytes).digest()
    return inspection, artifact, fingerprint


def _native_units(
    page_text: str,
    page_number: int,
    evidence_id: str,
    order_start: int,
) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    cursor = 0
    order = order_start
    for raw_line in page_text.splitlines(keepends=True):
        line_without_break = raw_line.rstrip("\r\n")
        stripped = line_without_break.strip()
        line_start = cursor + (
            len(line_without_break) - len(line_without_break.lstrip())
        )
        cursor += len(raw_line)
        if not stripped:
            continue
        char_start = line_start
        char_end = char_start + len(stripped)
        units.append(
            EvidenceUnit(
                unit_id=f"unit-p{page_number:04d}-{order:04d}",
                page_number=page_number,
                order_index=order,
                text=stripped,
                evidence_ids=[evidence_id],
                source_method=SourceMethod.NATIVE_PDF_TEXT,
                source_anchor=PageTextAnchor(
                    page_number=page_number,
                    char_start=char_start,
                    char_end=char_end,
                ),
                char_start=char_start,
                char_end=char_end,
            )
        )
        order += 1
    if not units and page_text.strip():
        text = page_text.strip()
        start = max(page_text.find(text), 0)
        units.append(
            EvidenceUnit(
                unit_id=f"unit-p{page_number:04d}-{order:04d}",
                page_number=page_number,
                order_index=order,
                text=text,
                evidence_ids=[evidence_id],
                source_method=SourceMethod.NATIVE_PDF_TEXT,
                source_anchor=PageTextAnchor(
                    page_number=page_number,
                    char_start=start,
                    char_end=start + len(text),
                ),
                char_start=start,
                char_end=start + len(text),
            )
        )
    return units


def build_evidence_stream(
    inspection: DocumentInspection,
    ocr_result: OcrRunResult | None,
) -> list[EvidenceUnit]:
    """Build the legacy PDF/image stream with typed page anchors."""

    if inspection.document_kind == DocumentKind.DOCX:
        raise StructureProcessingError(
            "DOCX uses SourceEvidenceArtifact rather than page-shaped evidence."
        )

    ocr_pages = {
        page.page_number: page for page in (ocr_result.pages if ocr_result else [])
    }
    units: list[EvidenceUnit] = []
    global_order = 1

    for page in inspection.pages:
        if page.route == PageRoute.NATIVE_TEXT_USABLE:
            page_units = _native_units(
                page.text,
                page.page_number,
                page.evidence_id,
                global_order,
            )
            units.extend(page_units)
            global_order += len(page_units)
            continue

        ocr_page = ocr_pages.get(page.page_number)
        if ocr_page is None:
            raise StructureIncompleteError(
                f"Missing OCR evidence for page {page.page_number}."
            )
        for block in sorted(ocr_page.blocks, key=lambda value: value.block_index):
            text = block.text.strip()
            if not text:
                continue
            units.append(
                EvidenceUnit(
                    unit_id=f"unit-p{page.page_number:04d}-{global_order:04d}",
                    page_number=page.page_number,
                    order_index=global_order,
                    text=text,
                    evidence_ids=[block.evidence_id],
                    source_method=SourceMethod.OCR,
                    source_anchor=PageRegionAnchor(
                        page_number=page.page_number,
                        bbox=block.bbox,
                        polygon=block.polygon,
                    ),
                    bbox=block.bbox,
                    polygon=block.polygon,
                    confidence=block.confidence,
                )
            )
            global_order += 1
    return units


def _docx_evidence_stream(
    artifact: SourceEvidenceArtifact,
) -> tuple[list[EvidenceUnit], list[ExtractionWarning], bool]:
    units: list[EvidenceUnit] = []
    locator_to_ids: dict[str, list[str]] = {}

    for evidence in sorted(artifact.evidence, key=lambda item: item.order_index):
        if evidence.source_locator:
            locator_to_ids.setdefault(evidence.source_locator, []).append(evidence.evidence_id)
        if evidence.block_kind == "IMAGE" or not evidence.text.strip():
            continue
        units.append(
            EvidenceUnit(
                unit_id=f"unit-docx-{evidence.order_index:06d}",
                page_number=None,
                order_index=evidence.order_index,
                text=evidence.text.strip(),
                evidence_ids=[evidence.evidence_id],
                source_method=evidence.source_method,
                source_anchor=evidence.source_anchor,
                block_kind=evidence.block_kind,
                parent_group_id=evidence.parent_group_id,
                confidence=evidence.confidence,
            )
        )

    source_warnings: list[ExtractionWarning] = []
    blocking = False
    for warning in artifact.warnings:
        blocking = blocking or warning.blocks_complete_coverage
        source_warnings.append(
            ExtractionWarning(
                warning_id=f"warning-{len(source_warnings) + 1:04d}",
                code=warning.code,
                message=warning.message,
                page_number=None,
                evidence_ids=(
                    locator_to_ids.get(warning.source_locator, [])
                    if warning.source_locator
                    else []
                ),
            )
        )
    return units, source_warnings, blocking


def _persist_contract(contract: CanonicalContract) -> None:
    job_contract_path(contract.job_id).write_text(
        json.dumps(
            contract.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def build_contract_structure(job_id: UUID) -> CanonicalContract:
    document_bytes, evidence_bytes, document_payload = _read_required_inputs(job_id)
    kind = _document_kind(document_payload)

    if kind == DocumentKind.DOCX:
        inspection, artifact, fingerprint_bytes = _load_docx_inputs(
            job_id,
            document_bytes=document_bytes,
            evidence_bytes=evidence_bytes,
            document_payload=document_payload,
        )
        units, source_warnings, partial_source = _docx_evidence_stream(artifact)
        contract = build_canonical_contract(
            job_id=job_id,
            filename=inspection.filename,
            fingerprint_bytes=fingerprint_bytes,
            units=units,
            source_warnings=source_warnings,
            partial_source=partial_source,
        )
    else:
        inspection, ocr_result, fingerprint_bytes = _load_paginated_inputs(
            job_id,
            document_bytes=document_bytes,
            evidence_bytes=evidence_bytes,
            document_payload=document_payload,
        )
        units = build_evidence_stream(inspection, ocr_result)
        contract = build_canonical_contract(
            job_id=job_id,
            filename=inspection.filename,
            fingerprint_bytes=fingerprint_bytes,
            units=units,
        )

    _persist_contract(contract)
    return contract


def load_contract_structure(job_id: UUID) -> CanonicalContract:
    path = job_contract_path(job_id)
    if not path.exists():
        raise FileNotFoundError(
            f"Canonical contract structure for job {job_id} has not been generated."
        )
    try:
        return CanonicalContract.model_validate_json(path.read_bytes())
    except Exception as exc:
        raise StructureProcessingError(
            "Persisted canonical contract structure is malformed."
        ) from exc


def structure_summary(contract: CanonicalContract) -> StructureSummary:
    return StructureSummary(
        job_id=contract.job_id,
        schema_version=contract.schema_version,
        status=contract.status,
        title=contract.title_candidates[0].text if contract.title_candidates else None,
        clause_count=len(contract.clauses),
        party_count=len(contract.parties),
        date_count=len(contract.dates),
        money_count=len(contract.money_mentions),
        percentage_count=len(contract.percentages),
        identifier_count=len(contract.identifiers),
        unresolved_reference_count=sum(
            reference.resolution_state.value != "RESOLVED"
            for reference in contract.references
        ),
        warning_count=len(contract.warnings),
        clauses=contract.clauses,
        parties=contract.parties,
        dates=contract.dates,
        money_mentions=contract.money_mentions,
        percentages=contract.percentages,
        identifiers=contract.identifiers,
    )
