from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import httpx

from app.ai_audit_models import AiAuditReport, AuditContextPackage
from app.secondary_review_models import SecondaryReviewContext
from app.secondary_review_providers import KimiSecondaryReviewProvider


def _context() -> SecondaryReviewContext:
    job_id = uuid4()
    as_of = date(2026, 8, 15)
    audit_context = AuditContextPackage(
        job_id=job_id,
        as_of=as_of,
        contract_schema_version="1.0.0",
        contract_source_fingerprint="source-fingerprint",
        contract_content_fingerprint="content-fingerprint",
        contract_items=[],
        rule_items=[],
        issues=[],
        warnings=[],
        context_fingerprint="primary-context-fingerprint",
    )
    primary = AiAuditReport(
        job_id=job_id,
        as_of=as_of,
        provider="deepseek",
        model="deepseek-v4-pro",
        contract_source_fingerprint="source-fingerprint",
        contract_content_fingerprint="content-fingerprint",
        context_fingerprint="primary-context-fingerprint",
        raw_response_hash="raw-primary-hash",
        findings=[],
        warnings=[],
        supplied_legal_evidence_ids=[],
        supplied_contract_evidence_ids=[],
    )
    return SecondaryReviewContext(
        job_id=job_id,
        as_of=as_of,
        primary_report=primary,
        audit_context=audit_context,
        context_fingerprint="secondary-context-fingerprint",
    )


class _Response:
    status_code = 200

    def __init__(self) -> None:
        self._body = {
            "id": "cmpl-kimi-test",
            "model": "kimi-k3",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "reasoning_content": "hidden reasoning that Law-Rag must not persist",
                        "content": json.dumps(
                            {"finding_reviews": [], "possible_omissions": []},
                            ensure_ascii=False,
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cached_tokens": 5,
            },
        }
        self.text = json.dumps(self._body, ensure_ascii=False)

    def json(self):
        return self._body

    def raise_for_status(self) -> None:
        return None


class _RecordingClient:
    last_url = None
    last_headers = None
    last_json = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, headers, json):
        type(self).last_url = url
        type(self).last_headers = headers
        type(self).last_json = json
        return _Response()


def test_kimi_k3_secondary_request_uses_current_contract_and_discards_reasoning(monkeypatch) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-secret")
    monkeypatch.delenv("MOONSHOT_BASE_URL", raising=False)
    monkeypatch.delenv("MOONSHOT_MODEL", raising=False)
    monkeypatch.setattr(httpx, "Client", _RecordingClient)

    provider = KimiSecondaryReviewProvider()
    result = provider.generate(_context())

    assert _RecordingClient.last_url == "https://api.moonshot.cn/v1/chat/completions"
    assert _RecordingClient.last_headers["Authorization"] == "Bearer test-secret"
    payload = _RecordingClient.last_json
    assert payload["model"] == "kimi-k3"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["reasoning_effort"] == "max"
    assert payload["max_completion_tokens"] == 12000
    assert payload["stream"] is False
    assert "thinking" not in payload
    assert payload["messages"][0]["role"] == "system"
    assert "UNTRUSTED DATA" in payload["messages"][0]["content"]

    assert result.provider == "kimi"
    assert result.model == "kimi-k3"
    assert result.request_id == "cmpl-kimi-test"
    assert result.finish_reason == "stop"
    assert result.usage.total_tokens == 120
    assert "reasoning_content" not in result.model_dump_json()
    assert "hidden reasoning" not in result.content


def test_kimi_health_is_configuration_only(monkeypatch) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    health = KimiSecondaryReviewProvider().health()
    assert health.provider == "kimi"
    assert health.configured is False
    assert health.model == "kimi-k3"
    assert "MOONSHOT_API_KEY" in health.detail
