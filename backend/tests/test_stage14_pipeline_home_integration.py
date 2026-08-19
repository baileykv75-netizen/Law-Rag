from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.evidence_models import (
    DocxParagraphAnchor,
    SourceDocumentIdentity,
    SourceEvidence,
    SourceEvidenceArtifact,
    SourceEvidenceWarning,
)
from app.main import DOCX_MEDIA_TYPE, app
from app.models import (
    DocumentInspection,
    DocumentKind,
    DocumentRoute,
    PageEvidence,
    PageRoute,
    SourceMethod,
)
from app.pipeline_models import PipelineReport, PipelineStage


client = TestClient(app)


def _seed_docx_job(root: Path, job_id: UUID, *, warnings: list[str] | None = None) -> None:
    job_dir = root / "jobs" / str(job_id)
    upload_dir = root / "uploads" / str(job_id)
    job_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)

    source = b"PK\x03\x04fictional-stage14-6-docx"
    (upload_dir / "source.docx").write_bytes(source)
    warning_messages = warnings or []
    inspection = DocumentInspection(
        job_id=job_id,
        filename="fictional-contract.docx",
        media_type=DOCX_MEDIA_TYPE,
        document_kind=DocumentKind.DOCX,
        page_count=0,
        route=DocumentRoute.NATIVE_TEXT,
        native_text_pages=0,
        ocr_required_pages=0,
        pages=[],
        evidence_count=4,
        warnings=warning_messages,
    )
    (job_dir / "document.json").write_text(
        json.dumps(inspection.model_dump(mode="json", exclude={"pages"}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    evidence_texts = [
        "设备采购合同",
        "第一条 服务范围",
        "甲方委托乙方提供设备采购与安装服务。",
        "合同总价为人民币100000元，乙方应于2026年9月1日前交付。",
    ]
    artifact = SourceEvidenceArtifact(
        job_id=job_id,
        source_document=SourceDocumentIdentity(
            job_id=job_id,
            filename=inspection.filename,
            media_type=inspection.media_type,
            document_kind=DocumentKind.DOCX,
            source_sha256=hashlib.sha256(source).hexdigest(),
            size_bytes=len(source),
        ),
        evidence=[
            SourceEvidence(
                evidence_id=f"ev-{job_id}-docx-p{index:06d}",
                order_index=index,
                text=text,
                source_method=SourceMethod.NATIVE_DOCX_TEXT,
                source_anchor=DocxParagraphAnchor(paragraph_index=index),
            )
            for index, text in enumerate(evidence_texts, start=1)
        ],
        warnings=[
            SourceEvidenceWarning(
                code=f"TEST_WARNING_{index}",
                message=message,
                blocks_complete_coverage=True,
            )
            for index, message in enumerate(warning_messages, start=1)
        ],
    )
    (job_dir / "evidence.json").write_text(
        artifact.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _seed_native_pdf_job(root: Path, job_id: UUID) -> None:
    job_dir = root / "jobs" / str(job_id)
    upload_dir = root / "uploads" / str(job_id)
    job_dir.mkdir(parents=True)
    upload_dir.mkdir(parents=True)
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\nfictional")
    page = PageEvidence(
        evidence_id=f"ev-{job_id}-p0001",
        page_number=1,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text="第一条 服务范围",
        character_count=8,
        non_whitespace_count=8,
        meaningful_ratio=1.0,
        suspicious_character_count=0,
        route=PageRoute.NATIVE_TEXT_USABLE,
        route_reason="fixture",
        source_locator="page:1",
    )
    inspection = DocumentInspection(
        job_id=job_id,
        filename="fictional-contract.pdf",
        media_type="application/pdf",
        document_kind=DocumentKind.PDF,
        page_count=1,
        route=DocumentRoute.NATIVE_TEXT,
        native_text_pages=1,
        ocr_required_pages=0,
        pages=[page],
        evidence_count=1,
    )
    (job_dir / "document.json").write_text(
        json.dumps(inspection.model_dump(mode="json", exclude={"pages"}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (job_dir / "evidence.json").write_text(
        json.dumps([page.model_dump(mode="json")], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wait(job_id: UUID, terminal: set[str], timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/documents/{job_id}/pipeline")
        if response.status_code == 200 and response.json()["status"] in terminal:
            return response.json()
        time.sleep(0.02)
    raise AssertionError("pipeline did not reach the expected terminal state")


def _complete_stage(stage: PipelineStage):
    def runner(report: PipelineReport) -> None:
        import app.pipeline as pipeline

        pipeline._mark_running(report, stage, f"stage14.6 fixture running {stage.value}")
        pipeline._mark_done(report, stage, detail=f"stage14.6 fixture done {stage.value}")

    return runner


def _patch_after_ocr(monkeypatch) -> None:
    import app.pipeline as pipeline

    for name, stage in (
        ("_run_structure_stage", PipelineStage.STRUCTURE),
        ("_run_rules_stage", PipelineStage.RULES),
        ("_run_audit_plan_stage", PipelineStage.AUDIT_PLAN),
        ("_run_issue_legal_context_stage", PipelineStage.ISSUE_LEGAL_CONTEXT),
        ("_run_issue_primary_stage", PipelineStage.ISSUE_PRIMARY_AUDIT),
        ("_run_issue_secondary_stage", PipelineStage.ISSUE_SECONDARY_REVIEW),
        ("_run_issue_review_stage", PipelineStage.ISSUE_REVIEW_REPORT),
    ):
        monkeypatch.setattr(pipeline, name, _complete_stage(stage))


def test_docx_enters_authoritative_pipeline_and_skips_ocr_without_provider_call(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_docx_job(tmp_path, job_id, warnings=["Tracked changes require source review."])

    import app.pipeline as pipeline

    def forbidden_ocr(*args, **kwargs):
        raise AssertionError("native DOCX must not initialize or call PaddleOCR")

    monkeypatch.setattr(pipeline, "run_ocr_for_job", forbidden_ocr)
    _patch_after_ocr(monkeypatch)

    response = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={
            "as_of": "2026-08-19",
            "use_semantic": False,
            "provider_mode": "REQUIRE_APPROVAL",
        },
    )
    assert response.status_code == 202
    completed = _wait(job_id, {"COMPLETE"})
    assert completed["current_stage"] == "COMPLETE"
    assert completed["progress_percent"] == 100
    assert [stage["stage"] for stage in completed["stages"]] == [
        "INGEST",
        "OCR",
        "STRUCTURE",
        "RULES",
        "AUDIT_PLAN",
        "ISSUE_LEGAL_CONTEXT",
        "ISSUE_PRIMARY_AUDIT",
        "ISSUE_SECONDARY_REVIEW",
        "ISSUE_REVIEW_REPORT",
    ]
    ocr_stage = next(stage for stage in completed["stages"] if stage["stage"] == "OCR")
    assert ocr_stage["state"] == "SKIPPED"
    assert "无需 OCR" in ocr_stage["detail"]


def test_docx_runs_real_local_structure_and_rules_before_existing_provider_approval_boundary(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_docx_job(tmp_path, job_id)

    import app.pipeline as pipeline

    class ConfiguredPlannerThatMustNotBeCalled:
        provider_name = "deepseek"
        model_name = "stage14.6-boundary-fixture"
        api_key = "synthetic-configured-key"

        def generate(self, planner_input):
            raise AssertionError("REQUIRE_APPROVAL must stop before the actual provider call")

    def forbidden_ocr(*args, **kwargs):
        raise AssertionError("native DOCX must not initialize or call PaddleOCR")

    monkeypatch.setattr(pipeline, "run_ocr_for_job", forbidden_ocr)
    monkeypatch.setattr(
        pipeline,
        "planner_provider_from_name",
        lambda provider_name: ConfiguredPlannerThatMustNotBeCalled(),
    )

    response = client.post(
        f"/api/documents/{job_id}/pipeline",
        json={
            "as_of": "2026-08-19",
            "use_semantic": False,
            "provider_mode": "REQUIRE_APPROVAL",
        },
    )
    assert response.status_code == 202
    paused = _wait(job_id, {"PAUSED_BEFORE_PROVIDER", "FAILED"})
    assert paused["status"] == "PAUSED_BEFORE_PROVIDER", paused
    assert paused["current_stage"] == "AUDIT_PLAN"
    assert paused["progress_percent"] == 48
    assert paused["failure_code"] == "PROVIDER_APPROVAL_REQUIRED"
    assert (tmp_path / "jobs" / str(job_id) / "contract.json").exists()
    assert (tmp_path / "jobs" / str(job_id) / "audit-rules.json").exists()
    ocr_stage = next(stage for stage in paused["stages"] if stage["stage"] == "OCR")
    structure_stage = next(stage for stage in paused["stages"] if stage["stage"] == "STRUCTURE")
    rules_stage = next(stage for stage in paused["stages"] if stage["stage"] == "RULES")
    assert ocr_stage["state"] == "SKIPPED"
    assert structure_stage["state"] == "COMPLETE"
    assert rules_stage["state"] == "COMPLETE"


def test_pipeline_loader_validates_docx_source_evidence_and_fails_closed_on_corruption(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_docx_job(tmp_path, job_id)

    import app.pipeline as pipeline

    loaded = pipeline._load_document(job_id)
    assert loaded.document_kind == DocumentKind.DOCX
    assert loaded.pages == []
    assert loaded.ocr_required_pages == 0

    (tmp_path / "jobs" / str(job_id) / "evidence.json").write_text("{}", encoding="utf-8")
    with pytest.raises(pipeline._StageFailure) as caught:
        pipeline._load_document(job_id)
    assert caught.value.code == "DOCUMENT_EVIDENCE_INVALID"


def test_pipeline_loader_preserves_paginated_pdf_evidence_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    _seed_native_pdf_job(tmp_path, job_id)

    import app.pipeline as pipeline

    loaded = pipeline._load_document(job_id)
    assert loaded.document_kind == DocumentKind.PDF
    assert loaded.page_count == 1
    assert loaded.pages[0].evidence_id == f"ev-{job_id}-p0001"
    assert loaded.ocr_required_pages == 0


def test_home_intake_exposes_complete_stage14_source_set_and_visible_source_warnings() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "frontend" / "src" / "IntakeApp.tsx"
    ).read_text(encoding="utf-8")

    assert "const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.jpg', '.jpeg', '.png']" in source
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in source
    assert "PDF · DOCX · JPG · PNG" in source
    assert "sourceWarningNotice" in source
    assert "源文件解析提示" in source
    assert "result.document_kind === 'docx'" in source
    assert "DOCX · ${result.evidence_count} 个源证据" in source
