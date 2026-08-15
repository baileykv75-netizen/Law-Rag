from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmark import BenchmarkError, evaluate_benchmark, evaluate_benchmark_files, load_benchmark_dataset
from app.benchmark_models import BenchmarkDataClass, BenchmarkTaskType


def _public_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    base = repo_root / "benchmarks" / "public"
    return (
        base / "stage11a_schema_smoke.dataset.json",
        base / "stage11a_schema_smoke.observations.json",
    )


def test_public_stage11a_schema_smoke_covers_all_required_task_types() -> None:
    dataset_path, _ = _public_paths()
    dataset = load_benchmark_dataset(dataset_path)

    assert {case.task_type for case in dataset.cases} == set(BenchmarkTaskType)
    assert all(case.provenance.data_class != BenchmarkDataClass.PRIVATE_EXTERNAL for case in dataset.cases)
    assert dataset.dataset_id == "law-rag-stage11a-schema-smoke"


def test_public_stage11a_schema_smoke_evaluates_per_task_without_fake_overall_accuracy() -> None:
    dataset_path, observations_path = _public_paths()
    report = evaluate_benchmark_files(dataset_path, observations_path)

    assert report.all_cases_passed is True
    assert report.case_count == 9
    assert len(report.task_summaries) == 9
    assert all(summary.case_count == 1 for summary in report.task_summaries)
    assert all(summary.passed == 1 for summary in report.task_summaries)
    payload = report.model_dump(mode="json")
    assert "overall_accuracy" not in payload
    assert "legal_accuracy" not in payload


def test_failed_assertion_keeps_expected_observed_and_reason() -> None:
    dataset_path, observations_path = _public_paths()
    dataset = load_benchmark_dataset(dataset_path)
    from app.benchmark import load_benchmark_observations

    observations = load_benchmark_observations(observations_path)
    target = next(item for item in observations.observations if item.case_id == "smoke-ocr-001")
    target.observed["page_number"] = 9

    report = evaluate_benchmark(dataset, observations)
    result = next(item for item in report.case_results if item.case_id == "smoke-ocr-001")
    failed = next(item for item in result.assertions if item.assertion_id == "ocr-page")

    assert report.all_cases_passed is False
    assert result.passed is False
    assert failed.passed is False
    assert failed.expected == 1
    assert failed.observed == 9
    assert failed.reason == "EXACT_MISMATCH"
    assert "ocr-page:EXACT_MISMATCH" in result.failure_reasons


def test_missing_observation_and_case_version_mismatch_fail_explicitly() -> None:
    dataset_path, observations_path = _public_paths()
    dataset = load_benchmark_dataset(dataset_path)
    from app.benchmark import load_benchmark_observations

    observations = load_benchmark_observations(observations_path)
    observations.observations = [
        item for item in observations.observations if item.case_id != "smoke-rule-001"
    ]
    version_target = next(
        item for item in observations.observations if item.case_id == "smoke-structure-001"
    )
    version_target.case_version = "0.9.0"

    report = evaluate_benchmark(dataset, observations)
    missing = next(item for item in report.case_results if item.case_id == "smoke-rule-001")
    mismatch = next(item for item in report.case_results if item.case_id == "smoke-structure-001")

    assert missing.failure_reasons == ["MISSING_OBSERVATION"]
    assert mismatch.failure_reasons[0].startswith("CASE_VERSION_MISMATCH")


def test_dataset_identity_mismatch_is_rejected() -> None:
    dataset_path, observations_path = _public_paths()
    dataset = load_benchmark_dataset(dataset_path)
    from app.benchmark import load_benchmark_observations

    observations = load_benchmark_observations(observations_path)
    observations.dataset_version = "99.0.0"

    with pytest.raises(BenchmarkError, match="dataset identity/version"):
        evaluate_benchmark(dataset, observations)


def test_private_external_dataset_can_be_loaded_from_untracked_local_path(tmp_path: Path) -> None:
    dataset_payload = {
        "schema_version": "1.0.0",
        "dataset_id": "private-external-example",
        "dataset_version": "1.0.0",
        "title": "Local private benchmark example",
        "description": "Created only inside pytest tmp_path.",
        "cases": [
            {
                "case_id": "private-001",
                "case_version": "1.0.0",
                "fixture_id": "external-local-fixture",
                "task_type": "PRIMARY_AUDIT_FINDING",
                "title": "External local case",
                "provenance": {
                    "data_class": "PRIVATE_EXTERNAL",
                    "source_name": "local external benchmark",
                    "scope": "Not checked into the repository"
                },
                "expectations": [
                    {
                        "assertion_id": "state",
                        "pointer": "/state",
                        "comparison": "EXACT",
                        "expected": "REVIEW_REQUIRED"
                    }
                ]
            }
        ]
    }
    observation_payload = {
        "schema_version": "1.0.0",
        "dataset_id": "private-external-example",
        "dataset_version": "1.0.0",
        "observations": [
            {
                "case_id": "private-001",
                "case_version": "1.0.0",
                "observed": {"state": "REVIEW_REQUIRED"},
                "producer": {
                    "producer_id": "external-local-run",
                    "producer_version": "1.0.0"
                }
            }
        ]
    }
    dataset_path = tmp_path / "dataset.json"
    observations_path = tmp_path / "observations.json"
    dataset_path.write_text(json.dumps(dataset_payload, ensure_ascii=False), encoding="utf-8")
    observations_path.write_text(json.dumps(observation_payload, ensure_ascii=False), encoding="utf-8")

    report = evaluate_benchmark_files(dataset_path, observations_path)

    assert report.all_cases_passed is True
    assert report.task_summaries[0].task_type == BenchmarkTaskType.PRIMARY_AUDIT_FINDING
