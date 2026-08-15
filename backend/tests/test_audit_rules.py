from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.audit_rule_models import RuleState
from app.audit_rules import (
    BASIC_BILATERAL_PROFILE,
    RULE_BY_ID,
    AuditRuleProcessingError,
    RegisteredRule,
    evaluate_contract,
    load_audit_rule_report,
    run_audit_rules,
)
from app.contract_models import (
    CanonicalContract,
    DateMention,
    ExtractionConfidence,
    ExtractionProvenance,
    IdentifierMention,
    MoneyMention,
    PartyMention,
    PercentageMention,
    ResolutionState,
    SourceSpan,
    TitleCandidate,
    UnnumberedBlock,
)
from app.models import SourceMethod
from app.storage import job_contract_path


def _prov(rule: str = "fixture", confidence: ExtractionConfidence = ExtractionConfidence.HIGH) -> ExtractionProvenance:
    return ExtractionProvenance(extractor_id=rule, confidence=confidence)


def _span(
    quote: str,
    *,
    evidence_id: str,
    page: int = 1,
    start: int = 0,
    source_method: SourceMethod = SourceMethod.NATIVE_PDF_TEXT,
    confidence: float | None = None,
) -> SourceSpan:
    return SourceSpan(
        page_number=page,
        evidence_ids=[evidence_id],
        source_method=source_method,
        quote=quote,
        char_start=start if source_method == SourceMethod.NATIVE_PDF_TEXT else None,
        char_end=(start + len(quote)) if source_method == SourceMethod.NATIVE_PDF_TEXT else None,
        bbox=[0, 0, 100, 20] if source_method == SourceMethod.OCR else None,
        confidence=confidence,
    )


def _base_contract() -> CanonicalContract:
    job_id = uuid4()
    title_span = _span("测试采购合同", evidence_id="e-title", start=0)
    party_a_span = _span("甲方：甲测试有限公司", evidence_id="e-a", start=20)
    party_b_span = _span("乙方：乙测试有限公司", evidence_id="e-b", start=50)
    return CanonicalContract(
        job_id=job_id,
        filename="fixture.pdf",
        source_fingerprint="fixture-source",
        evidence_unit_count=3,
        title_candidates=[
            TitleCandidate(
                candidate_id="title-001",
                text="测试采购合同",
                source_spans=[title_span],
                provenance=_prov(),
            )
        ],
        parties=[
            PartyMention(
                mention_id="party-0001",
                role_label="甲方",
                raw_name="甲测试有限公司",
                normalized_name="甲测试有限公司",
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[party_a_span],
                provenance=_prov(),
            ),
            PartyMention(
                mention_id="party-0002",
                role_label="乙方",
                raw_name="乙测试有限公司",
                normalized_name="乙测试有限公司",
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[party_b_span],
                provenance=_prov(),
            ),
        ],
    )


def _add_percentage_line(contract: CanonicalContract, text: str, values: list[tuple[str, str]]) -> None:
    evidence = "e-percent-line"
    line_span = _span(text, evidence_id=evidence, start=100)
    contract.unnumbered_blocks.append(
        UnnumberedBlock(
            block_id="unnumbered-percent",
            text=text,
            page_start=1,
            page_end=1,
            source_spans=[line_span],
            provenance=_prov(),
        )
    )
    for index, (raw, numeric) in enumerate(values, start=1):
        relative = text.index(raw, 0 if index == 1 else text.index(values[index - 2][0]) + len(values[index - 2][0]))
        contract.percentages.append(
            PercentageMention(
                mention_id=f"percentage-{index:04d}",
                raw_text=raw,
                numeric_value=numeric,
                resolution_state=ResolutionState.RESOLVED,
                source_spans=[_span(raw, evidence_id=evidence, start=100 + relative)],
                provenance=_prov(),
            )
        )


def _result(report, rule_id: str, instance_suffix: str | None = None):
    matches = [item for item in report.results if item.rule_id == rule_id]
    if instance_suffix is not None:
        matches = [item for item in matches if item.result_id.endswith(instance_suffix)]
    assert matches, f"missing result for {rule_id}"
    return matches[0]


def test_explicit_payment_percentages_sum_to_100_passes() -> None:
    contract = _base_contract()
    _add_percentage_line(contract, "首付款30%，进度款50%，尾款20%。", [("30%", "30"), ("50%", "50"), ("20%", "20")])

    report = evaluate_contract(contract)
    result = _result(report, "PAYMENT-PERCENTAGE-TOTAL")

    assert result.state == RuleState.PASS
    assert result.deterministic_state == RuleState.PASS
    assert {item.value for item in result.observed_values if item.label == "calculated_total_percent"} == {"100"}
    assert result.evidence_ids == ["e-percent-line"]


def test_explicit_payment_percentages_sum_above_100_fails() -> None:
    contract = _base_contract()
    _add_percentage_line(contract, "首付款30%，进度款50%，尾款30%。", [("30%", "30"), ("50%", "50"), ("30%", "30")])

    result = _result(evaluate_contract(contract), "PAYMENT-PERCENTAGE-TOTAL")

    assert result.state == RuleState.FAIL
    assert result.reason_code == "PAYMENT_PERCENTAGE_TOTAL_MISMATCH"
    assert any(item.value == "110" for item in result.observed_values)


def test_unrelated_percentages_are_not_summed() -> None:
    contract = _base_contract()
    _add_percentage_line(contract, "税率13%，违约金10%。", [("13%", "13"), ("10%", "10")])

    result = _result(evaluate_contract(contract), "PAYMENT-PERCENTAGE-TOTAL")

    assert result.state == RuleState.NOT_APPLICABLE
    assert result.reason_code == "NO_EXPLICIT_PAYMENT_PERCENTAGE_GROUP"


def test_same_role_repeated_name_passes_and_conflict_fails() -> None:
    contract = _base_contract()
    repeat_span = _span("甲方：甲测试有限公司", evidence_id="e-a2", start=80)
    contract.parties.append(
        PartyMention(
            mention_id="party-0003",
            role_label="甲方",
            raw_name="甲测试有限公司",
            normalized_name="甲测试有限公司",
            resolution_state=ResolutionState.RESOLVED,
            source_spans=[repeat_span],
            provenance=_prov(),
        )
    )
    report = evaluate_contract(contract)
    assert _result(report, "PARTY-ROLE-CONSISTENCY", "甲方").state == RuleState.PASS

    contract.parties[-1].raw_name = "甲建筑有限公司"
    contract.parties[-1].normalized_name = "甲建筑有限公司"
    report = evaluate_contract(contract)
    conflict = _result(report, "PARTY-ROLE-CONSISTENCY", "甲方")
    assert conflict.state == RuleState.FAIL
    assert conflict.reason_code == "PARTY_NAMES_CONFLICT"


def test_identifier_conflict_is_grouped_only_by_same_label() -> None:
    contract = _base_contract()
    contract.identifiers = [
        IdentifierMention(mention_id="identifier-1", label="合同编号", raw_value="HT-001", source_spans=[_span("合同编号：HT-001", evidence_id="id1", start=100)], provenance=_prov()),
        IdentifierMention(mention_id="identifier-2", label="合同编号", raw_value="HT-002", source_spans=[_span("合同编号：HT-002", evidence_id="id2", start=130)], provenance=_prov()),
        IdentifierMention(mention_id="identifier-3", label="项目编号", raw_value="HT-001", source_spans=[_span("项目编号：HT-001", evidence_id="id3", start=160)], provenance=_prov()),
    ]

    report = evaluate_contract(contract)
    contract_id = _result(report, "IDENTIFIER-LABEL-CONSISTENCY", "合同编号")
    project_id = _result(report, "IDENTIFIER-LABEL-CONSISTENCY", "项目编号")

    assert contract_id.state == RuleState.FAIL
    assert project_id.state == RuleState.NOT_APPLICABLE


def test_signing_effective_date_order_passes_or_routes_retroactive_case_to_review() -> None:
    contract = _base_contract()
    contract.dates = [
        DateMention(mention_id="date-1", raw_text="2026年8月15日", iso_date="2026-08-15", field_label="签订日期", resolution_state=ResolutionState.RESOLVED, source_spans=[_span("2026年8月15日", evidence_id="d1", start=100)], provenance=_prov()),
        DateMention(mention_id="date-2", raw_text="2026年8月16日", iso_date="2026-08-16", field_label="生效日期", resolution_state=ResolutionState.RESOLVED, source_spans=[_span("2026年8月16日", evidence_id="d2", start=130)], provenance=_prov()),
    ]
    assert _result(evaluate_contract(contract), "DATE-SIGNING-EFFECTIVE-ORDER").state == RuleState.PASS

    contract.dates[1].iso_date = "2026-08-10"
    retro = _result(evaluate_contract(contract), "DATE-SIGNING-EFFECTIVE-ORDER")
    assert retro.state == RuleState.REVIEW
    assert retro.reason_code == "EFFECTIVE_DATE_PRECEDES_SIGNING"


def test_unresolved_labelled_date_routes_to_review() -> None:
    contract = _base_contract()
    contract.dates = [
        DateMention(mention_id="date-1", raw_text="2026年2月30日", iso_date=None, field_label="签订日期", resolution_state=ResolutionState.UNRESOLVED, source_spans=[_span("2026年2月30日", evidence_id="d1", start=100)], provenance=_prov(confidence=ExtractionConfidence.UNRESOLVED)),
    ]

    result = _result(evaluate_contract(contract), "DATE-FIELD-CONSISTENCY", "签订日期")
    assert result.state == RuleState.REVIEW
    assert result.reason_code == "DATE_FIELD_UNRESOLVED"


def test_required_profile_passes_and_fails_without_universal_claim() -> None:
    contract = _base_contract()
    passing = _result(evaluate_contract(contract), "REQ-BASIC-PROFILE")
    assert passing.state == RuleState.PASS
    assert BASIC_BILATERAL_PROFILE.profile_id in passing.result_id

    contract.parties = contract.parties[:1]
    failing = _result(evaluate_contract(contract), "REQ-BASIC-PROFILE")
    assert failing.state == RuleState.FAIL
    assert failing.reason_code == "PROFILE_REQUIREMENTS_MISSING"


def test_low_confidence_ocr_conflict_is_downgraded_to_review() -> None:
    contract = _base_contract()
    contract.parties[0].source_spans = [
        _span(
            "甲方：甲测试有限公司",
            evidence_id="ocr-low-1",
            source_method=SourceMethod.OCR,
            confidence=0.61,
        )
    ]
    contract.parties.append(
        PartyMention(
            mention_id="party-0003",
            role_label="甲方",
            raw_name="甲建筑有限公司",
            normalized_name="甲建筑有限公司",
            resolution_state=ResolutionState.RESOLVED,
            source_spans=[_span("甲方：甲建筑有限公司", evidence_id="native-2", start=100)],
            provenance=_prov(),
        )
    )

    result = _result(evaluate_contract(contract), "PARTY-ROLE-CONSISTENCY", "甲方")

    assert result.deterministic_state == RuleState.FAIL
    assert result.state == RuleState.REVIEW
    assert "ocr-low-1" in result.evidence_ids
    assert result.review_reasons


def test_repeated_labelled_contract_amounts_conflict() -> None:
    contract = _base_contract()
    line1 = "合同总价：人民币100000元"
    line2 = "合同总价：人民币120000元"
    contract.unnumbered_blocks = [
        UnnumberedBlock(block_id="amount-1", text=line1, page_start=1, page_end=1, source_spans=[_span(line1, evidence_id="m1", start=100)], provenance=_prov()),
        UnnumberedBlock(block_id="amount-2", text=line2, page_start=1, page_end=1, source_spans=[_span(line2, evidence_id="m2", start=140)], provenance=_prov()),
    ]
    start1 = 100 + line1.index("人民币100000元")
    start2 = 140 + line2.index("人民币120000元")
    contract.money_mentions = [
        MoneyMention(mention_id="money-1", raw_text="人民币100000元", numeric_value="100000", currency="CNY", unit="元", resolution_state=ResolutionState.RESOLVED, source_spans=[_span("人民币100000元", evidence_id="m1", start=start1)], provenance=_prov()),
        MoneyMention(mention_id="money-2", raw_text="人民币120000元", numeric_value="120000", currency="CNY", unit="元", resolution_state=ResolutionState.RESOLVED, source_spans=[_span("人民币120000元", evidence_id="m2", start=start2)], provenance=_prov()),
    ]

    result = _result(evaluate_contract(contract), "AMOUNT-LABEL-CONSISTENCY", "合同总价")
    assert result.state == RuleState.FAIL
    assert result.reason_code == "LABELLED_AMOUNTS_CONFLICT"


def test_uppercase_rmb_is_explicit_review_limitation() -> None:
    contract = _base_contract()
    text = "合同价款：人民币壹拾万元整"
    contract.unnumbered_blocks = [
        UnnumberedBlock(block_id="upper-1", text=text, page_start=1, page_end=1, source_spans=[_span(text, evidence_id="upper-e", start=100)], provenance=_prov())
    ]
    result = _result(evaluate_contract(contract), "UPPERCASE-RMB-REVIEW")
    assert result.state == RuleState.REVIEW
    assert result.reason_code == "UPPERCASE_RMB_PARSER_NOT_ENABLED"


def test_rule_evidence_ids_come_from_canonical_spans() -> None:
    contract = _base_contract()
    report = evaluate_contract(contract)
    canonical_ids = {
        evidence_id
        for collection in [contract.title_candidates, contract.parties, contract.dates, contract.money_mentions, contract.percentages, contract.identifiers, contract.references, contract.clauses, contract.unnumbered_blocks]
        for item in collection
        for span in item.source_spans
        for evidence_id in span.evidence_ids
    }
    for result in report.results:
        assert set(result.evidence_ids).issubset(canonical_ids)


def test_broken_rule_does_not_suppress_other_rules() -> None:
    contract = _base_contract()

    def broken(_contract, _profile):
        raise RuntimeError("fixture rule broke")

    broken_rule = RegisteredRule("BROKEN-FIXTURE", "1.0.0", "test", "Broken fixture rule", broken)
    report = evaluate_contract(
        contract,
        registry=(RULE_BY_ID["REQ-BASIC-PROFILE"], broken_rule, RULE_BY_ID["IDENTIFIER-LABEL-CONSISTENCY"]),
    )

    assert len(report.engine_errors) == 1
    assert report.engine_errors[0].rule_id == "BROKEN-FIXTURE"
    assert any(item.rule_id == "REQ-BASIC-PROFILE" for item in report.results)
    error_result = next(item for item in report.results if item.rule_id == "BROKEN-FIXTURE")
    assert error_result.state == RuleState.REVIEW


def test_persisted_report_is_deterministic_and_loadable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    contract = _base_contract()
    path = job_contract_path(contract.job_id)
    path.write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    first = run_audit_rules(contract.job_id)
    first_bytes = path.parent.joinpath("audit-rules.json").read_bytes()
    second = run_audit_rules(contract.job_id)
    second_bytes = path.parent.joinpath("audit-rules.json").read_bytes()

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first_bytes == second_bytes
    assert load_audit_rule_report(contract.job_id).model_dump(mode="json") == first.model_dump(mode="json")


def test_missing_or_malformed_contract_fails_explicitly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    missing_id = uuid4()
    with pytest.raises(AuditRuleProcessingError, match="Generate Stage 4 structure first"):
        run_audit_rules(missing_id)

    bad_id = uuid4()
    path = job_contract_path(bad_id)
    path.write_text("{bad-json", encoding="utf-8")
    with pytest.raises(AuditRuleProcessingError, match="malformed"):
        run_audit_rules(bad_id)
