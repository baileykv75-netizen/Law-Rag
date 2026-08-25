from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

import httpx

from app.ai_audit_models import AuditContextPackage
from app.ai_audit_providers import DeepSeekProvider


def _context() -> AuditContextPackage:
    return AuditContextPackage(
        job_id=uuid4(),
        as_of=date(2026, 8, 15),
        contract_schema_version="1.0.0",
        contract_source_fingerprint="source",
        contract_content_fingerprint="content",
        context_fingerprint="context",
    )


def test_deepseek_v4_provider_uses_json_output_and_thinking_without_persisting_reasoning(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    captured: dict = {}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                request=request,
                json={
                    "id": "deepseek-test-id",
                    "model": "deepseek-v4-flash",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "reasoning_content": "private chain of thought that must not be persisted",
                                "content": '{"findings":[]}',
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                },
            )

    monkeypatch.setattr("app.ai_audit_providers.httpx.Client", FakeClient)
    provider = DeepSeekProvider()
    result = provider.generate(_context())

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["thinking"] == {"type": "enabled"}
    assert captured["json"]["reasoning_effort"] == "high"
    assert captured["json"]["stream"] is False
    assert "JSON" in captured["json"]["messages"][0]["content"]

    assert result.content == '{"findings":[]}'
    assert not hasattr(result, "reasoning_content")
    assert result.request_id == "deepseek-test-id"
    assert result.usage.total_tokens == 12
    assert len(result.raw_response_hash) == 64
    assert result.raw_response_hash != hashlib.sha256(result.content.encode("utf-8")).hexdigest()
