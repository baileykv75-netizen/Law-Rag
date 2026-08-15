from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest

from app.ai_audit_models import AuditContextPackage, ModelAuditEnvelope
from app.ai_audit_providers import DeepSeekProvider


@pytest.mark.deepseek_smoke
def test_real_deepseek_returns_stage8_json_envelope() -> None:
    if os.getenv("LAW_RAG_DEEPSEEK_SMOKE", "0") != "1":
        pytest.skip("Set LAW_RAG_DEEPSEEK_SMOKE=1 to opt in to a real paid/network DeepSeek smoke test.")
    if not os.getenv("DEEPSEEK_API_KEY", "").strip():
        pytest.skip("DEEPSEEK_API_KEY is required for the opt-in DeepSeek smoke test.")

    context = AuditContextPackage(
        job_id=uuid4(),
        as_of=date(2026, 8, 15),
        contract_schema_version="1.0.0",
        contract_source_fingerprint="fictional-public-smoke-source",
        contract_content_fingerprint="fictional-public-smoke-content",
        warnings=[
            "This is a synthetic empty-context integration smoke. No private contract data is present."
        ],
        context_fingerprint="fictional-public-smoke-context",
    )

    result = DeepSeekProvider().generate(context)
    envelope = ModelAuditEnvelope.model_validate_json(result.content)

    assert isinstance(envelope.findings, list)
    assert result.provider == "deepseek"
    assert result.raw_response_hash
