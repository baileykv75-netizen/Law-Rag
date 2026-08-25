from __future__ import annotations

import json
from uuid import uuid4

import httpx

from app.audit_plan_models import (
    AuditPlannerInput,
    ContractType,
    ContractTypeConfidence,
    ModelAuditPlanDraft,
    ModelAuditPlanIssueDraft,
    PlannerContractItem,
    ReviewPriority,
)
from app.audit_planner_provider import (
    AuditPlannerProviderError,
    RECOVERY_MAX_TOKENS,
    DeepSeekAuditPlannerProvider,
)


def _planner_input() -> AuditPlannerInput:
    return AuditPlannerInput(
        job_id=uuid4(),
        contract_schema_version="test",
        contract_source_fingerprint="source",
        contract_content_fingerprint="content",
        contract_items=[
            PlannerContractItem(
                canonical_object_id="clause-001",
                object_type="CLAUSE",
                text="乙方可以单方调价并长期保留数据。",
                evidence_ids=["evidence-001"],
            )
        ],
        global_facts=[],
        deterministic_rule_hints=[],
        legacy_topic_hints=[],
        total_text_chars=16,
        input_fingerprint="input",
    )


def _valid_content() -> str:
    return ModelAuditPlanDraft(
        contract_type=ContractType.SERVICE,
        contract_type_confidence=ContractTypeConfidence.HIGH,
        contract_type_reasoning="合同主要约定技术服务。",
        issues=[
            ModelAuditPlanIssueDraft(
                client_issue_id="P-001",
                topic="单方调价",
                priority=ReviewPriority.HIGH_ATTENTION,
                why_review="单方调价需要结合交易背景继续审查。",
                contract_object_ids=["clause-001"],
                questions=["调价触发条件是否明确？"],
                retrieval_queries=["服务合同 单方调价"],
            )
        ],
    ).model_dump_json()


class _FakeResponse:
    def __init__(self, body: dict, *, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.text = json.dumps(body, ensure_ascii=False)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.invalid/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._body


def _provider() -> DeepSeekAuditPlannerProvider:
    provider = DeepSeekAuditPlannerProvider.__new__(DeepSeekAuditPlannerProvider)
    provider.api_key = "test-key"
    provider.base_url = "https://example.invalid"
    provider.model_name = "deepseek-test"
    provider.request_timeout_seconds = 120.0
    provider.connect_timeout_seconds = 15.0
    return provider


def test_planner_recovers_from_length_with_compact_non_thinking_retry(monkeypatch) -> None:
    responses = [
        _FakeResponse(
            {
                "id": "first",
                "model": "deepseek-test",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"contract_type":"SERVICE"'},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 4000, "total_tokens": 4100},
            }
        ),
        _FakeResponse(
            {
                "id": "second",
                "model": "deepseek-test",
                "choices": [{"finish_reason": "stop", "message": {"content": _valid_content()}}],
                "usage": {"prompt_tokens": 110, "completion_tokens": 700, "total_tokens": 810},
            }
        ),
    ]
    payloads: list[dict] = []

    class _FakeClient:
        def __init__(self, *, timeout) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url, *, headers, json):
            payloads.append(json)
            return responses.pop(0)

    monkeypatch.setattr("app.audit_planner_provider.httpx.Client", _FakeClient)

    result = _provider().generate(_planner_input())

    assert result.request_id == "second"
    assert result.finish_reason == "stop"
    assert len(payloads) == 2
    assert payloads[0]["thinking"] == {"type": "enabled"}
    assert payloads[0]["reasoning_effort"] == "medium"
    assert "thinking" not in payloads[1]
    assert "reasoning_effort" not in payloads[1]
    assert payloads[1]["max_tokens"] == RECOVERY_MAX_TOKENS
    assert "COMPACT RECOVERY MODE" in payloads[1]["messages"][0]["content"]


def test_planner_uses_bounded_fallback_after_all_three_outputs_are_truncated(monkeypatch) -> None:
    responses = [
        _FakeResponse({"id": "first", "choices": [{"finish_reason": "length", "message": {"content": "{"}}]}),
        _FakeResponse({"id": "second", "choices": [{"finish_reason": "length", "message": {"content": "{"}}]}),
        _FakeResponse({"id": "third", "choices": [{"finish_reason": "length", "message": {"content": "{"}}]}),
    ]
    calls = 0

    class _FakeClient:
        def __init__(self, *, timeout) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            return responses.pop(0)

    monkeypatch.setattr("app.audit_planner_provider.httpx.Client", _FakeClient)

    result = _provider().generate(_planner_input())
    draft = ModelAuditPlanDraft.model_validate_json(result.content)

    assert calls == 3
    assert result.finish_reason == "bounded_fallback"
    assert draft.contract_type == ContractType.UNKNOWN
    assert draft.contract_type_confidence == ContractTypeConfidence.LOW
    assert draft.issues == []
    assert "降级" in draft.contract_type_reasoning


def test_planner_retries_transient_disconnect_before_succeeding(monkeypatch) -> None:
    calls = 0

    class _FakeClient:
        def __init__(self, *, timeout) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            if calls < 4:
                request = httpx.Request("POST", url)
                raise httpx.RemoteProtocolError("server disconnected", request=request)
            return _FakeResponse(
                {
                    "id": "eventual-success",
                    "model": "deepseek-test",
                    "choices": [{"finish_reason": "stop", "message": {"content": _valid_content()}}],
                }
            )

    monkeypatch.setattr("app.audit_planner_provider.httpx.Client", _FakeClient)
    monkeypatch.setattr("app.audit_planner_provider.time.sleep", lambda _: None)

    result = _provider().generate(_planner_input())

    assert calls == 4
    assert result.request_id == "eventual-success"


def test_planner_treats_deepseek_402_as_recoverable_quota_wait(monkeypatch) -> None:
    class _FakeClient:
        def __init__(self, *, timeout) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url, *, headers, json):
            return _FakeResponse({"error": {"message": "quota exhausted"}}, status_code=402)

    monkeypatch.setattr("app.audit_planner_provider.httpx.Client", _FakeClient)

    try:
        _provider().generate(_planner_input())
    except AuditPlannerProviderError as exc:
        assert exc.recoverable is True
        assert exc.code == "DEEPSEEK_QUOTA_OR_BILLING_REQUIRED"
    else:  # pragma: no cover
        raise AssertionError("expected recoverable planner provider error")
