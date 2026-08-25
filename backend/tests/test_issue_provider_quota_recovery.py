from __future__ import annotations

import json

import httpx

from app.issue_primary_audit_provider import (
    DeepSeekIssuePrimaryProvider,
    IssuePrimaryAuditProviderError,
)
from app.issue_secondary_review_provider import (
    IssueSecondaryReviewProviderError,
    KimiIssueSecondaryReviewProvider,
)


class _FakeResponse:
    status_code = 402
    text = json.dumps({"error": {"message": "quota exhausted"}})

    def raise_for_status(self) -> None:
        request = httpx.Request("POST", "https://example.invalid/chat/completions")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("quota exhausted", request=request, response=response)

    def json(self) -> dict:
        return {"error": {"message": "quota exhausted"}}


class _FakeClient:
    def __init__(self, *, timeout) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url, *, headers, json):
        return _FakeResponse()


def _deepseek_provider() -> DeepSeekIssuePrimaryProvider:
    provider = DeepSeekIssuePrimaryProvider.__new__(DeepSeekIssuePrimaryProvider)
    provider.api_key = "test-key"
    provider.base_url = "https://example.invalid"
    provider.model_name = "deepseek-test"
    provider.request_timeout_seconds = 1.0
    provider.connect_timeout_seconds = 1.0
    provider.max_attempts = 4
    provider.retry_backoff_seconds = 0.0
    return provider


def _kimi_provider() -> KimiIssueSecondaryReviewProvider:
    provider = KimiIssueSecondaryReviewProvider.__new__(KimiIssueSecondaryReviewProvider)
    provider.api_key = "test-key"
    provider.base_url = "https://example.invalid"
    provider.model_name = "kimi-test"
    provider.request_timeout_seconds = 1.0
    provider.connect_timeout_seconds = 1.0
    provider.max_attempts = 4
    provider.retry_backoff_seconds = 0.0
    return provider


def test_primary_provider_treats_deepseek_402_as_recoverable_quota_wait(monkeypatch) -> None:
    monkeypatch.setattr("app.issue_primary_audit_provider.httpx.Client", _FakeClient)
    monkeypatch.setattr("app.issue_primary_audit_provider.build_issue_primary_messages", lambda *_args, **_kwargs: [])

    try:
        _deepseek_provider()._request(object(), compact_response=False)  # type: ignore[arg-type]
    except IssuePrimaryAuditProviderError as exc:
        assert exc.recoverable is True
        assert exc.code == "DEEPSEEK_QUOTA_OR_BILLING_REQUIRED"
    else:  # pragma: no cover
        raise AssertionError("expected recoverable primary provider error")


def test_secondary_provider_treats_kimi_402_as_recoverable_quota_wait(monkeypatch) -> None:
    monkeypatch.setattr("app.issue_secondary_review_provider.httpx.Client", _FakeClient)
    monkeypatch.setattr("app.issue_secondary_review_provider.build_issue_secondary_messages", lambda *_args, **_kwargs: [])

    try:
        _kimi_provider()._request(object(), object(), compact_response=False)  # type: ignore[arg-type]
    except IssueSecondaryReviewProviderError as exc:
        assert exc.recoverable is True
        assert exc.code == "KIMI_QUOTA_OR_BILLING_REQUIRED"
    else:  # pragma: no cover
        raise AssertionError("expected recoverable secondary provider error")
