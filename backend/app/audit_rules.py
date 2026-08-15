from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Sequence
from uuid import UUID

from .audit_rule_models import (
    DEFAULT_PROFILE_ID,
    RULE_ENGINE_VERSION,
    AuditProfile,
    AuditRuleReport,
    ObservedValue,
    RuleCounts,
    RuleEngineError,
    RuleResult,
    RuleSeverity,
    RuleState,
)
from .contract_models import (
    CanonicalContract,
    DateMention,
    IdentifierMention,
    MoneyMention,
    PartyMention,
    PercentageMention,
    ResolutionState,
    SourceSpan,
)
from .models import SourceMethod
from .storage import job_audit_rules_path, job_contract_path


class AuditRuleProcessingError(RuntimeError):
    pass


OCR_REVIEW_THRESHOLD = Decimal("0.85")

BASIC_BILATERAL_PROFILE = AuditProfile(
    profile_id=DEFAULT_PROFILE_ID,
    version="1.0.0",
    title="Basic bilateral contract completeness",
    required_title=True,
    min_resolved_parties=2,
    min_distinct_party_roles=2,
)

PROFILE_REGISTRY: dict[str, AuditProfile] = {
    BASIC_BILATERAL_PROFILE.profile_id: BASIC_BILATERAL_PROFILE,
}

PAYMENT_PHASE_PATTERN = re.compile(
    r"首付款|预付款|进度款|阶段款|验收款|尾款|质保金|保证金|定金|"
    r"第[一二三四五六七八九十百零〇两\d]+期(?:款)?|[一二三四五六七八九十]期款"
)
MONEY_FIELD_PATTERN = re.compile(r"合同总价|合同价款|合同金额")
UPPERCASE_RMB_PATTERN = re.compile(
    r"(?:人民币)?[零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元角分整正]{3,}"
)


@dataclass(frozen=True)
class TextContext:
    container_id: str
    text: str
    source_span: SourceSpan
    mention_start: int | None


RuleEvaluator = Callable[[CanonicalContract, AuditProfile], list[RuleResult]]


@dataclass(frozen=True)
class RegisteredRule:
    rule_id: str
    version: str
    family: str
    title: str
    evaluator: RuleEvaluator


def _unique_spans(spans: Iterable[SourceSpan]) -> list[SourceSpan]:
    output: list[SourceSpan] = []
    seen: set[tuple[object, ...]] = set()
    for span in spans:
        key = (
            span.page_number,
            tuple(span.evidence_ids),
            span.source_method.value,
            span.quote,
            span.char_start,
            span.char_end,
            tuple(span.bbox or []),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(span)
    return output


def _evidence_ids(spans: Iterable[SourceSpan]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for span in spans:
        for evidence_id in span.evidence_ids:
            if evidence_id not in seen:
                seen.add(evidence_id)
                output.append(evidence_id)
    return output


def _ocr_review_reasons(spans: Iterable[SourceSpan]) -> list[str]:
    reasons: list[str] = []
    for span in spans:
        if span.source_method != SourceMethod.OCR:
            continue
        if span.confidence is None:
            reasons.append(
                f"OCR source on page {span.page_number} has no recognition confidence and requires source verification."
            )
            continue
        if Decimal(str(span.confidence)) < OCR_REVIEW_THRESHOLD:
            reasons.append(
                f"OCR source on page {span.page_number} has confidence {span.confidence:.3f}, below the {OCR_REVIEW_THRESHOLD} review threshold."
            )
    return list(dict.fromkeys(reasons))


def _result(
    rule: RegisteredRule,
    *,
    instance: str,
    state: RuleState,
    reason_code: str,
    explanation: str,
    canonical_object_ids: Iterable[str] = (),
    source_spans: Iterable[SourceSpan] = (),
    observed_values: Iterable[ObservedValue] = (),
    severity: RuleSeverity | None = None,
    review_reasons: Iterable[str] = (),
) -> RuleResult:
    spans = _unique_spans(source_spans)
    final_state = state
    final_review_reasons = list(dict.fromkeys(review_reasons))
    ocr_reasons = _ocr_review_reasons(spans)
    if ocr_reasons and state in {RuleState.PASS, RuleState.FAIL}:
        final_state = RuleState.REVIEW
        final_review_reasons.extend(ocr_reasons)
    elif ocr_reasons:
        final_review_reasons.extend(ocr_reasons)

    final_severity = severity
    if final_state == RuleState.REVIEW and final_severity is None:
        final_severity = RuleSeverity.WARNING
    if final_state == RuleState.FAIL and final_severity is None:
        final_severity = RuleSeverity.ERROR

    return RuleResult(
        result_id=f"{rule.rule_id}:{instance}",
        rule_id=rule.rule_id,
        rule_version=rule.version,
        family=rule.family,
        title=rule.title,
        state=final_state,
        deterministic_state=state,
        severity=final_severity,
        reason_code=reason_code,
        explanation=explanation,
        canonical_object_ids=list(dict.fromkeys(canonical_object_ids)),
        source_spans=spans,
        evidence_ids=_evidence_ids(spans),
        observed_values=list(observed_values),
        review_reasons=list(dict.fromkeys(final_review_reasons)),
    )


def _span_contains(container: SourceSpan, mention: SourceSpan) -> bool:
    if container.page_number != mention.page_number:
        return False
    if not set(container.evidence_ids).intersection(mention.evidence_ids):
        return False
    if (
        container.char_start is not None
        and container.char_end is not None
        and mention.char_start is not None
        and mention.char_end is not None
    ):
        return container.char_start <= mention.char_start and mention.char_end <= container.char_end
    return True


def _text_context(contract: CanonicalContract, span: SourceSpan, raw_text: str) -> TextContext | None:
    containers: list[tuple[str, Sequence[SourceSpan]]] = [
        (clause.clause_id, clause.source_spans) for clause in contract.clauses
    ]
    containers.extend((block.block_id, block.source_spans) for block in contract.unnumbered_blocks)

    for container_id, source_spans in containers:
        for candidate in source_spans:
            if not _span_contains(candidate, span):
                continue
            relative_start: int | None = None
            if candidate.char_start is not None and span.char_start is not None:
                relative_start = max(0, span.char_start - candidate.char_start)
            else:
                located = candidate.quote.find(raw_text)
                relative_start = located if located >= 0 else None
            return TextContext(
                container_id=container_id,
                text=candidate.quote,
                source_span=candidate,
                mention_start=relative_start,
            )
    return None


def _safe_name(value: str) -> str:
    return "".join(value.replace("\u3000", " ").split())


def _required_profile_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    rule = RULE_BY_ID["REQ-BASIC-PROFILE"]
    resolved_parties = [
        item for item in contract.parties
        if item.resolution_state == ResolutionState.RESOLVED and item.raw_name
    ]
    distinct_roles = sorted({item.role_label for item in resolved_parties})
    title_ok = bool(contract.title_candidates) if profile.required_title else True
    parties_ok = len(resolved_parties) >= profile.min_resolved_parties
    roles_ok = len(distinct_roles) >= profile.min_distinct_party_roles

    objects: list[str] = []
    spans: list[SourceSpan] = []
    observed = [
        ObservedValue(label="profile", value=profile.profile_id),
        ObservedValue(label="title_candidates", value=str(len(contract.title_candidates))),
        ObservedValue(label="resolved_parties", value=str(len(resolved_parties))),
        ObservedValue(label="distinct_party_roles", value=str(len(distinct_roles))),
    ]
    for title in contract.title_candidates[:1]:
        objects.append(title.candidate_id)
        spans.extend(title.source_spans)
    for party in resolved_parties:
        objects.append(party.mention_id)
        spans.extend(party.source_spans)

    if title_ok and parties_ok and roles_ok:
        return [_result(
            rule,
            instance=profile.profile_id,
            state=RuleState.PASS,
            reason_code="PROFILE_REQUIREMENTS_PRESENT",
            explanation=(
                f"Profile {profile.profile_id} found a title and at least "
                f"{profile.min_resolved_parties} resolved party mentions across "
                f"{profile.min_distinct_party_roles} explicit roles."
            ),
            canonical_object_ids=objects,
            source_spans=spans,
            observed_values=observed,
        )]

    missing: list[str] = []
    if not title_ok:
        missing.append("contract title candidate")
    if not parties_ok:
        missing.append(f"{profile.min_resolved_parties} resolved party mentions")
    if not roles_ok:
        missing.append(f"{profile.min_distinct_party_roles} distinct party roles")
    return [_result(
        rule,
        instance=profile.profile_id,
        state=RuleState.FAIL,
        reason_code="PROFILE_REQUIREMENTS_MISSING",
        explanation=f"Profile {profile.profile_id} is missing: {', '.join(missing)}.",
        canonical_object_ids=objects,
        source_spans=spans,
        observed_values=observed,
        severity=RuleSeverity.WARNING,
    )]


def _party_consistency_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["PARTY-ROLE-CONSISTENCY"]
    groups: dict[str, list[PartyMention]] = {}
    for item in contract.parties:
        groups.setdefault(item.role_label, []).append(item)

    results: list[RuleResult] = []
    for role in sorted(groups):
        mentions = groups[role]
        resolved = [item for item in mentions if item.resolution_state == ResolutionState.RESOLVED and item.raw_name]
        unresolved = [item for item in mentions if item not in resolved]
        normalized = {_safe_name(item.raw_name or "") for item in resolved}
        spans = [span for item in mentions for span in item.source_spans]
        observed = [
            ObservedValue(label=role, value=item.raw_name or "<unresolved>", canonical_object_id=item.mention_id)
            for item in mentions
        ]

        if unresolved:
            results.append(_result(
                rule,
                instance=role,
                state=RuleState.REVIEW,
                reason_code="PARTY_NAME_UNRESOLVED",
                explanation=f"Role {role} contains an unresolved party-name mention and requires source review.",
                canonical_object_ids=[item.mention_id for item in mentions],
                source_spans=spans,
                observed_values=observed,
                review_reasons=["At least one explicit role label has no safely extracted party name."],
            ))
        elif len(resolved) < 2:
            results.append(_result(
                rule,
                instance=role,
                state=RuleState.NOT_APPLICABLE,
                reason_code="SINGLE_PARTY_MENTION",
                explanation=f"Role {role} has only one resolved mention, so no repeated-name consistency comparison is available.",
                canonical_object_ids=[item.mention_id for item in mentions],
                source_spans=spans,
                observed_values=observed,
            ))
        elif len(normalized) == 1:
            results.append(_result(
                rule,
                instance=role,
                state=RuleState.PASS,
                reason_code="PARTY_NAMES_MATCH",
                explanation=f"Repeated explicit mentions for role {role} match after whitespace-only normalization.",
                canonical_object_ids=[item.mention_id for item in mentions],
                source_spans=spans,
                observed_values=observed,
            ))
        else:
            results.append(_result(
                rule,
                instance=role,
                state=RuleState.FAIL,
                reason_code="PARTY_NAMES_CONFLICT",
                explanation=f"Role {role} has conflicting explicit party names; no fuzzy entity merge was applied.",
                canonical_object_ids=[item.mention_id for item in mentions],
                source_spans=spans,
                observed_values=observed,
            ))

    if not results:
        results.append(_result(
            rule,
            instance="none",
            state=RuleState.NOT_APPLICABLE,
            reason_code="NO_PARTY_MENTIONS",
            explanation="No explicit party-role mentions are available for consistency checking.",
        ))
    return results


def _identifier_consistency_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["IDENTIFIER-LABEL-CONSISTENCY"]
    groups: dict[str, list[IdentifierMention]] = {}
    for item in contract.identifiers:
        groups.setdefault(item.label, []).append(item)

    results: list[RuleResult] = []
    for label in sorted(groups):
        mentions = groups[label]
        spans = [span for item in mentions for span in item.source_spans]
        observed = [
            ObservedValue(label=label, value=item.raw_value, canonical_object_id=item.mention_id)
            for item in mentions
        ]
        if len(mentions) < 2:
            state = RuleState.NOT_APPLICABLE
            reason = "SINGLE_IDENTIFIER_MENTION"
            explanation = f"Label {label} has only one explicit value, so repeated-value consistency cannot be checked."
        elif len({item.raw_value.strip() for item in mentions}) == 1:
            state = RuleState.PASS
            reason = "IDENTIFIER_VALUES_MATCH"
            explanation = f"Repeated values for explicit label {label} are identical."
        else:
            state = RuleState.FAIL
            reason = "IDENTIFIER_VALUES_CONFLICT"
            explanation = f"Explicit label {label} has conflicting values. Different identifier labels were not compared."
        results.append(_result(
            rule,
            instance=label,
            state=state,
            reason_code=reason,
            explanation=explanation,
            canonical_object_ids=[item.mention_id for item in mentions],
            source_spans=spans,
            observed_values=observed,
        ))

    if not results:
        results.append(_result(
            rule,
            instance="none",
            state=RuleState.NOT_APPLICABLE,
            reason_code="NO_IDENTIFIERS",
            explanation="No explicit labelled contract/project/agreement identifiers are available.",
        ))
    return results


def _date_field_consistency_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["DATE-FIELD-CONSISTENCY"]
    groups: dict[str, list[DateMention]] = {}
    for item in contract.dates:
        if item.field_label:
            groups.setdefault(item.field_label, []).append(item)

    results: list[RuleResult] = []
    for label in sorted(groups):
        mentions = groups[label]
        spans = [span for item in mentions for span in item.source_spans]
        observed = [
            ObservedValue(label=label, value=item.iso_date or item.raw_text, canonical_object_id=item.mention_id)
            for item in mentions
        ]
        if any(item.resolution_state != ResolutionState.RESOLVED or not item.iso_date for item in mentions):
            state = RuleState.REVIEW
            reason = "DATE_FIELD_UNRESOLVED"
            explanation = f"Date field {label} contains an invalid or unresolved explicit date."
            review = ["An explicit date could not be normalized safely."]
        elif len(mentions) < 2:
            state = RuleState.NOT_APPLICABLE
            reason = "SINGLE_DATE_FIELD_MENTION"
            explanation = f"Date field {label} appears once; repeated-value consistency is not applicable."
            review = []
        elif len({item.iso_date for item in mentions}) == 1:
            state = RuleState.PASS
            reason = "DATE_FIELD_VALUES_MATCH"
            explanation = f"Repeated explicit values for date field {label} match."
            review = []
        else:
            state = RuleState.FAIL
            reason = "DATE_FIELD_VALUES_CONFLICT"
            explanation = f"Date field {label} has conflicting explicit values."
            review = []
        results.append(_result(
            rule,
            instance=label,
            state=state,
            reason_code=reason,
            explanation=explanation,
            canonical_object_ids=[item.mention_id for item in mentions],
            source_spans=spans,
            observed_values=observed,
            review_reasons=review,
        ))

    if not results:
        results.append(_result(
            rule,
            instance="none",
            state=RuleState.NOT_APPLICABLE,
            reason_code="NO_LABELLED_DATES",
            explanation="No explicitly labelled date fields are available for deterministic comparison.",
        ))
    return results


def _signing_effective_order_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["DATE-SIGNING-EFFECTIVE-ORDER"]
    signing = [item for item in contract.dates if item.field_label in {"签订日期", "签署日期"}]
    effective = [item for item in contract.dates if item.field_label == "生效日期"]
    relevant = signing + effective
    spans = [span for item in relevant for span in item.source_spans]
    observed = [
        ObservedValue(label=item.field_label or "date", value=item.iso_date or item.raw_text, canonical_object_id=item.mention_id)
        for item in relevant
    ]

    if not signing or not effective:
        return [_result(
            rule,
            instance="signing-effective",
            state=RuleState.NOT_APPLICABLE,
            reason_code="DATE_PAIR_MISSING",
            explanation="Both an explicit signing date and an explicit effective date are required for this chronology check.",
            canonical_object_ids=[item.mention_id for item in relevant],
            source_spans=spans,
            observed_values=observed,
        )]
    if len(signing) != 1 or len(effective) != 1:
        return [_result(
            rule,
            instance="signing-effective",
            state=RuleState.REVIEW,
            reason_code="DATE_PAIR_AMBIGUOUS",
            explanation="Multiple signing/effective date mentions exist; resolve the intended fields before chronology review.",
            canonical_object_ids=[item.mention_id for item in relevant],
            source_spans=spans,
            observed_values=observed,
            review_reasons=["The chronology pair is not unique."],
        )]

    sign_item, effective_item = signing[0], effective[0]
    if not sign_item.iso_date or not effective_item.iso_date:
        return [_result(
            rule,
            instance="signing-effective",
            state=RuleState.REVIEW,
            reason_code="DATE_PAIR_UNRESOLVED",
            explanation="The signing/effective date pair contains an unresolved date.",
            canonical_object_ids=[sign_item.mention_id, effective_item.mention_id],
            source_spans=spans,
            observed_values=observed,
            review_reasons=["One or both dates could not be normalized safely."],
        )]

    if effective_item.iso_date < sign_item.iso_date:
        return [_result(
            rule,
            instance="signing-effective",
            state=RuleState.REVIEW,
            reason_code="EFFECTIVE_DATE_PRECEDES_SIGNING",
            explanation=(
                "The explicit effective date precedes the explicit signing date. This may be intentional retroactive effect, "
                "so it is flagged for review rather than declared legally invalid."
            ),
            canonical_object_ids=[sign_item.mention_id, effective_item.mention_id],
            source_spans=spans,
            observed_values=observed,
            review_reasons=["Retroactive effectiveness requires human confirmation of intent."],
        )]

    return [_result(
        rule,
        instance="signing-effective",
        state=RuleState.PASS,
        reason_code="SIGNING_EFFECTIVE_ORDER_NON_RETROACTIVE",
        explanation="The explicit effective date is on or after the explicit signing date.",
        canonical_object_ids=[sign_item.mention_id, effective_item.mention_id],
        source_spans=spans,
        observed_values=observed,
    )]


def _payment_label_before(context: TextContext) -> str | None:
    if context.mention_start is None:
        return None
    prefix = context.text[max(0, context.mention_start - 28):context.mention_start]
    matches = list(PAYMENT_PHASE_PATTERN.finditer(prefix))
    return matches[-1].group(0) if matches else None


def _percentage_total_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["PAYMENT-PERCENTAGE-TOTAL"]
    line_groups: dict[tuple[int, tuple[str, ...], str], list[tuple[PercentageMention, str | None, TextContext]]] = {}

    for item in contract.percentages:
        if not item.source_spans:
            continue
        span = item.source_spans[0]
        context = _text_context(contract, span, item.raw_text)
        if context is None:
            continue
        key = (context.source_span.page_number, tuple(context.source_span.evidence_ids), context.source_span.quote)
        line_groups.setdefault(key, []).append((item, _payment_label_before(context), context))

    results: list[RuleResult] = []
    group_index = 0
    for entries in line_groups.values():
        if len(entries) < 2:
            continue
        labelled = [entry for entry in entries if entry[1]]
        if len(labelled) < 2:
            continue
        group_index += 1
        mentions = [entry[0] for entry in entries]
        spans = [span for item in mentions for span in item.source_spans]
        observed = [
            ObservedValue(
                label=label or "unlabelled-percentage",
                value=item.numeric_value or item.raw_text,
                canonical_object_id=item.mention_id,
            )
            for item, label, _context in entries
        ]

        if len(labelled) != len(entries):
            results.append(_result(
                rule,
                instance=f"group-{group_index:03d}",
                state=RuleState.REVIEW,
                reason_code="PAYMENT_PERCENTAGE_GROUP_AMBIGUOUS",
                explanation="A line contains multiple percentages and payment-phase labels, but not every percentage can be assigned conservatively.",
                canonical_object_ids=[item.mention_id for item in mentions],
                source_spans=spans,
                observed_values=observed,
                review_reasons=["The deterministic grouping rule cannot assign every percentage to an explicit payment phase."],
            ))
            continue

        values: list[Decimal] = []
        unresolved = False
        for item in mentions:
            if item.resolution_state != ResolutionState.RESOLVED or item.numeric_value is None:
                unresolved = True
                break
            try:
                values.append(Decimal(item.numeric_value))
            except InvalidOperation:
                unresolved = True
                break
        if unresolved:
            results.append(_result(
                rule,
                instance=f"group-{group_index:03d}",
                state=RuleState.REVIEW,
                reason_code="PAYMENT_PERCENTAGE_VALUE_UNRESOLVED",
                explanation="An explicitly grouped payment percentage could not be normalized safely.",
                canonical_object_ids=[item.mention_id for item in mentions],
                source_spans=spans,
                observed_values=observed,
                review_reasons=["At least one grouped percentage has no safe numeric value."],
            ))
            continue

        total = sum(values, Decimal("0"))
        observed.append(ObservedValue(label="calculated_total_percent", value=str(total)))
        if total == Decimal("100"):
            state = RuleState.PASS
            reason = "PAYMENT_PERCENTAGE_TOTAL_100"
            explanation = "Explicit payment-phase percentages in the same source line sum to 100%."
        else:
            state = RuleState.FAIL
            reason = "PAYMENT_PERCENTAGE_TOTAL_MISMATCH"
            explanation = f"Explicit payment-phase percentages in the same source line sum to {total}%, not 100%."
        results.append(_result(
            rule,
            instance=f"group-{group_index:03d}",
            state=state,
            reason_code=reason,
            explanation=explanation,
            canonical_object_ids=[item.mention_id for item in mentions],
            source_spans=spans,
            observed_values=observed,
        ))

    if not results:
        results.append(_result(
            rule,
            instance="none",
            state=RuleState.NOT_APPLICABLE,
            reason_code="NO_EXPLICIT_PAYMENT_PERCENTAGE_GROUP",
            explanation="No conservative same-line group of two or more explicitly labelled payment percentages was found; unrelated percentages were not summed.",
        ))
    return results


def _money_field_before(context: TextContext) -> str | None:
    if context.mention_start is None:
        return None
    prefix = context.text[max(0, context.mention_start - 20):context.mention_start]
    matches = list(MONEY_FIELD_PATTERN.finditer(prefix))
    return matches[-1].group(0) if matches else None


def _amount_consistency_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["AMOUNT-LABEL-CONSISTENCY"]
    groups: dict[str, list[MoneyMention]] = {}
    for item in contract.money_mentions:
        if not item.source_spans:
            continue
        context = _text_context(contract, item.source_spans[0], item.raw_text)
        if context is None:
            continue
        label = _money_field_before(context)
        if label:
            groups.setdefault(label, []).append(item)

    results: list[RuleResult] = []
    for label in sorted(groups):
        mentions = groups[label]
        spans = [span for item in mentions for span in item.source_spans]
        observed = [
            ObservedValue(label=label, value=item.numeric_value or item.raw_text, canonical_object_id=item.mention_id)
            for item in mentions
        ]
        if len(mentions) < 2:
            state = RuleState.NOT_APPLICABLE
            reason = "SINGLE_LABELLED_AMOUNT"
            explanation = f"Explicit field {label} appears once; repeated-value consistency is not applicable."
        elif any(item.resolution_state != ResolutionState.RESOLVED or item.numeric_value is None for item in mentions):
            state = RuleState.REVIEW
            reason = "LABELLED_AMOUNT_UNRESOLVED"
            explanation = f"Explicit field {label} contains an unresolved amount value."
        elif len({item.numeric_value for item in mentions}) == 1:
            state = RuleState.PASS
            reason = "LABELLED_AMOUNTS_MATCH"
            explanation = f"Repeated explicit values for {label} match numerically."
        else:
            state = RuleState.FAIL
            reason = "LABELLED_AMOUNTS_CONFLICT"
            explanation = f"Repeated explicit values for {label} conflict numerically."
        results.append(_result(
            rule,
            instance=label,
            state=state,
            reason_code=reason,
            explanation=explanation,
            canonical_object_ids=[item.mention_id for item in mentions],
            source_spans=spans,
            observed_values=observed,
        ))

    if not results:
        results.append(_result(
            rule,
            instance="none",
            state=RuleState.NOT_APPLICABLE,
            reason_code="NO_SUPPORTED_LABELLED_AMOUNTS",
            explanation="No supported explicit contract-total amount label was found for repeated-value comparison.",
        ))
    return results


def _uppercase_rmb_limitation_rule(contract: CanonicalContract, profile: AuditProfile) -> list[RuleResult]:
    del profile
    rule = RULE_BY_ID["UPPERCASE-RMB-REVIEW"]
    findings: list[tuple[str, SourceSpan, str]] = []
    for container in [*contract.clauses, *contract.unnumbered_blocks]:
        for span in container.source_spans:
            for match in UPPERCASE_RMB_PATTERN.finditer(span.quote):
                findings.append((container.clause_id if hasattr(container, "clause_id") else container.block_id, span, match.group(0)))

    if not findings:
        return [_result(
            rule,
            instance="none",
            state=RuleState.NOT_APPLICABLE,
            reason_code="NO_UPPERCASE_RMB_TEXT",
            explanation="No Chinese uppercase RMB candidate was detected in canonical source text.",
        )]

    return [_result(
        rule,
        instance="detected",
        state=RuleState.REVIEW,
        reason_code="UPPERCASE_RMB_PARSER_NOT_ENABLED",
        explanation="Chinese uppercase RMB text is present, but Stage 5 does not ship a weak uppercase-to-number comparison parser; verify it manually.",
        canonical_object_ids=[item[0] for item in findings],
        source_spans=[item[1] for item in findings],
        observed_values=[ObservedValue(label="uppercase_rmb", value=item[2], canonical_object_id=item[0]) for item in findings],
        review_reasons=["Uppercase/lowercase RMB consistency is intentionally deferred until a thoroughly tested parser is available."],
    )]


RULE_REGISTRY: tuple[RegisteredRule, ...] = (
    RegisteredRule("REQ-BASIC-PROFILE", "1.0.0", "required_fields", "Basic profile required fields", _required_profile_rule),
    RegisteredRule("PARTY-ROLE-CONSISTENCY", "1.0.0", "party_consistency", "Party name consistency by explicit role", _party_consistency_rule),
    RegisteredRule("IDENTIFIER-LABEL-CONSISTENCY", "1.0.0", "identifier_consistency", "Identifier consistency by explicit label", _identifier_consistency_rule),
    RegisteredRule("DATE-FIELD-CONSISTENCY", "1.0.0", "date_consistency", "Repeated explicit date-field consistency", _date_field_consistency_rule),
    RegisteredRule("DATE-SIGNING-EFFECTIVE-ORDER", "1.0.0", "date_order", "Signing/effective date chronology", _signing_effective_order_rule),
    RegisteredRule("PAYMENT-PERCENTAGE-TOTAL", "1.0.0", "percentage_arithmetic", "Explicit payment-percentage total", _percentage_total_rule),
    RegisteredRule("AMOUNT-LABEL-CONSISTENCY", "1.0.0", "amount_consistency", "Explicit labelled amount consistency", _amount_consistency_rule),
    RegisteredRule("UPPERCASE-RMB-REVIEW", "1.0.0", "amount_consistency", "Chinese uppercase RMB review limitation", _uppercase_rmb_limitation_rule),
)
RULE_BY_ID = {rule.rule_id: rule for rule in RULE_REGISTRY}


def _load_contract(job_id: UUID) -> tuple[CanonicalContract, bytes]:
    path = job_contract_path(job_id)
    if not path.exists():
        raise AuditRuleProcessingError(
            f"Canonical contract for job {job_id} does not exist. Generate Stage 4 structure first."
        )
    try:
        content = path.read_bytes()
        contract = CanonicalContract.model_validate_json(content)
    except Exception as exc:
        raise AuditRuleProcessingError("Persisted contract.json is malformed and cannot be audited safely.") from exc
    if contract.job_id != job_id:
        raise AuditRuleProcessingError("Persisted contract.json belongs to a different job ID.")
    return contract, content


def _counts(results: Sequence[RuleResult]) -> RuleCounts:
    return RuleCounts(
        total=len(results),
        passed=sum(item.state == RuleState.PASS for item in results),
        failed=sum(item.state == RuleState.FAIL for item in results),
        review=sum(item.state == RuleState.REVIEW for item in results),
        not_applicable=sum(item.state == RuleState.NOT_APPLICABLE for item in results),
    )


def evaluate_contract(
    contract: CanonicalContract,
    *,
    profile: AuditProfile = BASIC_BILATERAL_PROFILE,
    registry: Sequence[RegisteredRule] = RULE_REGISTRY,
    contract_content_fingerprint: str | None = None,
) -> AuditRuleReport:
    results: list[RuleResult] = []
    errors: list[RuleEngineError] = []

    for rule in registry:
        try:
            emitted = rule.evaluator(contract, profile)
            results.extend(emitted)
        except Exception as exc:
            errors.append(RuleEngineError(
                rule_id=rule.rule_id,
                error_type=type(exc).__name__,
                message=str(exc) or "Rule raised an exception.",
            ))
            results.append(_result(
                rule,
                instance="engine-error",
                state=RuleState.REVIEW,
                reason_code="RULE_EXECUTION_ERROR",
                explanation=f"Rule {rule.rule_id} could not be evaluated; other rules continued running.",
                review_reasons=[f"{type(exc).__name__}: {str(exc) or 'no error message'}"],
            ))

    fingerprint = contract_content_fingerprint or hashlib.sha256(
        json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return AuditRuleReport(
        job_id=contract.job_id,
        status="complete_with_errors" if errors else "complete",
        contract_schema_version=contract.schema_version,
        contract_source_fingerprint=contract.source_fingerprint,
        contract_content_fingerprint=fingerprint,
        profile=profile,
        counts=_counts(results),
        results=results,
        engine_errors=errors,
    )


def run_audit_rules(job_id: UUID, profile_id: str = DEFAULT_PROFILE_ID) -> AuditRuleReport:
    profile = PROFILE_REGISTRY.get(profile_id)
    if profile is None:
        raise AuditRuleProcessingError(f"Unknown audit profile: {profile_id}.")
    contract, content = _load_contract(job_id)
    report = evaluate_contract(
        contract,
        profile=profile,
        contract_content_fingerprint=hashlib.sha256(content).hexdigest(),
    )
    job_audit_rules_path(job_id).write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def load_audit_rule_report(job_id: UUID) -> AuditRuleReport:
    path = job_audit_rules_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Deterministic audit report for job {job_id} does not exist.")
    try:
        return AuditRuleReport.model_validate_json(path.read_bytes())
    except Exception as exc:
        raise AuditRuleProcessingError("Persisted audit-rules.json is malformed and cannot be loaded safely.") from exc
