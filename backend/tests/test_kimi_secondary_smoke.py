from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest

from app.ai_audit_models import AiAuditReport, AuditContextPackage
from app.secondary_review_models import ModelSecondaryEnvelope, SecondaryReviewContext
from app.secondary_review_providers import KimiSecondaryReviewProvider

pytestmark = pytest.mark.kimi_smoke


def _empty_public_context() -> SecondaryReviewContext:
    job_id = uuid4()
    as_of = date(2026, 8, 15)
    audit_context = AuditContextPackage(
        job_id=job_id,
        as_of=as_of,
        contract_schema_version="1.0.0",
        contract_source_fingerprint="synthetic-public-source",
        contract_content_fingerprint="synthetic-public-content",
        contract_items=[],
        rule_items=[],
        issues=[],
        warnings=["Synthetic/public empty smoke context only."],
        context_fingerprint="synthetic-primary-context",
    )
    primary = AiAuditReport(
        job_id=job_id,
        as_of=as_of,
        provider="deepseek",
        model="synthetic-primary",
        contract_source_fingerprint="synthetic-public-source",
        contract_content_fingerprint="synthetic-public-content",
        context_fingerprint="synthetic-primary-context",
        raw_response_hash="synthetic-primary-hash",
        findings=[],
        warnings=["Synthetic/public empty smoke context only."],
        supplied_legal_evidence_ids=[],
        supplied_contract_evidence_ids=[],
    )
    return SecondaryReviewContext(
        job_id=job_id,
        as_of=as_of,
        primary_report=primary,
        audit_context=audit_context,
        context_fingerprint="synthetic-secondary-context",
    )


def test_real_kimi_k3_secondary_smoke() -> None:
    if os.getenv("LAW_RAG_KIMI_SMOKE", "0") != "1":
        pytest.skip("Set LAW_RAG_KIMI_SMOKE=1 to enable the paid/network Kimi smoke test.")
    if not os.getenv("MOONSHOT_API_KEY", "").strip():
        pytest.skip("MOONSHOT_API_KEY is required for the paid/network Kimi smoke test.")

    result = KimiSecondaryReviewProvider().generate(_empty_public_context())
    parsed = ModelSecondaryEnvelope.model_validate_json(result.content)

    assert result.provider == "kimi"
    assert result.model
    assert parsed.finding_reviews == []
