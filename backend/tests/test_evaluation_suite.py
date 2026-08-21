from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation_suite import EvaluationSuiteError, run_evaluation_suite
from app.evaluation_suite_models import EvaluationSuiteManifest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _single_case_dataset(*, data_class: str, expected_value: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "dataset_id": "stage16-local-example",
        "dataset_version": "1.0.0",
        "title": "Stage 16 local fixture",
        "description": "Ephemeral pytest-only benchmark fixture.",
        "cases": [
            {
                "case_id": "local-case-001",
                "case_version": "1.0.0",
                "fixture_id": "local-fixture-001",
                "task_type": "PRIMARY_AUDIT_FINDING",
                "title": "Local benchmark case",
                "provenance": {
                    "data_class": data_class,
                    "source_name": "pytest ephemeral fixture",
                    "scope": "Never checked into the repository"
                },
                "expectations": [
                    {
                        "assertion_id": "state",
                        "pointer": "/state",
                        "comparison": "EXACT",
                        "expected": expected_value
                    }
                ]
            }
        ]
    }


def _single_case_observations(*, observed_value: str, producer: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "dataset_id": "stage16-local-example",
        "dataset_version": "1.0.0",
        "observations": [
            {
                "case_id": "local-case-001",
                "case_version": "1.0.0",
                "observed": {"state": observed_value},
                "producer": producer
            }
        ]
    }


def _suite_payload(*, suite_class: str, dataset_path: str, observations_path: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "suite_id": "stage16-local-suite",
        "suite_version": "1.0.0",
        "title": "Stage 16 local suite",
        "description": "Ephemeral pytest-only evaluation suite.",
        "suite_class": suite_class,
        "entries": [
            {
                "entry_id": "local-benchmark",
                "kind": "BENCHMARK",
                "scope": "Ephemeral boundary test",
                "dataset_path": dataset_path,
                "observations_path": observations_path
            }
        ]
    }


def _contains_key(value, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(_contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def test_checked_in_public_stage16_suite_reuses_existing_evaluators_without_fake_overall_score(
    tmp_path: Path,
) -> None:
    root = _repo_root()
    suite_path = root / "benchmarks" / "public" / "stage16a_evaluation_suite.json"

    report = run_evaluation_suite(root, suite_path, tmp_path / "work")

    assert report.all_entries_passed is True
    assert report.suite_class.value == "PUBLIC_REGRESSION"
    assert [entry.entry_id for entry in report.entries] == [
        "stage11-schema-smoke",
        "stage11-public-quality-gates",
    ]
    assert report.entries[0].unit_label == "cases"
    assert report.entries[0].unit_count == 9
    assert report.entries[1].unit_label == "gates"
    assert report.entries[1].failed_count == 0
    payload = report.model_dump(mode="json")
    assert not _contains_key(payload, "overall_accuracy")
    assert not _contains_key(payload, "legal_accuracy")
    assert not _contains_key(payload, "expected")
    assert not _contains_key(payload, "observed")


def test_private_expert_suite_is_external_and_summary_does_not_leak_labels_or_observations(
    tmp_path: Path,
) -> None:
    secret_label = "SECRET-EXPERT-LABEL-DO-NOT-REPORT"
    dataset = _write_json(
        tmp_path / "dataset.json",
        _single_case_dataset(data_class="PRIVATE_EXTERNAL", expected_value=secret_label),
    )
    observations = _write_json(
        tmp_path / "observations.json",
        _single_case_observations(
            observed_value=secret_label,
            producer={"producer_id": "local-expert-run", "producer_version": "1.0.0"},
        ),
    )
    suite = _write_json(
        tmp_path / "suite.json",
        _suite_payload(
            suite_class="PRIVATE_EXPERT",
            dataset_path=dataset.name,
            observations_path=observations.name,
        ),
    )

    report = run_evaluation_suite(_repo_root(), suite, tmp_path / "work")
    rendered = report.model_dump_json()

    assert report.all_entries_passed is True
    assert report.entries[0].passed_count == 1
    assert report.entries[0].producers == []
    assert secret_label not in rendered
    assert "local-expert-run" not in rendered


def test_private_expert_suite_rejects_dataset_that_is_not_labeled_private_external(
    tmp_path: Path,
) -> None:
    dataset = _write_json(
        tmp_path / "dataset.json",
        _single_case_dataset(data_class="PUBLIC_SYNTHETIC", expected_value="PASS"),
    )
    observations = _write_json(
        tmp_path / "observations.json",
        _single_case_observations(
            observed_value="PASS",
            producer={"producer_id": "deterministic", "producer_version": "1.0.0"},
        ),
    )
    suite = _write_json(
        tmp_path / "suite.json",
        _suite_payload(
            suite_class="PRIVATE_EXPERT",
            dataset_path=dataset.name,
            observations_path=observations.name,
        ),
    )

    with pytest.raises(EvaluationSuiteError, match="PRIVATE_EXTERNAL"):
        run_evaluation_suite(_repo_root(), suite, tmp_path / "work")


def test_real_provider_uat_requires_provider_model_and_sha256_artifact_provenance(
    tmp_path: Path,
) -> None:
    dataset = _write_json(
        tmp_path / "dataset.json",
        _single_case_dataset(data_class="PUBLIC_SYNTHETIC", expected_value="PASS"),
    )
    observations = _write_json(
        tmp_path / "observations.json",
        _single_case_observations(
            observed_value="PASS",
            producer={"producer_id": "uat-run", "producer_version": "1.0.0"},
        ),
    )
    suite = _write_json(
        tmp_path / "suite.json",
        _suite_payload(
            suite_class="REAL_PROVIDER_UAT",
            dataset_path=dataset.name,
            observations_path=observations.name,
        ),
    )

    with pytest.raises(EvaluationSuiteError, match=r"producer\.provider and producer\.model"):
        run_evaluation_suite(_repo_root(), suite, tmp_path / "work-missing")

    _write_json(
        observations,
        _single_case_observations(
            observed_value="PASS",
            producer={
                "producer_id": "uat-run",
                "producer_version": "1.0.0",
                "provider": "fake",
                "model": "fixture",
                "artifact_fingerprint": "a" * 64,
            },
        ),
    )
    with pytest.raises(EvaluationSuiteError, match="Fake providers"):
        run_evaluation_suite(_repo_root(), suite, tmp_path / "work-fake")

    _write_json(
        observations,
        _single_case_observations(
            observed_value="PASS",
            producer={
                "producer_id": "uat-run-sensitive-local-id",
                "producer_version": "1.0.0",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "artifact_fingerprint": "b" * 64,
            },
        ),
    )
    report = run_evaluation_suite(_repo_root(), suite, tmp_path / "work-valid")
    rendered = report.model_dump_json()

    assert report.all_entries_passed is True
    assert report.entries[0].producers[0].provider == "deepseek"
    assert report.entries[0].producers[0].model == "deepseek-v4-pro"
    assert report.entries[0].producers[0].artifact_fingerprint == "b" * 64
    assert "uat-run-sensitive-local-id" not in rendered


def test_public_suite_manifest_cannot_be_run_from_external_or_private_location(tmp_path: Path) -> None:
    dataset = _write_json(
        tmp_path / "dataset.json",
        _single_case_dataset(data_class="PUBLIC_SYNTHETIC", expected_value="PASS"),
    )
    observations = _write_json(
        tmp_path / "observations.json",
        _single_case_observations(
            observed_value="PASS",
            producer={"producer_id": "deterministic", "producer_version": "1.0.0"},
        ),
    )
    suite = _write_json(
        tmp_path / "suite.json",
        _suite_payload(
            suite_class="PUBLIC_REGRESSION",
            dataset_path=str(dataset),
            observations_path=str(observations),
        ),
    )

    with pytest.raises(EvaluationSuiteError, match="benchmarks/public"):
        run_evaluation_suite(_repo_root(), suite, tmp_path / "work")


def test_manifest_rejects_duplicate_entry_ids() -> None:
    payload = {
        "schema_version": "1.0.0",
        "suite_id": "duplicate-suite",
        "suite_version": "1.0.0",
        "title": "Duplicate suite",
        "description": "Schema validation fixture.",
        "suite_class": "PUBLIC_REGRESSION",
        "entries": [
            {
                "entry_id": "same",
                "kind": "BENCHMARK",
                "scope": "first",
                "dataset_path": "benchmarks/public/a.json",
                "observations_path": "benchmarks/public/b.json"
            },
            {
                "entry_id": "same",
                "kind": "BENCHMARK",
                "scope": "second",
                "dataset_path": "benchmarks/public/c.json",
                "observations_path": "benchmarks/public/d.json"
            }
        ]
    }

    with pytest.raises(ValidationError, match="duplicate entry_id"):
        EvaluationSuiteManifest.model_validate(payload)
