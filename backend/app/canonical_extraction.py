from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable
from uuid import UUID

from .contract_models import (
    CanonicalContract,
    Clause,
    DateMention,
    EvidenceUnit,
    ExtractionConfidence,
    ExtractionProvenance,
    ExtractionWarning,
    IdentifierMention,
    MoneyMention,
    PartyMention,
    PercentageMention,
    ReferenceMention,
    ReferenceType,
    ResolutionState,
    SourceSpan,
    StructuredBlockCandidate,
    StructuredBlockKind,
    TitleCandidate,
    UnnumberedBlock,
)
from .evidence_models import (
    DocxParagraphAnchor,
    DocxTableCellAnchor,
    PageTextAnchor,
    SourceAnchor,
)
from .models import SourceMethod


ROLE_LABELS = (
    "甲方",
    "乙方",
    "丙方",
    "买方",
    "卖方",
    "出租方",
    "承租方",
    "委托方",
    "受托方",
    "发包方",
    "承包方",
    "采购方",
    "供应方",
    "用人单位",
    "劳动者",
)
ROLE_ALTERNATION = "|".join(re.escape(value) for value in ROLE_LABELS)
PARTY_PATTERN = re.compile(
    rf"(?P<role>{ROLE_ALTERNATION})\s*[:：]\s*(?P<name>.+?)(?=(?:{ROLE_ALTERNATION})\s*[:：]|$)"
)

DATE_PATTERN = re.compile(
    r"(?P<cn>(?P<cy>\d{4})年(?P<cm>\d{1,2})月(?P<cd>\d{1,2})日)"
    r"|(?P<sep>(?P<sy>\d{4})[-/](?P<sm>\d{1,2})[-/](?P<sd>\d{1,2}))"
)
DATE_LABEL_PATTERN = re.compile(r"(签订日期|签署日期|生效日期|履行日期|交付日期|日期)\s*[:：]?\s*$")

NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
MONEY_PATTERN = re.compile(
    rf"(?:人民币\s*)?(?:[¥￥]\s*)?(?P<number>{NUMBER})\s*(?P<unit>亿元|万元|千元|百元|元)"
    rf"|(?P<symbol>[¥￥])\s*(?P<symbol_number>{NUMBER})"
)
PERCENT_ARABIC_PATTERN = re.compile(r"(?<!\d)(?P<number>\d+(?:\.\d+)?)\s*[%％]")
PERCENT_CHINESE_PATTERN = re.compile(r"百分之(?P<number>[零〇一二三四五六七八九十百千万两]+)")

IDENTIFIER_PATTERN = re.compile(
    r"(?P<label>合同编号|项目编号|协议编号)\s*[:：]\s*(?P<value>[^\s，,；;]{1,64})"
)
ATTACHMENT_PATTERN = re.compile(r"(?:见|详见|参见|按照|根据|依照|依据)?\s*(附件\s*[一二三四五六七八九十百零〇两\d]+)")
ARTICLE_REFERENCE_PATTERN = re.compile(r"第[一二三四五六七八九十百零〇两\d]+条|(?<!\d)\d+(?:\.\d+)+条")

CLAUSE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?P<token>第[一二三四五六七八九十百零〇两\d]+条)\s*[：:、.]?\s*(?P<rest>.*)$"), "article"),
    (re.compile(r"^(?P<token>[一二三四五六七八九十百零〇两]+、)\s*(?P<rest>.+)$"), "cn-major"),
    (re.compile(r"^(?P<token>[（(][一二三四五六七八九十百零〇两]+[）)])\s*(?P<rest>.+)$"), "cn-sub"),
    (re.compile(r"^(?P<token>[（(]\d+[）)])\s*(?P<rest>.+)$"), "arabic-paren"),
    (re.compile(r"^(?P<token>\d+(?:\.\d+){1,2})(?:[.、]\s*|\s+)(?P<rest>.+)$"), "arabic-nested"),
    (re.compile(r"^(?P<token>\d+[.、])\s*(?P<rest>.+)$"), "arabic-major"),
)

CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _chinese_integer(text: str) -> int | None:
    if not text:
        return None
    if all(char in CHINESE_DIGITS for char in text):
        digits = "".join(str(CHINESE_DIGITS[char]) for char in text)
        try:
            return int(digits)
        except ValueError:
            return None

    total = 0
    section = 0
    number = 0
    seen = False
    for char in text:
        if char in CHINESE_DIGITS:
            number = CHINESE_DIGITS[char]
            seen = True
            continue
        unit = CHINESE_UNITS.get(char)
        if unit is None:
            return None
        seen = True
        if unit == 10000:
            section += number
            total += (section or 1) * unit
            section = 0
            number = 0
        else:
            section += (number or 1) * unit
            number = 0
    return total + section + number if seen else None


def _compact_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    rendered = format(normalized, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _provenance(extractor_id: str, confidence: ExtractionConfidence) -> ExtractionProvenance:
    return ExtractionProvenance(extractor_id=extractor_id, confidence=confidence)


def _subspan_anchor(unit: EvidenceUnit, start: int, end: int) -> SourceAnchor | None:
    anchor = unit.source_anchor
    if anchor is None:
        return None

    if isinstance(anchor, PageTextAnchor):
        base_start = unit.char_start if unit.char_start is not None else anchor.char_start
        absolute_start = (base_start + start) if base_start is not None else None
        absolute_end = (base_start + end) if base_start is not None else None
        return anchor.model_copy(
            update={"char_start": absolute_start, "char_end": absolute_end}
        )

    if isinstance(anchor, (DocxParagraphAnchor, DocxTableCellAnchor)):
        base_start = anchor.char_start or 0
        return anchor.model_copy(
            update={"char_start": base_start + start, "char_end": base_start + end}
        )

    return anchor


def _span(unit: EvidenceUnit, start: int = 0, end: int | None = None) -> SourceSpan:
    end = len(unit.text) if end is None else end
    quote = unit.text[start:end]
    native_start = unit.char_start + start if unit.char_start is not None else None
    native_end = unit.char_start + end if unit.char_start is not None else None
    return SourceSpan(
        page_number=unit.page_number,
        evidence_ids=unit.evidence_ids,
        source_method=unit.source_method,
        quote=quote,
        source_anchor=_subspan_anchor(unit, start, end),
        char_start=native_start,
        char_end=native_end,
        bbox=unit.bbox,
        polygon=unit.polygon,
        confidence=unit.confidence,
    )


def parse_clause_heading(text: str) -> tuple[str, str, int] | None:
    for pattern, kind in CLAUSE_PATTERNS:
        match = pattern.match(text.strip())
        if not match:
            continue
        token = match.group("token")
        rest = match.group("rest").strip()
        if not rest and kind != "article":
            continue
        if kind in {"article", "cn-major"}:
            level = 1
        elif kind in {"cn-sub", "arabic-paren"}:
            level = 2
        elif kind == "arabic-nested":
            numeric = token.rstrip(".、")
            parts = numeric.split(".")
            try:
                if int(parts[0]) > 999:
                    continue
            except ValueError:
                continue
            if rest.startswith(("元", "万元", "亿元", "%", "％", "年", "月", "日")):
                continue
            level = len(parts)
        else:
            try:
                if int(token.rstrip(".、")) > 999:
                    continue
            except ValueError:
                continue
            level = 1
        return token, rest, level
    return None


def _title_candidates(units: list[EvidenceUnit]) -> list[TitleCandidate]:
    candidates: list[TitleCandidate] = []
    preferred: list[EvidenceUnit] = []
    fallback: list[EvidenceUnit] = []
    for unit in units[:20]:
        text = unit.text.strip()
        if not (2 <= len(text) <= 80):
            continue
        if parse_clause_heading(text):
            continue
        if re.search(r"(合同|协议|契约|备忘录)$", text) or ("合同" in text and len(text) <= 40):
            preferred.append(unit)
        elif len(text) <= 40:
            fallback.append(unit)
    chosen = preferred[:3] if preferred else fallback[:1]
    for index, unit in enumerate(chosen, start=1):
        confidence = ExtractionConfidence.HIGH if unit in preferred else ExtractionConfidence.MEDIUM
        candidates.append(
            TitleCandidate(
                candidate_id=f"title-{index:03d}",
                text=unit.text,
                source_spans=[_span(unit)],
                provenance=_provenance("title.explicit-short-line", confidence),
            )
        )
    return candidates


def _build_clauses(
    units: list[EvidenceUnit],
    title_spans: set[tuple[int | None, str]],
) -> tuple[list[Clause], list[UnnumberedBlock]]:
    clauses: list[Clause] = []
    unnumbered: list[UnnumberedBlock] = []
    level_stack: dict[int, str] = {}
    current: Clause | None = None
    preamble_units: list[EvidenceUnit] = []

    def flush_preamble() -> None:
        nonlocal preamble_units
        if not preamble_units:
            return
        text = "\n".join(unit.text for unit in preamble_units).strip()
        if text:
            unnumbered.append(
                UnnumberedBlock(
                    block_id=f"unnumbered-{len(unnumbered) + 1:04d}",
                    text=text,
                    page_start=preamble_units[0].page_number,
                    page_end=preamble_units[-1].page_number,
                    source_spans=[_span(unit) for unit in preamble_units],
                    provenance=_provenance("clause.unnumbered-preamble", ExtractionConfidence.LOW),
                )
            )
        preamble_units = []

    for unit in units:
        if (unit.page_number, unit.text) in title_spans and current is None:
            continue
        parsed = parse_clause_heading(unit.text)
        if parsed:
            flush_preamble()
            token, heading_text, level = parsed
            parent_id = None
            lower_levels = [candidate for candidate in level_stack if candidate < level]
            if lower_levels:
                parent_id = level_stack[max(lower_levels)]
            for candidate in list(level_stack):
                if candidate >= level:
                    del level_stack[candidate]
            clause = Clause(
                clause_id=f"clause-{len(clauses) + 1:04d}",
                heading_token=token,
                heading_text=heading_text,
                body_text="",
                level=level,
                parent_clause_id=parent_id,
                page_start=unit.page_number,
                page_end=unit.page_number,
                source_spans=[_span(unit)],
                provenance=_provenance("clause.numbering-pattern", ExtractionConfidence.HIGH),
            )
            clauses.append(clause)
            current = clause
            level_stack[level] = clause.clause_id
            continue

        if current is None:
            preamble_units.append(unit)
            continue

        current.body_text = f"{current.body_text}\n{unit.text}".strip()
        if unit.page_number is not None:
            current.page_end = unit.page_number
        current.source_spans.append(_span(unit))

    flush_preamble()
    return clauses, unnumbered


def _extract_parties(units: Iterable[EvidenceUnit]) -> list[PartyMention]:
    results: list[PartyMention] = []
    for unit in units:
        for match in PARTY_PATTERN.finditer(unit.text):
            role = match.group("role")
            raw_name = match.group("name").strip().strip("；;，,")
            if not raw_name:
                raw_name = None
            state = ResolutionState.RESOLVED if raw_name else ResolutionState.UNRESOLVED
            confidence = ExtractionConfidence.HIGH if raw_name else ExtractionConfidence.UNRESOLVED
            results.append(
                PartyMention(
                    mention_id=f"party-{len(results) + 1:04d}",
                    role_label=role,
                    raw_name=raw_name,
                    normalized_name=raw_name,
                    resolution_state=state,
                    source_spans=[_span(unit, match.start(), match.end())],
                    provenance=_provenance("party.explicit-role-label", confidence),
                )
            )
    return results


def _extract_dates(units: Iterable[EvidenceUnit]) -> list[DateMention]:
    results: list[DateMention] = []
    for unit in units:
        for match in DATE_PATTERN.finditer(unit.text):
            raw = match.group(0)
            if match.group("cn"):
                year, month, day = int(match.group("cy")), int(match.group("cm")), int(match.group("cd"))
            else:
                year, month, day = int(match.group("sy")), int(match.group("sm")), int(match.group("sd"))
            iso: str | None = None
            state = ResolutionState.RESOLVED
            confidence = ExtractionConfidence.HIGH
            try:
                iso = date(year, month, day).isoformat()
            except ValueError:
                state = ResolutionState.UNRESOLVED
                confidence = ExtractionConfidence.UNRESOLVED
            prefix = unit.text[max(0, match.start() - 16):match.start()]
            label_match = DATE_LABEL_PATTERN.search(prefix)
            label = label_match.group(1) if label_match else None
            results.append(
                DateMention(
                    mention_id=f"date-{len(results) + 1:04d}",
                    raw_text=raw,
                    iso_date=iso,
                    field_label=label,
                    resolution_state=state,
                    source_spans=[_span(unit, match.start(), match.end())],
                    provenance=_provenance("date.explicit-format", confidence),
                )
            )
    return results


def _extract_money(units: Iterable[EvidenceUnit]) -> list[MoneyMention]:
    results: list[MoneyMention] = []
    multipliers = {
        "元": Decimal("1"),
        "百元": Decimal("100"),
        "千元": Decimal("1000"),
        "万元": Decimal("10000"),
        "亿元": Decimal("100000000"),
    }
    for unit in units:
        for match in MONEY_PATTERN.finditer(unit.text):
            raw = match.group(0)
            number_text = match.group("number") or match.group("symbol_number")
            unit_text = match.group("unit") or "元"
            numeric: str | None = None
            state = ResolutionState.RESOLVED
            confidence = ExtractionConfidence.HIGH
            try:
                number = Decimal(number_text.replace(",", ""))
                numeric = _compact_decimal(number * multipliers[unit_text])
            except (InvalidOperation, KeyError):
                state = ResolutionState.UNRESOLVED
                confidence = ExtractionConfidence.UNRESOLVED
            results.append(
                MoneyMention(
                    mention_id=f"money-{len(results) + 1:04d}",
                    raw_text=raw,
                    numeric_value=numeric,
                    currency="CNY",
                    unit=unit_text,
                    resolution_state=state,
                    source_spans=[_span(unit, match.start(), match.end())],
                    provenance=_provenance("money.explicit-arabic", confidence),
                )
            )
    return results


def _extract_percentages(units: Iterable[EvidenceUnit]) -> list[PercentageMention]:
    results: list[PercentageMention] = []
    for unit in units:
        matches: list[tuple[int, int, str, str | None, str]] = []
        for match in PERCENT_ARABIC_PATTERN.finditer(unit.text):
            matches.append((match.start(), match.end(), match.group(0), match.group("number"), "percent.arabic"))
        for match in PERCENT_CHINESE_PATTERN.finditer(unit.text):
            parsed = _chinese_integer(match.group("number"))
            matches.append((match.start(), match.end(), match.group(0), str(parsed) if parsed is not None else None, "percent.chinese"))
        for start, end, raw, numeric, rule in sorted(matches):
            state = ResolutionState.RESOLVED if numeric is not None else ResolutionState.UNRESOLVED
            confidence = ExtractionConfidence.HIGH if numeric is not None else ExtractionConfidence.UNRESOLVED
            results.append(
                PercentageMention(
                    mention_id=f"percentage-{len(results) + 1:04d}",
                    raw_text=raw,
                    numeric_value=numeric,
                    resolution_state=state,
                    source_spans=[_span(unit, start, end)],
                    provenance=_provenance(rule, confidence),
                )
            )
    return results


def _extract_identifiers(units: Iterable[EvidenceUnit]) -> list[IdentifierMention]:
    results: list[IdentifierMention] = []
    for unit in units:
        for match in IDENTIFIER_PATTERN.finditer(unit.text):
            results.append(
                IdentifierMention(
                    mention_id=f"identifier-{len(results) + 1:04d}",
                    label=match.group("label"),
                    raw_value=match.group("value"),
                    source_spans=[_span(unit, match.start(), match.end())],
                    provenance=_provenance("identifier.explicit-label", ExtractionConfidence.HIGH),
                )
            )
    return results


def _article_key(text: str) -> str | None:
    match = re.fullmatch(r"第([一二三四五六七八九十百零〇两\d]+)条", text.strip())
    if match:
        inner = match.group(1)
        value = int(inner) if inner.isdigit() else _chinese_integer(inner)
        return f"article:{value}" if value is not None else None
    match = re.fullmatch(r"(\d+(?:\.\d+)+)条?", text.strip())
    if match:
        return f"numeric:{match.group(1)}"
    return None


def _extract_references(units: Iterable[EvidenceUnit], clauses: list[Clause]) -> list[ReferenceMention]:
    results: list[ReferenceMention] = []
    clause_targets: dict[str, list[str]] = {}
    for clause in clauses:
        key = _article_key(clause.heading_token)
        if key:
            clause_targets.setdefault(key, []).append(clause.clause_id)

    for unit in units:
        for match in ATTACHMENT_PATTERN.finditer(unit.text):
            raw = match.group(0).strip()
            target = match.group(1).replace(" ", "")
            results.append(
                ReferenceMention(
                    reference_id=f"reference-{len(results) + 1:04d}",
                    raw_text=raw,
                    reference_type=ReferenceType.ATTACHMENT,
                    target_label=target,
                    resolution_state=ResolutionState.UNRESOLVED,
                    source_spans=[_span(unit, match.start(), match.end())],
                    provenance=_provenance("reference.attachment-label", ExtractionConfidence.MEDIUM),
                )
            )

        heading = parse_clause_heading(unit.text)
        heading_token = heading[0] if heading else None
        for match in ARTICLE_REFERENCE_PATTERN.finditer(unit.text):
            raw = match.group(0)
            if match.start() == 0 and heading_token and raw.rstrip("条") == heading_token.rstrip("条"):
                continue
            key = _article_key(raw)
            targets = clause_targets.get(key or "", [])
            if len(targets) == 1:
                state = ResolutionState.RESOLVED
                resolved_id = targets[0]
                confidence = ExtractionConfidence.HIGH
            elif len(targets) > 1:
                state = ResolutionState.AMBIGUOUS
                resolved_id = None
                confidence = ExtractionConfidence.UNRESOLVED
            else:
                state = ResolutionState.UNRESOLVED
                resolved_id = None
                confidence = ExtractionConfidence.UNRESOLVED
            results.append(
                ReferenceMention(
                    reference_id=f"reference-{len(results) + 1:04d}",
                    raw_text=raw,
                    reference_type=ReferenceType.CLAUSE,
                    target_label=raw,
                    resolved_target_id=resolved_id,
                    resolution_state=state,
                    source_spans=[_span(unit, match.start(), match.end())],
                    provenance=_provenance("reference.explicit-clause-label", confidence),
                )
            )
    return results


def _structured_candidates(units: list[EvidenceUnit]) -> list[StructuredBlockCandidate]:
    results: list[StructuredBlockCandidate] = []
    grouped: dict[str, list[EvidenceUnit]] = {}
    seen_group_order: list[str] = []

    for unit in units:
        if unit.block_kind == "TABLE_CELL" and unit.parent_group_id:
            if unit.parent_group_id not in grouped:
                grouped[unit.parent_group_id] = []
                seen_group_order.append(unit.parent_group_id)
            grouped[unit.parent_group_id].append(unit)
            continue

        if "\t" not in unit.text:
            continue
        cells = [cell.strip() for cell in unit.text.split("\t") if cell.strip()]
        if len(cells) < 2:
            continue
        results.append(
            StructuredBlockCandidate(
                block_id=f"structured-{len(results) + 1:04d}",
                kind=StructuredBlockKind.TABLE_CANDIDATE,
                raw_text=unit.text,
                source_spans=[_span(unit)],
                provenance=_provenance("structured.tab-delimited-candidate", ExtractionConfidence.LOW),
            )
        )

    for group_id in seen_group_order:
        group_units = grouped[group_id]
        if not group_units:
            continue
        results.append(
            StructuredBlockCandidate(
                block_id=f"structured-{len(results) + 1:04d}",
                kind=StructuredBlockKind.TABLE_CANDIDATE,
                raw_text="\n".join(unit.text for unit in group_units),
                source_spans=[_span(unit) for unit in group_units],
                provenance=_provenance("structured.docx-table-group", ExtractionConfidence.HIGH),
            )
        )
    return results


def _warnings(
    units: list[EvidenceUnit],
    titles: list[TitleCandidate],
    parties: list[PartyMention],
    dates: list[DateMention],
    references: list[ReferenceMention],
) -> list[ExtractionWarning]:
    warnings: list[ExtractionWarning] = []
    if not units:
        warnings.append(
            ExtractionWarning(
                warning_id="warning-0001",
                code="NO_TEXT_EVIDENCE",
                message="No usable text evidence was available for deterministic structuring.",
            )
        )
    if not titles:
        warnings.append(
            ExtractionWarning(
                warning_id=f"warning-{len(warnings) + 1:04d}",
                code="TITLE_UNRESOLVED",
                message="No conservative document title candidate was detected.",
            )
        )
    for party in parties:
        if party.resolution_state != ResolutionState.RESOLVED:
            span = party.source_spans[0]
            warnings.append(
                ExtractionWarning(
                    warning_id=f"warning-{len(warnings) + 1:04d}",
                    code="PARTY_NAME_UNRESOLVED",
                    message=f"Party role {party.role_label} has no clear explicit name.",
                    page_number=span.page_number,
                    evidence_ids=span.evidence_ids,
                )
            )
    for mention in dates:
        if mention.resolution_state != ResolutionState.RESOLVED:
            span = mention.source_spans[0]
            warnings.append(
                ExtractionWarning(
                    warning_id=f"warning-{len(warnings) + 1:04d}",
                    code="INVALID_DATE",
                    message=f"Explicit date could not be normalized safely: {mention.raw_text}",
                    page_number=span.page_number,
                    evidence_ids=span.evidence_ids,
                )
            )
    for reference in references:
        if reference.resolution_state != ResolutionState.RESOLVED:
            span = reference.source_spans[0]
            warnings.append(
                ExtractionWarning(
                    warning_id=f"warning-{len(warnings) + 1:04d}",
                    code="REFERENCE_UNRESOLVED",
                    message=f"Reference target is not uniquely resolved: {reference.raw_text}",
                    page_number=span.page_number,
                    evidence_ids=span.evidence_ids,
                )
            )
    for unit in units:
        if unit.source_method == SourceMethod.OCR and (unit.confidence is None or unit.confidence < 0.85):
            warnings.append(
                ExtractionWarning(
                    warning_id=f"warning-{len(warnings) + 1:04d}",
                    code="LOW_CONFIDENCE_OCR_SOURCE",
                    message="Canonical structure includes an OCR block that requires review.",
                    page_number=unit.page_number,
                    evidence_ids=unit.evidence_ids,
                )
            )
    return warnings


def build_canonical_contract(
    *,
    job_id: UUID,
    filename: str,
    fingerprint_bytes: bytes,
    units: list[EvidenceUnit],
    source_warnings: list[ExtractionWarning] | None = None,
    partial_source: bool = False,
) -> CanonicalContract:
    titles = _title_candidates(units)
    title_keys = {
        (span.page_number, title.text)
        for title in titles
        for span in title.source_spans
    }
    clauses, unnumbered = _build_clauses(units, title_keys)
    parties = _extract_parties(units)
    dates = _extract_dates(units)
    money = _extract_money(units)
    percentages = _extract_percentages(units)
    identifiers = _extract_identifiers(units)
    references = _extract_references(units, clauses)
    structured = _structured_candidates(units)
    warnings = list(source_warnings or [])
    generated = _warnings(units, titles, parties, dates, references)
    for warning in generated:
        warning.warning_id = f"warning-{len(warnings) + 1:04d}"
        warnings.append(warning)

    return CanonicalContract(
        job_id=job_id,
        filename=filename,
        status="partial" if partial_source else "complete",
        source_fingerprint=fingerprint_bytes.hex(),
        evidence_unit_count=len(units),
        title_candidates=titles,
        clauses=clauses,
        unnumbered_blocks=unnumbered,
        parties=parties,
        dates=dates,
        money_mentions=money,
        percentages=percentages,
        identifiers=identifiers,
        references=references,
        structured_blocks=structured,
        warnings=warnings,
    )
