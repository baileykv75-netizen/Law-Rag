from __future__ import annotations

import json
from uuid import uuid4

import pytest

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
    RECOVERY_MAX_TOKENS,
    AuditPlannerProviderError,
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
                why_review="单方调价可能显著改变交易价格与风险分配。",
                contract_object_ids=["clause-001"],
                questions=["调价触发条件和幅度是否明确？"],
                retrieval_queries=["服务合同 单方调价 价格变更"],
            )
        ],
    ).model_dump_json()


class _FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = body
        self.status_code = 200
        self.text = json.dumps(body, ensure_ascii=False)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def _provider() -> DeepSeekAuditPlannerProvider:
    provider = DeepSeekAuditPlannerProvider.__new__(DeepSeekAuditPlannerProvider)
    provider.api_key = "test-key"
    provider.base_url = "https://example.invalid"
    provider.model_name = "deepseek-test"
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
                "usage": {"prompt_tokens": 100, "completion_tokens": 5000, "total_tokens": 5100},
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
    assert payloads[0]["reasoning_effort"] == "high"
    assert "thinking" not in payloads[1]
    assert "reasoning_effort" not in payloads[1]
    assert payloads[1]["max_tokens"] == RECOVERY_MAX_TOKENS
    assert "RECOVERY MODE" in payloads[1]["messages"][0]["content"]


def test_planner_fails_only_after_compact_retry_is_also_truncated(monkeypatch) -> None:
    responses = [
        _FakeResponse(
            {
                "id": "first",
                "choices": [{"finish_reason": "length", "message": {"content": "{"}}],
            }
        ),
        _FakeResponse(
            {
                "id": "second",
                "choices": [{"finish_reason": "length", "message": {"content": "{"}}],
            }
        ),
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

    with pytest.raises(AuditPlannerProviderError, match="自动紧凑重试"):
        _provider().generate(_planner_input())

    assert calls == 2
