from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterator
from uuid import UUID
from xml.etree import ElementTree as ET

from .evidence_models import (
    DocxEmbeddedImageAnchor,
    DocxParagraphAnchor,
    DocxTableCellAnchor,
    SourceDocumentIdentity,
    SourceEvidence,
    SourceEvidenceArtifact,
    SourceEvidenceWarning,
    source_anchor_locator,
)
from .models import DocumentInspection, DocumentKind, DocumentRoute, SourceMethod

DOCX_MAIN_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
MAX_DOCX_ENTRIES = 4096
MAX_DOCX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024
MAX_DOCX_ENTRY_UNCOMPRESSED = 128 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 1000
MAX_XML_BYTES = 64 * 1024 * 1024

TRACKED_CHANGE_TAGS = {"ins", "del", "moveFrom", "moveTo"}
UNSUPPORTED_TEXT_CONTAINER_TAGS = {"txbxContent"}


class DocxProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class NumberingLevel:
    level: int
    start: int
    num_format: str
    level_text: str


@dataclass
class NumberingDefinition:
    levels: dict[int, NumberingLevel] = field(default_factory=dict)


@dataclass
class NumberingState:
    definitions: dict[str, NumberingDefinition]
    style_num_pr: dict[str, tuple[str, int]]
    counters: dict[tuple[str, int], int] = field(default_factory=dict)


@dataclass
class ParseState:
    job_id: UUID
    numbering: NumberingState
    image_relationships: set[str]
    evidence: list[SourceEvidence] = field(default_factory=list)
    warnings: list[SourceEvidenceWarning] = field(default_factory=list)
    warning_keys: set[tuple[str, str | None]] = field(default_factory=set)
    order_index: int = 1
    paragraph_index: int = 0
    table_index: int = 0
    image_index: int = 0

    def warn(
        self,
        code: str,
        message: str,
        *,
        source_locator: str | None = None,
        blocks_complete_coverage: bool = False,
    ) -> None:
        key = (code, source_locator)
        if key in self.warning_keys:
            return
        self.warning_keys.add(key)
        self.warnings.append(
            SourceEvidenceWarning(
                code=code,
                message=message,
                source_locator=source_locator,
                blocks_complete_coverage=blocks_complete_coverage,
            )
        )

    def next_evidence_id(self) -> str:
        return f"ev-{self.job_id}-s{self.order_index:06d}"

    def append_evidence(
        self,
        *,
        text: str,
        anchor: DocxParagraphAnchor | DocxTableCellAnchor | DocxEmbeddedImageAnchor,
        block_kind: str,
        parent_group_id: str | None = None,
    ) -> None:
        self.evidence.append(
            SourceEvidence(
                evidence_id=self.next_evidence_id(),
                order_index=self.order_index,
                text=text,
                source_method=SourceMethod.NATIVE_DOCX_TEXT,
                source_anchor=anchor,
                block_kind=block_kind,
                parent_group_id=parent_group_id,
            )
        )
        self.order_index += 1


def _local_name(value: str) -> str:
    return value.rsplit("}", maxsplit=1)[-1]


def _attribute(element: ET.Element, local_name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local_name(key) == local_name:
            return value
    return None


def _children(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == local_name]


def _first_child(element: ET.Element | None, local_name: str) -> ET.Element | None:
    if element is None:
        return None
    return next((child for child in element if _local_name(child.tag) == local_name), None)


def _descendant(element: ET.Element | None, *path: str) -> ET.Element | None:
    current = element
    for name in path:
        current = _first_child(current, name)
        if current is None:
            return None
    return current


def _xml_root(archive: zipfile.ZipFile, name: str, *, required: bool = False) -> ET.Element | None:
    try:
        info = archive.getinfo(name)
    except KeyError:
        if required:
            raise DocxProcessingError(f"DOCX package is missing required part {name}.")
        return None
    if info.file_size > MAX_XML_BYTES:
        raise DocxProcessingError(f"DOCX XML part {name} exceeds the safe parsing limit.")
    try:
        payload = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise DocxProcessingError(f"DOCX part {name} could not be read safely.") from exc
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise DocxProcessingError(f"DOCX XML part {name} contains a forbidden DTD/entity declaration.")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise DocxProcessingError(f"DOCX XML part {name} is malformed.") from exc


def _validate_archive(source_path: Path) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(source_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise DocxProcessingError("The uploaded DOCX is not a readable OOXML ZIP package.") from exc

    try:
        infos = archive.infolist()
        if not infos:
            raise DocxProcessingError("The uploaded DOCX package is empty.")
        if len(infos) > MAX_DOCX_ENTRIES:
            raise DocxProcessingError("The DOCX package contains too many ZIP entries to process safely.")

        total_uncompressed = 0
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise DocxProcessingError("The DOCX package contains an unsafe ZIP entry path.")
            if info.flag_bits & 0x1:
                raise DocxProcessingError("Encrypted DOCX ZIP entries are not supported.")
            if info.file_size > MAX_DOCX_ENTRY_UNCOMPRESSED:
                raise DocxProcessingError("A DOCX package entry exceeds the safe uncompressed-size limit.")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_DOCX_TOTAL_UNCOMPRESSED:
                raise DocxProcessingError("The DOCX package expands beyond the safe uncompressed-size limit.")
            if info.file_size and info.compress_size:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_DOCX_COMPRESSION_RATIO:
                    raise DocxProcessingError("The DOCX package contains a suspicious compression ratio.")

        names = {info.filename for info in infos}
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise DocxProcessingError("The uploaded ZIP is not a valid Word DOCX package.")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise DocxProcessingError("Macro/VBA content is not accepted in DOCX input.")

        content_types = _xml_root(archive, "[Content_Types].xml", required=True)
        assert content_types is not None
        main_type = None
        for element in content_types.iter():
            if _local_name(element.tag) != "Override":
                continue
            if _attribute(element, "PartName") == "/word/document.xml":
                main_type = _attribute(element, "ContentType")
                break
        if main_type != DOCX_MAIN_CONTENT_TYPE:
            raise DocxProcessingError("The package does not declare a supported WordprocessingML main document.")
        return archive
    except Exception:
        archive.close()
        raise


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_relationships(archive: zipfile.ZipFile, state: ParseState) -> None:
    root = _xml_root(archive, "word/_rels/document.xml.rels")
    if root is None:
        return
    for relation in root.iter():
        if _local_name(relation.tag) != "Relationship":
            continue
        rel_id = _attribute(relation, "Id")
        target_mode = (_attribute(relation, "TargetMode") or "").lower()
        rel_type = _attribute(relation, "Type") or ""
        if target_mode == "external":
            state.warn(
                "DOCX_EXTERNAL_RELATIONSHIP_PRESENT",
                "The document contains an external relationship. Law-Rag records it but never fetches external content during ingestion.",
                blocks_complete_coverage=False,
            )
        if rel_id and rel_type.endswith("/image"):
            state.image_relationships.add(rel_id)


def _level_from_element(level_element: ET.Element, level_index: int) -> NumberingLevel | None:
    start_element = _first_child(level_element, "start")
    format_element = _first_child(level_element, "numFmt")
    text_element = _first_child(level_element, "lvlText")
    try:
        start = int(_attribute(start_element, "val") or "1")
    except ValueError:
        start = 1
    num_format = _attribute(format_element, "val") if format_element is not None else None
    level_text = _attribute(text_element, "val") if text_element is not None else None
    if not num_format or level_text is None:
        return None
    return NumberingLevel(
        level=level_index,
        start=max(1, start),
        num_format=num_format,
        level_text=level_text,
    )


def _parse_numbering(archive: zipfile.ZipFile) -> dict[str, NumberingDefinition]:
    root = _xml_root(archive, "word/numbering.xml")
    if root is None:
        return {}

    abstract: dict[str, NumberingDefinition] = {}
    for node in root:
        if _local_name(node.tag) != "abstractNum":
            continue
        abstract_id = _attribute(node, "abstractNumId")
        if abstract_id is None:
            continue
        definition = NumberingDefinition()
        for level_element in _children(node, "lvl"):
            try:
                level_index = int(_attribute(level_element, "ilvl") or "0")
            except ValueError:
                continue
            parsed = _level_from_element(level_element, level_index)
            if parsed is not None:
                definition.levels[level_index] = parsed
        abstract[abstract_id] = definition

    definitions: dict[str, NumberingDefinition] = {}
    for node in root:
        if _local_name(node.tag) != "num":
            continue
        num_id = _attribute(node, "numId")
        abstract_ref = _first_child(node, "abstractNumId")
        abstract_id = _attribute(abstract_ref, "val") if abstract_ref is not None else None
        if num_id is None or abstract_id is None or abstract_id not in abstract:
            continue
        definition = NumberingDefinition(levels=dict(abstract[abstract_id].levels))
        for override in _children(node, "lvlOverride"):
            try:
                level_index = int(_attribute(override, "ilvl") or "0")
            except ValueError:
                continue
            overridden_level = _first_child(override, "lvl")
            if overridden_level is not None:
                parsed = _level_from_element(overridden_level, level_index)
                if parsed is not None:
                    definition.levels[level_index] = parsed
            start_override = _first_child(override, "startOverride")
            if start_override is not None and level_index in definition.levels:
                try:
                    value = max(1, int(_attribute(start_override, "val") or "1"))
                except ValueError:
                    value = definition.levels[level_index].start
                old = definition.levels[level_index]
                definition.levels[level_index] = NumberingLevel(
                    level=old.level,
                    start=value,
                    num_format=old.num_format,
                    level_text=old.level_text,
                )
        definitions[num_id] = definition
    return definitions


def _num_pr(element: ET.Element | None) -> tuple[str, int] | None:
    num_pr = _descendant(element, "pPr", "numPr")
    if num_pr is None:
        return None
    num_id_element = _first_child(num_pr, "numId")
    level_element = _first_child(num_pr, "ilvl")
    num_id = _attribute(num_id_element, "val") if num_id_element is not None else None
    if not num_id or num_id == "0":
        return None
    try:
        level = int(_attribute(level_element, "val") or "0") if level_element is not None else 0
    except ValueError:
        level = 0
    return num_id, max(0, level)


def _parse_styles(archive: zipfile.ZipFile) -> dict[str, tuple[str, int]]:
    root = _xml_root(archive, "word/styles.xml")
    if root is None:
        return {}
    raw: dict[str, tuple[tuple[str, int] | None, str | None]] = {}
    for style in root:
        if _local_name(style.tag) != "style" or (_attribute(style, "type") or "") != "paragraph":
            continue
        style_id = _attribute(style, "styleId")
        if not style_id:
            continue
        based_on_element = _first_child(style, "basedOn")
        based_on = _attribute(based_on_element, "val") if based_on_element is not None else None
        raw[style_id] = (_num_pr(style), based_on)

    resolved: dict[str, tuple[str, int]] = {}

    def resolve(style_id: str, stack: set[str]) -> tuple[str, int] | None:
        if style_id in resolved:
            return resolved[style_id]
        if style_id in stack or style_id not in raw:
            return None
        direct, based_on = raw[style_id]
        if direct is not None:
            resolved[style_id] = direct
            return direct
        if based_on:
            inherited = resolve(based_on, stack | {style_id})
            if inherited is not None:
                resolved[style_id] = inherited
                return inherited
        return None

    for style_id in raw:
        resolve(style_id, set())
    return resolved


def _paragraph_num_pr(paragraph: ET.Element, state: ParseState) -> tuple[str, int] | None:
    direct = _num_pr(paragraph)
    if direct is not None:
        return direct
    style_element = _descendant(paragraph, "pPr", "pStyle")
    style_id = _attribute(style_element, "val") if style_element is not None else None
    return state.numbering.style_num_pr.get(style_id or "")


def _roman(value: int) -> str:
    values = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    remaining = max(1, value)
    result: list[str] = []
    for number, token in values:
        while remaining >= number:
            result.append(token)
            remaining -= number
    return "".join(result)


def _letters(value: int) -> str:
    value = max(1, value)
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _chinese_number(value: int) -> str:
    if value <= 0 or value > 9999:
        return str(value)
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    units = ((1000, "千"), (100, "百"), (10, "十"))
    remaining = value
    result = ""
    zero_pending = False
    for unit_value, unit_text in units:
        digit = remaining // unit_value
        remaining %= unit_value
        if digit:
            if zero_pending and result:
                result += "零"
            if not (unit_value == 10 and digit == 1 and not result):
                result += digits[digit]
            result += unit_text
            zero_pending = False
        elif result and remaining:
            zero_pending = True
    if remaining:
        if zero_pending:
            result += "零"
        result += digits[remaining]
    return result


def _format_number(value: int, num_format: str) -> str | None:
    if num_format == "decimal":
        return str(value)
    if num_format == "decimalZero":
        return f"{value:02d}"
    if num_format == "upperLetter":
        return _letters(value)
    if num_format == "lowerLetter":
        return _letters(value).lower()
    if num_format == "upperRoman":
        return _roman(value)
    if num_format == "lowerRoman":
        return _roman(value).lower()
    if num_format in {"chineseCounting", "chineseCountingThousand", "ideographDigital"}:
        return _chinese_number(value)
    if num_format == "bullet":
        return ""
    return None


def _numbering_prefix(paragraph: ET.Element, state: ParseState, locator: str) -> str:
    num_pr = _paragraph_num_pr(paragraph, state)
    if num_pr is None:
        return ""
    num_id, level = num_pr
    definition = state.numbering.definitions.get(num_id)
    if definition is None or level not in definition.levels:
        state.warn(
            "DOCX_NUMBERING_DEFINITION_MISSING",
            "A Word list/numbered paragraph could not be resolved from numbering.xml; visible numbering may be incomplete.",
            source_locator=locator,
            blocks_complete_coverage=True,
        )
        return ""

    current_level = definition.levels[level]
    key = (num_id, level)
    current = state.numbering.counters.get(key, current_level.start - 1) + 1
    state.numbering.counters[key] = current
    for other_key in list(state.numbering.counters):
        if other_key[0] == num_id and other_key[1] > level:
            del state.numbering.counters[other_key]

    rendered = current_level.level_text
    for placeholder_level in range(9):
        placeholder = f"%{placeholder_level + 1}"
        if placeholder not in rendered:
            continue
        level_definition = definition.levels.get(placeholder_level)
        if level_definition is None:
            state.warn(
                "DOCX_NUMBERING_LEVEL_MISSING",
                "A multilevel Word numbering template references an unavailable level.",
                source_locator=locator,
                blocks_complete_coverage=True,
            )
            return ""
        counter = state.numbering.counters.get(
            (num_id, placeholder_level),
            level_definition.start,
        )
        token = _format_number(counter, level_definition.num_format)
        if token is None:
            state.warn(
                "DOCX_NUMBERING_FORMAT_UNSUPPORTED",
                f"Word numbering format {level_definition.num_format!r} is not yet supported safely.",
                source_locator=locator,
                blocks_complete_coverage=True,
            )
            return ""
        rendered = rendered.replace(placeholder, token)
    if current_level.num_format == "bullet" and not rendered:
        rendered = "•"
    return rendered.strip()


def _paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        name = _local_name(node.tag)
        if name == "delText":
            continue
        if name == "t" and node.text:
            parts.append(node.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _paragraph_style(paragraph: ET.Element) -> str | None:
    style = _descendant(paragraph, "pPr", "pStyle")
    return _attribute(style, "val") if style is not None else None


def _iter_block_children(parent: ET.Element) -> Iterator[ET.Element]:
    for child in parent:
        name = _local_name(child.tag)
        if name in {"p", "tbl"}:
            yield child
            continue
        if name in {"sdt", "sdtContent", "customXml", "ins", "moveTo"}:
            yield from _iter_block_children(child)


def _image_relationship_ids(element: ET.Element, valid_ids: set[str]) -> list[str]:
    found: list[str] = []
    for node in element.iter():
        for key, value in node.attrib.items():
            if _local_name(key) in {"embed", "id"} and value in valid_ids and value not in found:
                found.append(value)
    return found


def _append_embedded_images(
    element: ET.Element,
    state: ParseState,
    *,
    parent_locator: str,
    parent_group_id: str | None,
) -> None:
    for relationship_id in _image_relationship_ids(element, state.image_relationships):
        state.image_index += 1
        state.append_evidence(
            text="",
            anchor=DocxEmbeddedImageAnchor(
                image_index=state.image_index,
                relationship_id=relationship_id,
                parent_locator=parent_locator,
            ),
            block_kind="IMAGE",
            parent_group_id=parent_group_id,
        )
        state.warn(
            "DOCX_EMBEDDED_IMAGE_REQUIRES_OCR_REVIEW",
            "An embedded image was inventoried but is not OCR-processed during Stage 14.2.",
            source_locator=parent_locator,
            blocks_complete_coverage=True,
        )


def _append_paragraph(
    paragraph: ET.Element,
    state: ParseState,
    *,
    table_context: tuple[int, int, int, int] | None = None,
) -> None:
    if table_context is None:
        state.paragraph_index += 1
        anchor = DocxParagraphAnchor(paragraph_index=state.paragraph_index)
        block_kind = "TEXT"
        parent_group_id = None
    else:
        table_index, row_index, cell_index, paragraph_index = table_context
        anchor = DocxTableCellAnchor(
            table_index=table_index,
            row_index=row_index,
            cell_index=cell_index,
            paragraph_index=paragraph_index,
        )
        block_kind = "TABLE_CELL"
        parent_group_id = f"docx-table-{table_index:04d}"

    locator = source_anchor_locator(anchor)
    prefix = _numbering_prefix(paragraph, state, locator)
    text = _paragraph_text(paragraph)
    if prefix and text and not text.startswith(prefix):
        text = f"{prefix} {text}"
    elif prefix and not text:
        text = prefix

    if text:
        state.append_evidence(
            text=text,
            anchor=anchor,
            block_kind=block_kind,
            parent_group_id=parent_group_id,
        )

    _append_embedded_images(
        paragraph,
        state,
        parent_locator=locator,
        parent_group_id=parent_group_id,
    )

    style_id = _paragraph_style(paragraph)
    if style_id and len(style_id) > 128:
        state.warn(
            "DOCX_STYLE_IDENTIFIER_SUSPICIOUS",
            "A paragraph style identifier is unexpectedly long and was not interpreted further.",
            source_locator=locator,
        )


def _process_table(table: ET.Element, state: ParseState) -> None:
    state.table_index += 1
    table_index = state.table_index
    rows = _children(table, "tr")
    for row_index, row in enumerate(rows, start=1):
        cells = _children(row, "tc")
        for cell_index, cell in enumerate(cells, start=1):
            paragraph_index = 0
            for block in _iter_block_children(cell):
                name = _local_name(block.tag)
                if name == "p":
                    paragraph_index += 1
                    _append_paragraph(
                        block,
                        state,
                        table_context=(table_index, row_index, cell_index, paragraph_index),
                    )
                elif name == "tbl":
                    _process_table(block, state)


def _scan_document_features(archive: zipfile.ZipFile, document_root: ET.Element, state: ParseState) -> None:
    names = set(archive.namelist())
    local_names = {_local_name(node.tag) for node in document_root.iter()}
    if local_names & TRACKED_CHANGE_TAGS:
        state.warn(
            "DOCX_TRACKED_CHANGES_PRESENT",
            "Tracked changes are present. Extracted visible text is retained, but complete legal coverage is blocked until revision semantics are reviewed.",
            blocks_complete_coverage=True,
        )
    if local_names & UNSUPPORTED_TEXT_CONTAINER_TAGS:
        state.warn(
            "DOCX_TEXTBOX_PRESENT",
            "Text-box content is present and cannot yet be assigned a fully reliable standalone structural anchor.",
            blocks_complete_coverage=True,
        )
    if "word/comments.xml" in names:
        state.warn(
            "DOCX_COMMENTS_PRESENT",
            "Word comments are present and are not treated as operative contract text during native ingestion.",
        )
    for prefix, code, label in (
        ("word/header", "DOCX_HEADER_PRESENT", "header"),
        ("word/footer", "DOCX_FOOTER_PRESENT", "footer"),
    ):
        if any(name.startswith(prefix) and name.endswith(".xml") for name in names):
            state.warn(
                code,
                f"The document contains {label} content that Stage 14.2 does not yet include in canonical contract text.",
                blocks_complete_coverage=True,
            )
    if "word/footnotes.xml" in names:
        state.warn(
            "DOCX_FOOTNOTES_PRESENT",
            "Footnotes are present and are not yet included in canonical contract text.",
            blocks_complete_coverage=True,
        )
    if "word/endnotes.xml" in names:
        state.warn(
            "DOCX_ENDNOTES_PRESENT",
            "Endnotes are present and are not yet included in canonical contract text.",
            blocks_complete_coverage=True,
        )


def inspect_docx(
    *,
    job_id: UUID,
    filename: str,
    media_type: str,
    source_path: Path,
) -> tuple[DocumentInspection, SourceEvidenceArtifact]:
    archive = _validate_archive(source_path)
    try:
        numbering = NumberingState(
            definitions=_parse_numbering(archive),
            style_num_pr=_parse_styles(archive),
        )
        state = ParseState(
            job_id=job_id,
            numbering=numbering,
            image_relationships=set(),
        )
        _parse_relationships(archive, state)
        document_root = _xml_root(archive, "word/document.xml", required=True)
        assert document_root is not None
        _scan_document_features(archive, document_root, state)

        body = next((node for node in document_root.iter() if _local_name(node.tag) == "body"), None)
        if body is None:
            raise DocxProcessingError("DOCX document.xml does not contain a document body.")

        for block in _iter_block_children(body):
            if _local_name(block.tag) == "p":
                _append_paragraph(block, state)
            else:
                _process_table(block, state)

        if not any(item.text.strip() for item in state.evidence if item.block_kind != "IMAGE"):
            raise DocxProcessingError("DOCX contains no supported native contract text.")

        source_document = SourceDocumentIdentity(
            job_id=job_id,
            filename=filename,
            media_type=media_type,
            document_kind=DocumentKind.DOCX,
            source_sha256=_source_sha256(source_path),
            size_bytes=source_path.stat().st_size,
        )
        artifact = SourceEvidenceArtifact(
            job_id=job_id,
            source_document=source_document,
            evidence=state.evidence,
            warnings=state.warnings,
        )
        blocking = any(item.blocks_complete_coverage for item in state.warnings)
        warning_text = [f"{item.code}: {item.message}" for item in state.warnings]
        inspection = DocumentInspection(
            job_id=job_id,
            filename=filename,
            media_type=media_type,
            document_kind=DocumentKind.DOCX,
            page_count=0,
            route=DocumentRoute.NATIVE_TEXT,
            native_text_pages=0,
            ocr_required_pages=0,
            pages=[],
            evidence_count=len(state.evidence),
            warnings=warning_text,
            status="partial" if blocking else "inspected",
        )
        return inspection, artifact
    finally:
        archive.close()
