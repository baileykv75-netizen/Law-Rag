from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.ai_audit_models import AiAuditFinding, EvidenceSufficiency, FindingSeverity, FindingState
from app.main import app
from app.review_comparison_models import (
    AgentFollowUpDecision,
    EvidenceSetComparison,
    EvidenceSetComparisonState,
    FindingComparison,
    OverallComparisonState,
    ReviewComparisonReport,
    RiskComparisonState,
    SeverityComparison,
    SeverityComparisonState,
)
from app.review_report import ReviewReport
from app.review_workflow import Stage9cWorkflowState
from app.secondary_review_models import SecondaryAssessment, SecondaryFindingReview
from app.storage import job_review_report_path


client = TestClient(app)


def _write_review_report(tmp_path: Path, monkeypatch) -> tuple[str, Path]:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()
    finding = AiAuditFinding(
        finding_id="finding-human-001",
        state=FindingState.SUPPORTED_FINDING,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        risk_category="违约责任",
        severity=FindingSeverity.HIGH,
        title="虚构违约金条款需要复核",
        reasoning_summary="仅用于人工复核持久化测试。",
        suggestion="由人工确认。",
        contract_evidence_ids=["contract-evidence-001"],
        legal_evidence_ids=["legal:test:v1:article-1"],
    )
    secondary = SecondaryFindingReview(
        review_id="secondary-human-001",
        primary_finding_id=finding.finding_id,
        assessment=SecondaryAssessment.SUPPORTED,
        severity=FindingSeverity.HIGH,
        reasoning_summary="二审支持该虚构发现。",
        suggestion="人工确认。",
        contract_evidence_ids=["contract-evidence-002"],
        legal_evidence_ids=["legal:test:v1:article-1"],
    )
    comparison = FindingComparison(
        comparison_id="comparison-human-001",
        primary_finding_id=finding.finding_id,
        risk_state=RiskComparisonState.AGREE_SUPPORTED,
        severity=SeverityComparison(
            primary=FindingSeverity.HIGH,
            secondary=FindingSeverity.HIGH,
            distance=0,
            state=SeverityComparisonState.AGREE,
        ),
        contract_evidence=EvidenceSetComparison(
            state=EvidenceSetComparisonState.DISJOINT,
            shared=[],
            primary_only=["contract-evidence-001"],
            secondary_only=["contract-evidence-002"],
        ),
        legal_basis=EvidenceSetComparison(
            state=EvidenceSetComparisonState.AGREE,
            shared=["legal:test:v1:article-1"],
            primary_only=[],
            secondary_only=[],
        ),
        overall_state=OverallComparisonState.AGREEMENT_WITH_REVIEW,
        material_reasons=[],
        follow_up=AgentFollowUpDecision.NOT_REQUIRED,
    )
    comparison_report = ReviewComparisonReport(
        job_id=str(job_id),
        primary_context_fingerprint="p" * 64,
        secondary_context_fingerprint="s" * 64,
        finding_comparisons=[comparison],
        overall_state=OverallComparisonState.AGREEMENT_WITH_REVIEW,
        follow_up=AgentFollowUpDecision.NOT_REQUIRED,
    )
    report = ReviewReport(
        job_id=job_id,
        as_of="2026-08-15",
        final_state=Stage9cWorkflowState.HUMAN_REVIEW_REQUIRED,
        primary_provider="fake-primary",
        primary_model="fake-v1",
        secondary_provider="fake-secondary",
        secondary_model="fake-v1",
        primary_external_call_occurred=False,
        secondary_external_call_occurred=False,
        primary_findings=[finding],
        secondary_reviews=[secondary],
        comparison=comparison_report,
        final_reasons=["fixture"],
    )
    path = job_review_report_path(job_id)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return str(job_id), path


def test_get_human_review_starts_empty_without_creating_model_activity(tmp_path: Path, monkeypatch) -> None:
    job_id, _ = _write_review_report(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("human review must not call a model provider")

    monkeypatch.setattr("app.ai_audit_providers.provider_from_name", forbidden)
    monkeypatch.setattr("app.secondary_review_providers.secondary_provider_from_name", forbidden)

    response = client.get(f"/api/documents/{job_id}/human-review")

    assert response.status_code == 200
    assert response.json()["revisions"] == []
    assert response.json()["latest_by_target"] == {}
    assert not (tmp_path / "jobs" / job_id / "human-review.json").exists()


def test_decision_appends_revision_and_server_snapshots_evidence(tmp_path: Path, monkeypatch) -> None:
    job_id, _ = _write_review_report(tmp_path, monkeypatch)

    first = client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "finding",
            "target_id": "finding-human-001",
            "state": "CONFIRMED",
            "reviewer_note": "人工确认第一版。",
        },
    )
    second = client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "finding",
            "target_id": "finding-human-001",
            "state": "NEEDS_MORE_REVIEW",
            "reviewer_note": "补充复核后保留疑问。",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    body = second.json()
    assert [item["revision"] for item in body["revisions"]] == [1, 2]
    latest = body["latest_by_target"]["finding:finding-human-001"]
    assert latest["state"] == "NEEDS_MORE_REVIEW"
    assert latest["contract_evidence_ids"] == ["contract-evidence-001", "contract-evidence-002"]
    assert latest["legal_evidence_ids"] == ["legal:test:v1:article-1"]
    persisted = json.loads((tmp_path / "jobs" / job_id / "human-review.json").read_text(encoding="utf-8"))
    assert len(persisted["revisions"]) == 2
    assert persisted["revisions"][0]["reviewer_note"] == "人工确认第一版。"


def test_prior_revisions_become_stale_when_review_report_changes(tmp_path: Path, monkeypatch) -> None:
    job_id, report_path = _write_review_report(tmp_path, monkeypatch)
    response = client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "finding",
            "target_id": "finding-human-001",
            "state": "CONFIRMED",
            "reviewer_note": "基于当前报告确认。",
        },
    )
    assert response.status_code == 200
    assert response.json()["revisions"][0]["is_stale"] is False

    raw = json.loads(report_path.read_text(encoding="utf-8"))
    raw["warnings"] = ["review report changed after decision"]
    report_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    refreshed = client.get(f"/api/documents/{job_id}/human-review")
    assert refreshed.status_code == 200
    assert refreshed.json()["revisions"][0]["is_stale"] is True


def test_invalid_target_cannot_create_human_decision(tmp_path: Path, monkeypatch) -> None:
    job_id, _ = _write_review_report(tmp_path, monkeypatch)

    response = client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "finding",
            "target_id": "invented-finding",
            "state": "CONFIRMED",
            "reviewer_note": "should fail",
        },
    )

    assert response.status_code == 404
    assert not (tmp_path / "jobs" / job_id / "human-review.json").exists()


def test_human_review_requires_stage9_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    job_id = uuid4()

    response = client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "finding",
            "target_id": "missing",
            "state": "CONFIRMED",
            "reviewer_note": "no report",
        },
    )

    assert response.status_code == 409
