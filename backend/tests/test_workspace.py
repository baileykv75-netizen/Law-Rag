from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.ai_audit_models import AiAuditReport
from app.audit_rule_models import AuditProfile, AuditRuleReport, RuleCounts
from app.contract_models import CanonicalContract
from app.main import app
from app.review_comparison_models import (
    AgentFollowUpDecision,
    OverallComparisonState,
    ReviewComparisonReport,
)
from app.review_report import ReviewReport
from app.review_workflow import Stage9cWorkflowState
from app.secondary_review_models import SecondaryReviewReport


client = TestClient(app)


def _native_pdf_bytes() -> bytes:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = StreamObject()
    stream._data = (
        b"BT /F1 12 Tf 72 720 Td "
        b"(Fictional contract payment terms require performance within thirty days after acceptance.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _upload_native_job(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    response = client.post(
        "/api/documents",
        files={"file": ("workspace-fixture.pdf", _native_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["job_id"]


def _complete_stage9_artifacts(tmp_path: Path, job_id: str) -> None:
    job_uuid = UUID(job_id)
    job_dir = tmp_path / "jobs" / job_id
    contract = CanonicalContract(
        job_id=job_uuid,
        filename="workspace-fixture.pdf",
        source_fingerprint="workspace-source",
        evidence_unit_count=1,
    )
    (job_dir / "contract.json").write_text(contract.model_dump_json(indent=2), encoding="utf-8")

    rules = AuditRuleReport(
        job_id=job_uuid,
        contract_schema_version=contract.schema_version,
        contract_source_fingerprint="workspace-source",
        contract_content_fingerprint="workspace-content",
        profile=AuditProfile(
            profile_id="workspace-profile",
            version="1.0.0",
            title="Workspace fixture",
        ),
        counts=RuleCounts(total=0, passed=0, failed=0, review=0, not_applicable=0),
    )
    (job_dir / "audit-rules.json").write_text(rules.model_dump_json(indent=2), encoding="utf-8")

    primary = AiAuditReport(
        job_id=job_uuid,
        as_of=date(2026, 8, 15),
        provider="fake-primary",
        model="fake-primary-v1",
        contract_source_fingerprint="workspace-source",
        contract_content_fingerprint="workspace-content",
        context_fingerprint="p" * 64,
        raw_response_hash="a" * 64,
        findings=[],
    )
    (job_dir / "ai-audit.json").write_text(primary.model_dump_json(indent=2), encoding="utf-8")

    secondary = SecondaryReviewReport(
        job_id=job_uuid,
        as_of=date(2026, 8, 15),
        primary_provider=primary.provider,
        primary_model=primary.model,
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint="s" * 64,
        provider="fake-secondary",
        model="fake-secondary-v1",
        raw_response_hash="b" * 64,
        finding_reviews=[],
        possible_omissions=[],
    )
    (job_dir / "secondary-review.json").write_text(secondary.model_dump_json(indent=2), encoding="utf-8")

    comparison = ReviewComparisonReport(
        job_id=job_id,
        primary_context_fingerprint=primary.context_fingerprint,
        secondary_context_fingerprint=secondary.secondary_context_fingerprint,
        overall_state=OverallComparisonState.AGREEMENT,
        follow_up=AgentFollowUpDecision.NOT_REQUIRED,
    )
    report = ReviewReport(
        job_id=job_uuid,
        as_of="2026-08-15",
        final_state=Stage9cWorkflowState.DUAL_MODEL_AGREEMENT,
        primary_provider=primary.provider,
        primary_model=primary.model,
        secondary_provider=secondary.provider,
        secondary_model=secondary.model,
        primary_external_call_occurred=False,
        secondary_external_call_occurred=False,
        primary_findings=[],
        secondary_reviews=[],
        comparison=comparison,
    )
    (job_dir / "review-report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    legal_dir = tmp_path / "legal"
    legal_dir.mkdir(parents=True, exist_ok=True)
    (legal_dir / "legal.db").write_bytes(b"workspace-legal-store")
    (legal_dir / "retrieval.db").write_bytes(b"workspace-retrieval-index")


def test_workspace_load_is_read_only_and_explicitly_partial(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_native_job(tmp_path, monkeypatch)

    def forbidden_provider_call(*args, **kwargs):
        raise AssertionError("workspace GET must not resolve or call an external model provider")

    monkeypatch.setattr("app.ai_audit_providers.provider_from_name", forbidden_provider_call)
    monkeypatch.setattr("app.secondary_review_providers.secondary_provider_from_name", forbidden_provider_call)

    response = client.get(f"/api/documents/{job_id}/workspace")
    assert response.status_code == 200
    body = response.json()

    assert body["job_id"] == job_id
    assert body["architecture"] == "ISSUE_V1"
    assert body["overall_state"] == "INCOMPLETE"
    assert body["source_available"] is True
    assert body["document"]["filename"] == "workspace-fixture.pdf"
    assert body["document"]["page_count"] == 1
    assert body["document"]["ocr_used"] is False
    assert body["review"]["primary_available"] is False
    assert body["review"]["secondary_available"] is False
    assert body["review"]["comparison_available"] is False
    assert body["issues"] == []

    stages = {item["stage"]: item for item in body["stages"]}
    assert stages["2"]["state"] == "READY"
    assert stages["3"]["state"] == "NOT_REQUIRED"
    assert stages["4"]["state"] == "MISSING"
    assert stages["5"]["state"] == "MISSING"
    assert stages["13B/C"]["state"] == "MISSING"
    assert stages["13D"]["state"] == "MISSING"
    assert stages["13E"]["state"] == "MISSING"
    assert stages["13F"]["state"] == "MISSING"
    assert stages["13G"]["state"] == "MISSING"


def test_complete_legacy_workspace_load_never_resolves_external_provider(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_native_job(tmp_path, monkeypatch)
    _complete_stage9_artifacts(tmp_path, job_id)

    def forbidden_provider_call(*args, **kwargs):
        raise AssertionError("complete workspace GET must not resolve or call an external model provider")

    monkeypatch.setattr("app.ai_audit_providers.provider_from_name", forbidden_provider_call)
    monkeypatch.setattr("app.secondary_review_providers.secondary_provider_from_name", forbidden_provider_call)

    response = client.get(f"/api/documents/{job_id}/workspace")

    assert response.status_code == 200
    body = response.json()
    assert body["architecture"] == "LEGACY_RC2"
    assert body["overall_state"] == "COMPLETE"
    assert body["review"]["primary_available"] is True
    assert body["review"]["secondary_available"] is True
    assert body["review"]["comparison_available"] is True
    assert body["review"]["final_review_state"] == "DUAL_MODEL_AGREEMENT"
    stages = {item["stage"]: item for item in body["stages"]}
    assert all(
        stage["state"] in {"READY", "NOT_REQUIRED"}
        for stage in stages.values()
    )


def test_unknown_workspace_job_returns_404_without_creating_runtime_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()

    response = client.get(f"/api/documents/{job_id}/workspace")

    assert response.status_code == 404
    assert not (tmp_path / "jobs" / str(job_id)).exists()
    assert not (tmp_path / "uploads" / str(job_id)).exists()


def test_workspace_surfaces_invalid_artifact_instead_of_hiding_it(tmp_path: Path, monkeypatch) -> None:
    job_id = _upload_native_job(tmp_path, monkeypatch)
    job_dir = tmp_path / "jobs" / job_id
    (job_dir / "contract.json").write_text("{}", encoding="utf-8")

    response = client.get(f"/api/documents/{job_id}/workspace")

    assert response.status_code == 200
    body = response.json()
    stages = {item["stage"]: item for item in body["stages"]}
    assert stages["4"]["state"] == "INVALID"
    assert body["overall_state"] == "INVALID"


def test_stage9_routes_remain_mounted_on_main_application(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    response = client.get(f"/api/documents/{job_id}/review-report")

    assert response.status_code == 404
    assert "review-report.json" in response.json()["detail"]
