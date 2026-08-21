from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from app.audit_planner import run_audit_planner
from app.audit_planner_provider import FakeAuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.issue_legal_context import build_issue_legal_context
from app.issue_primary_audit import run_issue_primary_audit
from app.issue_primary_audit_models import IssuePrimaryAuditArtifact, IssuePrimaryAuditStatus
from app.issue_review_report import build_issue_review_report
from app.issue_secondary_review import run_issue_secondary_review
from app.issue_secondary_review_models import IssueSecondaryReviewArtifact, IssueSecondaryReviewStatus
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.models import SourceMethod
from app.pipeline_control import set_provider_mode
from app.pipeline_control_models import ProviderExecutionMode
from app.pipeline_models import PipelineReport, PipelineStage, PipelineStageRecord, PipelineStageState, PipelineStatus
from app.storage import (
    job_contract_path,
    job_issue_primary_audit_path,
    job_issue_review_report_path,
    job_issue_secondary_review_path,
    job_pipeline_path,
    legal_db_path,
    legal_retrieval_index_path,
)
from app.uat_capture import capture_issue_v1_uat
from app.uat_capture_models import UATCaptureMode, UATChainState, UATProviderStage


AS_OF = date(2026, 8, 18)


def _stable_fingerprint(model) -> str:
    payload = model.model_dump(mode="json", exclude={"artifact_fingerprint"})
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contract() -> CanonicalContract:
    provenance = ExtractionProvenance(
        extractor_id="stage16d-interruption-fixture",
        confidence=ExtractionConfidence.HIGH,
    )
    text = "乙方逾期履行的，应按合同总金额的50%支付违约金；甲方对格式条款负有提示说明义务。"
    quote = f"第八条 违约责任\n{text}"
    return CanonicalContract(
        job_id=uuid4(),
        filename="stage16d-interruption.pdf",
        source_fingerprint="stage16d-interruption-source",
        evidence_unit_count=1,
        clauses=[
            Clause(
                clause_id="clause-008",
                heading_token="第八条",
                heading_text="违约责任",
                body_text=text,
                level=1,
                page_start=1,
                page_end=1,
                source_spans=[
                    SourceSpan(
                        page_number=1,
                        evidence_ids=["evidence-stage16d-interruption"],
                        source_method=SourceMethod.NATIVE_PDF_TEXT,
                        quote=quote,
                        char_start=0,
                        char_end=len(quote),
                    )
                ],
                provenance=provenance,
            )
        ],
    )


def _forbid_network(monkeypatch) -> None:
    class ForbiddenHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Stage 16.4 interruption regression attempted outbound HTTP.")

    monkeypatch.setattr(httpx, "Client", ForbiddenHttpClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenHttpClient)


def _write_pipeline(job_id, *, status: PipelineStatus, current_stage: PipelineStage, interrupted_stage: PipelineStage | None) -> None:
    now = datetime.now(timezone.utc)
    audit_stages = [
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
    records: list[PipelineStageRecord] = []
    blocked = False
    for index, stage in enumerate(audit_stages):
        if interrupted_stage is not None and stage == interrupted_stage:
            blocked = True
            state = PipelineStageState.CANCELLED
        elif blocked:
            state = PipelineStageState.PENDING
        else:
            state = PipelineStageState.COMPLETE
        records.append(
            PipelineStageRecord(
                stage=stage,
                state=state,
                label=stage.value,
                progress_percent=min(100, 10 + index * 11),
            )
        )
    report = PipelineReport(
        job_id=job_id,
        status=status,
        current_stage=current_stage,
        progress_percent=70 if status != PipelineStatus.COMPLETE else 100,
        as_of=AS_OF,
        use_semantic=False,
        started_at=now,
        updated_at=now,
        completed_at=now if status == PipelineStatus.COMPLETE else None,
        stages=records,
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
    import_manifest(repo_root / "legal_data" / "seed" / "manifest.json", legal_db_path(), rebuild=True)
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)

    plan = run_audit_planner(contract.job_id, provider=FakeAuditPlannerProvider())
    build_issue_legal_context(contract.job_id, as_of=AS_OF, use_semantic=False)
    primary = run_issue_primary_audit(contract.job_id, provider_name="fake")
    secondary = run_issue_secondary_review(contract.job_id, provider_name="fake")
    build_issue_review_report(contract.job_id)
    _write_pipeline(
        contract.job_id,
        status=PipelineStatus.COMPLETE,
        current_stage=PipelineStage.COMPLETE,
        interrupted_stage=None,
    )
    return contract, plan, primary, secondary


def _persist_interrupted_primary(primary: IssuePrimaryAuditArtifact) -> None:
    primary = primary.model_copy(deep=True)
    primary.status = IssuePrimaryAuditStatus.INTERRUPTED
    if primary.results:
        removed_issue = primary.results[-1].issue_id
        primary.results = primary.results[:-1]
        primary.provider_calls = [item for item in primary.provider_calls if item.issue_id != removed_issue]
    primary.completed_issue_count = len(primary.results)
    primary.artifact_fingerprint = _stable_fingerprint(primary)
    job_issue_primary_audit_path(primary.job_id).write_text(primary.model_dump_json(indent=2), encoding="utf-8")


def _persist_interrupted_secondary(secondary: IssueSecondaryReviewArtifact) -> None:
    secondary = secondary.model_copy(deep=True)
    secondary.status = IssueSecondaryReviewStatus.INTERRUPTED
    if secondary.results:
        removed_issue = secondary.results[-1].issue_id
        secondary.results = secondary.results[:-1]
        secondary.provider_calls = [item for item in secondary.provider_calls if item.issue_id != removed_issue]
    secondary.completed_issue_count = len(secondary.results)
    secondary.artifact_fingerprint = _stable_fingerprint(secondary)
    job_issue_secondary_review_path(secondary.job_id).write_text(secondary.model_dump_json(indent=2), encoding="utf-8")


def test_uat_capture_preserves_primary_interrupted_checkpoint(tmp_path: Path, monkeypatch) -> None:
    contract, plan, primary, _ = _prepare_complete_chain(tmp_path, monkeypatch)
    _persist_interrupted_primary(primary)
    job_issue_secondary_review_path(contract.job_id).unlink()
    job_issue_review_report_path(contract.job_id).unlink()
    _write_pipeline(
        contract.job_id,
        status=PipelineStatus.CANCELLED,
        current_stage=PipelineStage.ISSUE_PRIMARY_AUDIT,
        interrupted_stage=PipelineStage.ISSUE_PRIMARY_AUDIT,
    )

    observation, sanitized = capture_issue_v1_uat(
        Path(__file__).resolve().parents[2],
        contract.job_id,
        tmp_path / "primary-interrupted.json",
        capture_mode=UATCaptureMode.TEST_DOUBLE,
    )

    assert observation.chain_state == UATChainState.PRIMARY_INTERRUPTED
    assert sanitized.chain_state == UATChainState.PRIMARY_INTERRUPTED
    assert observation.audit_plan_issue_count == len(plan.issues)
    assert observation.primary_completed_issue_count < len(plan.issues)
    assert observation.secondary_completed_issue_count == 0
    assert observation.compared_issue_count == 0
    assert all(item.stage != UATProviderStage.SECONDARY for item in observation.provider_calls)
    assert all(not item.secondary_result_present for item in observation.issue_coverage)
    assert all(not item.comparison_present for item in observation.issue_coverage)


def test_uat_capture_preserves_secondary_interrupted_checkpoint(tmp_path: Path, monkeypatch) -> None:
    contract, plan, _, secondary = _prepare_complete_chain(tmp_path, monkeypatch)
    _persist_interrupted_secondary(secondary)
    job_issue_review_report_path(contract.job_id).unlink()
    _write_pipeline(
        contract.job_id,
        status=PipelineStatus.CANCELLED,
        current_stage=PipelineStage.ISSUE_SECONDARY_REVIEW,
        interrupted_stage=PipelineStage.ISSUE_SECONDARY_REVIEW,
    )

    observation, sanitized = capture_issue_v1_uat(
        Path(__file__).resolve().parents[2],
        contract.job_id,
        tmp_path / "secondary-interrupted.json",
        capture_mode=UATCaptureMode.TEST_DOUBLE,
    )

    assert observation.chain_state == UATChainState.SECONDARY_INTERRUPTED
    assert sanitized.chain_state == UATChainState.SECONDARY_INTERRUPTED
    assert observation.primary_completed_issue_count == len(plan.issues)
    assert observation.secondary_completed_issue_count < len(plan.issues)
    assert observation.compared_issue_count == 0
    assert any(item.stage == UATProviderStage.SECONDARY for item in observation.provider_calls) or not secondary.provider_calls
    assert all(not item.comparison_present for item in observation.issue_coverage)
