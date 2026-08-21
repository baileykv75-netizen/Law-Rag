from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.audit_planner import run_audit_planner
from app.audit_planner_provider import FakeAuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.issue_legal_context import build_issue_legal_context
from app.issue_primary_audit import run_issue_primary_audit
from app.issue_secondary_review import run_issue_secondary_review
from app.issue_review_report import build_issue_review_report
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.models import SourceMethod
from app.pipeline_control import set_provider_mode
from app.pipeline_control_models import ProviderExecutionMode
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStageRecord, PipelineStageState, PipelineStatus
from app.storage import (
    job_audit_plan_path,
    job_contract_path,
    job_issue_legal_context_path,
    job_issue_primary_audit_path,
    job_issue_review_report_path,
    job_issue_secondary_review_path,
    job_pipeline_path,
    legal_db_path,
    legal_retrieval_index_path,
)
from app.uat_capture import (
    UATCaptureError,
    _validate_issue_counts,
    capture_issue_v1_uat,
    load_issue_v1_uat_observation,
)
from app.uat_capture_models import UATCaptureMode, UATChainState, UATProviderStage


AS_OF = date(2026, 8, 18)


def _contract() -> CanonicalContract:
    job_id = uuid4()
    provenance = ExtractionProvenance(
        extractor_id="stage16d-uat-fixture",
        confidence=ExtractionConfidence.HIGH,
    )
    text = (
        "本条为甲方预先拟定条款。乙方逾期履行的，应按合同总金额的50%支付违约金；"
        "甲方对该责任限制条款负有提示说明义务。"
    )
    quote = f"第八条 违约责任\n{text}"
    span = SourceSpan(
        page_number=2,
        evidence_ids=["evidence-stage16d-clause-8"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )
    return CanonicalContract(
        job_id=job_id,
        filename="stage16d-uat-fixture.pdf",
        source_fingerprint="stage16d-uat-source",
        evidence_unit_count=1,
        clauses=[
            Clause(
                clause_id="clause-008",
                heading_token="第八条",
                heading_text="违约责任",
                body_text=text,
                level=1,
                page_start=2,
                page_end=2,
                source_spans=[span],
                provenance=provenance,
            )
        ],
    )


def _forbid_network(monkeypatch) -> None:
    class ForbiddenHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Stage 16.4 UAT capture regression attempted outbound HTTP.")

    monkeypatch.setattr(httpx, "Client", ForbiddenHttpClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenHttpClient)


def _write_pipeline(tmp_path: Path, job_id) -> None:
    now = datetime.now(timezone.utc)
    stages = [
        PipelineStage.INGEST,
        PipelineStage.OCR,
        PipelineStage.STRUCTURE,
        PipelineStage.RULES,
        PipelineStage.AUDIT_PLAN,
        PipelineStage.ISSUE_LEGAL_CONTEXT,
        PipelineStage.ISSUE_PRIMARY_AUDIT,
        PipelineStage.ISSUE_SECONDARY_REVIEW,
        PipelineStage.ISSUE_REVIEW_REPORT,
    ]
    report = PipelineReport(
        job_id=job_id,
        status=PipelineStatus.COMPLETE,
        current_stage=PipelineStage.COMPLETE,
        progress_percent=100,
        as_of=AS_OF,
        use_semantic=False,
        started_at=now,
        updated_at=now,
        completed_at=now,
        stages=[
            PipelineStageRecord(
                stage=stage,
                state=PipelineStageState.COMPLETE,
                label=stage.value,
                progress_percent=min(100, 10 + index * 11),
            )
            for index, stage in enumerate(stages)
        ],
    )
    job_pipeline_path(job_id).write_text(report.model_dump_json(indent=2), encoding="utf-8")


def _prepare_complete_chain(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_ISSUE_SECONDARY", "1")
    _forbid_network(monkeypatch)

    contract = _contract()
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(contract.job_id)

    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(
        repo_root / "legal_data" / "seed" / "manifest.json",
        legal_db_path(),
        rebuild=True,
    )
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)

    plan = run_audit_planner(contract.job_id, provider=FakeAuditPlannerProvider())
    legal = build_issue_legal_context(contract.job_id, as_of=AS_OF, use_semantic=False)
    primary = run_issue_primary_audit(contract.job_id, provider_name="fake")
    secondary = run_issue_secondary_review(contract.job_id, provider_name="fake")
    report = build_issue_review_report(contract.job_id)
    _write_pipeline(tmp_path, contract.job_id)
    return contract, plan, legal, primary, secondary, report


def test_uat_capture_test_double_complete_chain_is_private_and_sanitized(tmp_path: Path, monkeypatch) -> None:
    contract, plan, _, _, _, _ = _prepare_complete_chain(tmp_path, monkeypatch)
    repo_root = Path(__file__).resolve().parents[2]
    output = tmp_path / "private-uat" / "observation.json"

    observation, sanitized = capture_issue_v1_uat(
        repo_root,
        contract.job_id,
        output,
        capture_mode=UATCaptureMode.TEST_DOUBLE,
    )

    assert observation.chain_state == UATChainState.COMPLETE
    assert sanitized.chain_state == UATChainState.COMPLETE
    assert observation.audit_plan_issue_count == len(plan.issues)
    assert sanitized.audit_plan_issue_count == len(plan.issues)
    assert output.exists()
    assert load_issue_v1_uat_observation(output).observation_fingerprint == observation.observation_fingerprint

    sanitized_text = sanitized.model_dump_json()
    assert str(contract.job_id) not in sanitized_text
    for issue in plan.issues:
        assert issue.issue_id not in sanitized_text
    for call in observation.provider_calls:
        assert call.raw_response_hash not in sanitized_text
        if call.request_id:
            assert call.request_id not in sanitized_text

    assert {item.stage for item in sanitized.provider_summaries} == {
        UATProviderStage.PLANNER,
        UATProviderStage.PRIMARY,
        UATProviderStage.SECONDARY,
    }
    assert any("does not establish legal correctness" in warning for warning in sanitized.warnings)


def test_uat_capture_rejects_tracked_repository_output_before_reading_job() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with pytest.raises(UATCaptureError, match="tracked repository paths are forbidden"):
        capture_issue_v1_uat(
            repo_root,
            uuid4(),
            repo_root / "docs" / "forbidden-uat-observation.json",
            capture_mode=UATCaptureMode.TEST_DOUBLE,
        )


def test_uat_capture_is_append_only(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output = tmp_path / "existing-observation.json"
    output.write_text("already captured", encoding="utf-8")
    with pytest.raises(UATCaptureError, match="append-only evidence"):
        capture_issue_v1_uat(
            repo_root,
            uuid4(),
            output,
            capture_mode=UATCaptureMode.TEST_DOUBLE,
        )


def test_real_provider_capture_requires_explicit_confirmation(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with pytest.raises(UATCaptureError, match="explicit confirm_real_provider_uat"):
        capture_issue_v1_uat(
            repo_root,
            uuid4(),
            tmp_path / "real-provider.json",
            capture_mode=UATCaptureMode.REAL_PROVIDER,
        )


def test_real_provider_capture_rejects_fake_provider_identity(tmp_path: Path, monkeypatch) -> None:
    contract, *_ = _prepare_complete_chain(tmp_path, monkeypatch)
    repo_root = Path(__file__).resolve().parents[2]
    with pytest.raises(UATCaptureError, match="expected deepseek|Fake/test provider"):
        capture_issue_v1_uat(
            repo_root,
            contract.job_id,
            tmp_path / "fake-as-real.json",
            capture_mode=UATCaptureMode.REAL_PROVIDER,
            confirm_real_provider_uat=True,
        )


def test_uat_capture_rejects_stale_embedded_fingerprint(tmp_path: Path, monkeypatch) -> None:
    contract, *_ = _prepare_complete_chain(tmp_path, monkeypatch)
    legal_path = job_issue_legal_context_path(contract.job_id)
    payload = json.loads(legal_path.read_text(encoding="utf-8"))
    payload.setdefault("warnings", []).append("tampered after persistence")
    legal_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(UATCaptureError, match="stale or invalid"):
        capture_issue_v1_uat(
            Path(__file__).resolve().parents[2],
            contract.job_id,
            tmp_path / "stale.json",
            capture_mode=UATCaptureMode.TEST_DOUBLE,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("as_of", "2026-08-19", "disagree on as_of"),
        ("use_semantic", True, "semantic retrieval mode"),
    ],
)
def test_uat_capture_rejects_pipeline_run_parameter_mismatch(
    tmp_path: Path,
    monkeypatch,
    field: str,
    value,
    error: str,
) -> None:
    contract, *_ = _prepare_complete_chain(tmp_path, monkeypatch)
    pipeline_path = job_pipeline_path(contract.job_id)
    payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
    payload[field] = value
    pipeline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(UATCaptureError, match=error):
        capture_issue_v1_uat(
            Path(__file__).resolve().parents[2],
            contract.job_id,
            tmp_path / f"mismatch-{field}.json",
            capture_mode=UATCaptureMode.TEST_DOUBLE,
        )


def test_uat_capture_rejects_legacy_audit_stage_in_pipeline(tmp_path: Path, monkeypatch) -> None:
    contract, *_ = _prepare_complete_chain(tmp_path, monkeypatch)
    pipeline_path = job_pipeline_path(contract.job_id)
    payload = json.loads(pipeline_path.read_text(encoding="utf-8"))
    payload["stages"].append(
        {
            "stage": "PRIMARY_AUDIT",
            "state": "COMPLETE",
            "label": "legacy stage",
            "progress_percent": 100,
            "detail": "",
            "reused_existing_artifact": False,
            "started_at": None,
            "finished_at": None,
        }
    )
    pipeline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(UATCaptureError, match="legacy RC2 audit stages"):
        capture_issue_v1_uat(
            Path(__file__).resolve().parents[2],
            contract.job_id,
            tmp_path / "legacy.json",
            capture_mode=UATCaptureMode.TEST_DOUBLE,
        )


def test_uat_issue_coverage_guard_rejects_missing_legal_issue(tmp_path: Path, monkeypatch) -> None:
    _, plan, legal, primary, secondary, report = _prepare_complete_chain(tmp_path, monkeypatch)
    assert legal.issues
    broken_legal = legal.model_copy(deep=True)
    broken_legal.issues = broken_legal.issues[:-1]

    with pytest.raises(UATCaptureError, match="Issue Legal Context count|cover exactly"):
        _validate_issue_counts(plan, broken_legal, primary, secondary, report)


def test_uat_observation_fingerprint_detects_post_capture_tampering(tmp_path: Path, monkeypatch) -> None:
    contract, *_ = _prepare_complete_chain(tmp_path, monkeypatch)
    output = tmp_path / "tamper-observation.json"
    capture_issue_v1_uat(
        Path(__file__).resolve().parents[2],
        contract.job_id,
        output,
        capture_mode=UATCaptureMode.TEST_DOUBLE,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["pipeline_status"] = "FAILED"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(UATCaptureError, match="fingerprint is stale or invalid"):
        load_issue_v1_uat_observation(output)
