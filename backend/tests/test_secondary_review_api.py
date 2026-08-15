from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient

import app.secondary_review_api as api_module
from app.ai_audit_models import ProviderHealth
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


def _secondary_report(job_id):
    return SecondaryReviewReport(
        job_id=job_id,
        as_of=date(2026, 8, 15),
        primary_provider="deepseek",
        primary_model="deepseek-v4-pro",
        primary_context_fingerprint="primary-fp",
        secondary_context_fingerprint="secondary-fp",
        provider="kimi",
        model="kimi-k3",
        raw_response_hash="b" * 64,
        finding_reviews=[],
        possible_omissions=[],
    )


def _review_report(job_id):
    comparison = ReviewComparisonReport(
        job_id=str(job_id),
        primary_context_fingerprint="primary-fp",
        secondary_context_fingerprint="secondary-fp",
        finding_comparisons=[],
        omission_comparisons=[],
        overall_state=OverallComparisonState.AGREEMENT,
        follow_up=AgentFollowUpDecision.NOT_REQUIRED,
    )
    return ReviewReport(
        job_id=job_id,
        as_of="2026-08-15",
        final_state=Stage9cWorkflowState.DUAL_MODEL_AGREEMENT,
        primary_provider="deepseek",
        primary_model="deepseek-v4-pro",
        secondary_provider="kimi",
        secondary_model="kimi-k3",
        primary_external_call_occurred=True,
        secondary_external_call_occurred=True,
        comparison=comparison,
    )


def test_secondary_health_defaults_to_kimi_without_network_call(monkeypatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    response = client.get("/api/ai/secondary/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "kimi"
    assert payload["model"] == "kimi-k3"
    assert payload["configured"] is False


def test_secondary_review_post_is_mounted(monkeypatch) -> None:
    job_id = uuid4()
    expected = _secondary_report(job_id)
    monkeypatch.setattr(api_module, "run_secondary_review", lambda supplied_job_id, request: expected)

    response = client.post(
        f"/api/documents/{job_id}/secondary-review",
        json={"provider": "kimi", "use_semantic": False},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "kimi"
    assert response.json()["model"] == "kimi-k3"


def test_review_report_post_is_local_api_boundary(monkeypatch) -> None:
    job_id = uuid4()
    expected = _review_report(job_id)
    monkeypatch.setattr(api_module, "build_review_report", lambda supplied_job_id: expected)

    response = client.post(f"/api/documents/{job_id}/review-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["final_state"] == "DUAL_MODEL_AGREEMENT"
    assert payload["secondary_provider"] == "kimi"
