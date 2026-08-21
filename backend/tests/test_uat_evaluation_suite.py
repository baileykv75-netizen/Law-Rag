from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.evaluation_suite import EvaluationSuiteError, run_evaluation_suite
from app.evaluation_suite_models import EvaluationSuiteManifest
from app.uat_capture_models import IssueV1UATObservation


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_observation(path: Path, *, capture_mode: str = "REAL_PROVIDER", chain_state: str = "COMPLETE") -> IssueV1UATObservation:
    job_id = uuid4()
    complete = chain_state == "COMPLETE"
    primary_interrupted = chain_state == "PRIMARY_INTERRUPTED"
    payload = {
        "schema_version": "1.0.0",
        "capture_version": "stage16d-1.0.0",
        "capture_mode": capture_mode,
        "captured_at": "2026-08-21T08:30:00+00:00",
        "architecture": "ISSUE_V1",
        "job_id": str(job_id),
        "chain_state": chain_state,
        "pipeline_status": "COMPLETE" if complete else "CANCELLED",
        "pipeline_failure_code": None,
        "audit_plan_issue_count": 1,
        "primary_completed_issue_count": 0 if primary_interrupted else 1,
        "secondary_completed_issue_count": 1 if complete else 0,
        "compared_issue_count": 1 if complete else 0,
        "issue_coverage": [
            {
                "issue_id": "issue-secret-private-001",
                "primary_result_present": not primary_interrupted,
                "primary_provider_call_present": not primary_interrupted,
                "secondary_result_present": complete,
                "secondary_provider_call_present": complete,
                "comparison_present": complete,
            }
        ],
        "provider_calls": [
            {
                "stage": "PLANNER",
                "issue_id": None,
                "provider": "deepseek",
                "model": "deepseek-chat",
                "request_id": "private-planner-request-id",
                "finish_reason": "stop",
                "raw_response_hash": "a" * 64,
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        ],
        "artifacts": [
            {
                "artifact": "pipeline.json",
                "file_sha256": "1" * 64,
                "embedded_fingerprint": None,
            },
            {
                "artifact": "audit-plan.json",
                "file_sha256": "2" * 64,
                "embedded_fingerprint": "3" * 64,
            },
            {
                "artifact": "issue-legal-context.json",
                "file_sha256": "4" * 64,
                "embedded_fingerprint": "5" * 64,
            },
        ],
    }
    if not primary_interrupted:
        payload["provider_calls"].append(
            {
                "stage": "PRIMARY",
                "issue_id": "issue-secret-private-001",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "request_id": "private-primary-request-id",
                "finish_reason": "stop",
                "raw_response_hash": "b" * 64,
                "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            }
        )
        payload["artifacts"].append(
            {
                "artifact": "issue-primary-audit.json",
                "file_sha256": "6" * 64,
                "embedded_fingerprint": "7" * 64,
            }
        )
    if complete:
        payload["provider_calls"].append(
            {
                "stage": "SECONDARY",
                "issue_id": "issue-secret-private-001",
                "provider": "kimi",
                "model": "kimi-k3",
                "request_id": "private-secondary-request-id",
                "finish_reason": "stop",
                "raw_response_hash": "c" * 64,
                "usage": {"prompt_tokens": 18, "completion_tokens": 7, "total_tokens": 25},
            }
        )
        payload["artifacts"].extend(
            [
                {
                    "artifact": "issue-secondary-review.json",
                    "file_sha256": "8" * 64,
                    "embedded_fingerprint": "9" * 64,
                },
                {
                    "artifact": "issue-review-report.json",
                    "file_sha256": "d" * 64,
                    "embedded_fingerprint": "e" * 64,
                },
            ]
        )
    payload["observation_fingerprint"] = _fingerprint(payload)
    observation = IssueV1UATObservation.model_validate(payload)
    path.write_text(observation.model_dump_json(indent=2), encoding="utf-8")
    return observation


def _write_suite(path: Path, observation_name: str) -> Path:
    payload = {
        "schema_version": "1.0.0",
        "suite_id": "stage16d-private-uat-suite",
        "suite_version": "1.0.0",
        "title": "Stage 16.4 private UAT capture suite",
        "description": "Ephemeral pytest-only UAT capture integration fixture.",
        "suite_class": "REAL_PROVIDER_UAT",
        "entries": [
            {
                "entry_id": "issue-v1-capture",
                "kind": "UAT_CAPTURE",
                "scope": "Provider-chain provenance only; not legal correctness.",
                "uat_observation_path": observation_name,
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_real_provider_uat_capture_entry_is_sanitized_and_complete(tmp_path: Path) -> None:
    observation_path = tmp_path / "observation.json"
    observation = _write_observation(observation_path)
    suite_path = _write_suite(tmp_path / "suite.json", observation_path.name)

    report = run_evaluation_suite(_repo_root(), suite_path, tmp_path / "work")
    rendered = report.model_dump_json()

    assert report.all_entries_passed is True
    entry = report.entries[0]
    assert entry.kind.value == "UAT_CAPTURE"
    assert entry.identity_id == "ISSUE_V1"
    assert entry.identity_version == "stage16d-1.0.0"
    assert entry.unit_label == "uat_capture"
    assert entry.passed_count == 1
    assert {producer.provider for producer in entry.producers} == {"deepseek", "kimi"}
    assert entry.source_fingerprints["uat_observation_fingerprint"] == observation.observation_fingerprint

    assert str(observation.job_id) not in rendered
    assert "issue-secret-private-001" not in rendered
    assert "private-planner-request-id" not in rendered
    assert "private-primary-request-id" not in rendered
    assert "private-secondary-request-id" not in rendered
    assert "a" * 64 not in rendered
    assert "b" * 64 not in rendered
    assert "c" * 64 not in rendered
    assert "overall_accuracy" not in rendered
    assert "legal_accuracy" not in rendered


def test_uat_capture_entry_rejects_test_double_observation(tmp_path: Path) -> None:
    observation_path = tmp_path / "observation.json"
    _write_observation(observation_path, capture_mode="TEST_DOUBLE")
    suite_path = _write_suite(tmp_path / "suite.json", observation_path.name)

    with pytest.raises(EvaluationSuiteError, match="REAL_PROVIDER observations"):
        run_evaluation_suite(_repo_root(), suite_path, tmp_path / "work")


def test_interrupted_uat_capture_is_preserved_but_not_reported_as_pass(tmp_path: Path) -> None:
    observation_path = tmp_path / "observation.json"
    _write_observation(observation_path, chain_state="PRIMARY_INTERRUPTED")
    suite_path = _write_suite(tmp_path / "suite.json", observation_path.name)

    report = run_evaluation_suite(_repo_root(), suite_path, tmp_path / "work")

    assert report.all_entries_passed is False
    assert report.entries[0].passed is False
    assert report.entries[0].failed_count == 1
    assert any("PRIMARY_INTERRUPTED" in warning for warning in report.entries[0].warnings)


def test_uat_capture_entry_is_rejected_outside_real_provider_uat_suite() -> None:
    payload = {
        "schema_version": "1.0.0",
        "suite_id": "bad-public-suite",
        "suite_version": "1.0.0",
        "title": "Bad suite",
        "description": "Schema boundary fixture.",
        "suite_class": "PUBLIC_REGRESSION",
        "entries": [
            {
                "entry_id": "bad-uat",
                "kind": "UAT_CAPTURE",
                "scope": "invalid placement",
                "uat_observation_path": "observation.json",
            }
        ],
    }

    with pytest.raises(ValidationError, match="valid only in REAL_PROVIDER_UAT"):
        EvaluationSuiteManifest.model_validate(payload)
