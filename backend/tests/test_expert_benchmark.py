from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.benchmark_models import BenchmarkCase
from app.expert_benchmark import (
    ExpertBenchmarkError,
    expert_case_label_fingerprint,
    run_expert_benchmark,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _base_cases() -> list[dict]:
    private = {
        "data_class": "PRIVATE_EXTERNAL",
        "source_name": "Synthetic expert-protocol regression fixture",
        "scope": "Synthetic private fixture used only to validate Stage 16.3 protocol mechanics.",
    }
    return [
        {
            "case_id": "risk-positive-hit",
            "case_version": "1.0.0",
            "fixture_id": "private-risk-positive-hit",
            "task_type": "PRIMARY_AUDIT_FINDING",
            "title": "Positive expert finding correctly surfaced",
            "provenance": private,
            "tags": ["finding", "high-risk"],
            "expectations": [
                {
                    "assertion_id": "risk_class",
                    "pointer": "/risk_class",
                    "comparison": "EXACT",
                    "expected": "RISK",
                }
            ],
        },
        {
            "case_id": "risk-negative-fp",
            "case_version": "1.0.0",
            "fixture_id": "private-risk-negative-fp",
            "task_type": "PRIMARY_AUDIT_FINDING",
            "title": "Negative expert case incorrectly surfaced",
            "provenance": private,
            "tags": ["finding"],
            "expectations": [
                {
                    "assertion_id": "risk_class",
                    "pointer": "/risk_class",
                    "comparison": "EXACT",
                    "expected": "NO_RISK",
                }
            ],
        },
        {
            "case_id": "risk-negative-tn",
            "case_version": "1.0.0",
            "fixture_id": "private-risk-negative-tn",
            "task_type": "PRIMARY_AUDIT_FINDING",
            "title": "Negative expert case correctly left negative",
            "provenance": private,
            "tags": ["finding"],
            "expectations": [
                {
                    "assertion_id": "risk_class",
                    "pointer": "/risk_class",
                    "comparison": "EXACT",
                    "expected": "NO_RISK",
                }
            ],
        },
        {
            "case_id": "risk-ambiguous",
            "case_version": "1.0.0",
            "fixture_id": "private-risk-ambiguous",
            "task_type": "PRIMARY_AUDIT_FINDING",
            "title": "Professionally ambiguous risk case",
            "provenance": private,
            "tags": ["finding", "high-risk"],
            "expectations": [
                {
                    "assertion_id": "risk_class",
                    "pointer": "/risk_class",
                    "comparison": "EXACT",
                    "expected": "RISK",
                }
            ],
        },
        {
            "case_id": "legal-evidence-set",
            "case_version": "1.0.0",
            "fixture_id": "private-legal-evidence-set",
            "task_type": "LEGAL_CITATION_VALIDITY",
            "title": "Exhaustive expert Legal Evidence set",
            "provenance": private,
            "tags": ["citations"],
            "expectations": [
                {
                    "assertion_id": "legal_ids",
                    "pointer": "/legal_ids",
                    "comparison": "SET_EQUALS",
                    "expected": ["LE-1", "LE-2"],
                }
            ],
        },
    ]


def _audit_cases(cases: list[dict]) -> list[dict]:
    statuses = {
        "risk-positive-hit": ("AGREED", 2, 0),
        "risk-negative-fp": ("ADJUDICATED", 2, 1),
        "risk-negative-tn": ("AGREED", 3, 0),
        "risk-ambiguous": ("AMBIGUOUS", 2, 0),
        "legal-evidence-set": ("AGREED", 2, 0),
    }
    audits = []
    for payload in cases:
        case = BenchmarkCase.model_validate(payload)
        status, reviewers, adjudicators = statuses[case.case_id]
        audits.append(
            {
                "case_id": case.case_id,
                "case_version": case.case_version,
                "status": status,
                "reviewer_count": reviewers,
                "adjudicator_count": adjudicators,
                "label_fingerprint": expert_case_label_fingerprint(case),
            }
        )
    return audits


def _write_bundle(tmp_path: Path) -> tuple[Path, Path, dict, dict, dict, dict]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    private_root = tmp_path / "private-benchmark"
    private_root.mkdir()

    cases = _base_cases()
    dataset = {
        "schema_version": "1.0.0",
        "dataset_id": "private-expert-synthetic",
        "dataset_version": "1.0.0",
        "title": "Synthetic private expert benchmark mechanics",
        "description": "Private synthetic fixture for testing protocol mechanics only.",
        "cases": cases,
    }
    observations = {
        "schema_version": "1.0.0",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "observations": [
            {
                "case_id": "risk-positive-hit",
                "case_version": "1.0.0",
                "observed": {"risk_class": "RISK"},
                "producer": {"producer_id": "synthetic-system", "producer_version": "1"},
            },
            {
                "case_id": "risk-negative-fp",
                "case_version": "1.0.0",
                "observed": {"risk_class": "RISK"},
                "producer": {"producer_id": "synthetic-system", "producer_version": "1"},
            },
            {
                "case_id": "risk-negative-tn",
                "case_version": "1.0.0",
                "observed": {"risk_class": "NO_RISK"},
                "producer": {"producer_id": "synthetic-system", "producer_version": "1"},
            },
            {
                "case_id": "risk-ambiguous",
                "case_version": "1.0.0",
                "observed": {"risk_class": "NO_RISK"},
                "producer": {"producer_id": "synthetic-system", "producer_version": "1"},
            },
            {
                "case_id": "legal-evidence-set",
                "case_version": "1.0.0",
                "observed": {"legal_ids": ["LE-1", "LE-3"]},
                "producer": {"producer_id": "synthetic-system", "producer_version": "1"},
            },
        ],
    }
    audit = {
        "schema_version": "1.0.0",
        "protocol_id": "private-expert-protocol",
        "protocol_version": "1.0.0",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "cases": _audit_cases(cases),
    }
    protocol = {
        "schema_version": "1.0.0",
        "protocol_id": audit["protocol_id"],
        "protocol_version": audit["protocol_version"],
        "title": "Synthetic private expert protocol",
        "scope": "Tests Stage 16.3 private expert benchmark mechanics; not a professional accuracy claim.",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "dataset_path": "dataset.json",
        "observations_path": "observations.json",
        "label_audit_path": "label-audit.json",
        "minimum_reviewer_count": 2,
        "metrics": [
            {
                "metric_id": "risk-detection",
                "label": "Expert risk-finding classification",
                "metric_type": "BINARY_CLASSIFICATION",
                "assertion_id": "risk_class",
                "scope": "Synthetic PRIMARY_AUDIT_FINDING cases tagged finding.",
                "task_types": ["PRIMARY_AUDIT_FINDING"],
                "include_tags_all": ["finding"],
                "positive_values": ["RISK"],
                "negative_values": ["NO_RISK"],
            },
            {
                "metric_id": "legal-evidence-set",
                "label": "Expert Legal Evidence set extraction",
                "metric_type": "SET_EXTRACTION",
                "assertion_id": "legal_ids",
                "scope": "Synthetic exhaustive Legal Evidence labels.",
                "task_types": ["LEGAL_CITATION_VALIDITY"],
                "include_tags_all": ["citations"],
            },
        ],
    }

    protocol_path = private_root / "protocol.json"
    _write_json(private_root / "dataset.json", dataset)
    _write_json(private_root / "observations.json", observations)
    _write_json(private_root / "label-audit.json", audit)
    _write_json(protocol_path, protocol)
    return repo_root, protocol_path, dataset, observations, audit, protocol


def _rewrite_bundle(protocol_path: Path, dataset: dict, observations: dict, audit: dict, protocol: dict) -> None:
    root = protocol_path.parent
    _write_json(root / "dataset.json", dataset)
    _write_json(root / "observations.json", observations)
    _write_json(root / "label-audit.json", audit)
    _write_json(protocol_path, protocol)


def test_expert_benchmark_reports_scoped_metrics_and_visible_ambiguity(tmp_path: Path) -> None:
    repo_root, protocol_path, *_ = _write_bundle(tmp_path)

    report = run_expert_benchmark(repo_root, protocol_path)

    assert report.evaluator_version == "stage16c-1.0.0"
    assert report.label_quality.total_case_count == 5
    assert report.label_quality.agreed_case_count == 3
    assert report.label_quality.adjudicated_case_count == 1
    assert report.label_quality.ambiguous_case_count == 1
    assert report.label_quality.usable_case_count == 4
    assert report.label_quality.minimum_reviewer_count_observed == 2

    by_id = {metric.metric_id: metric for metric in report.metrics}
    risk = by_id["risk-detection"]
    assert risk.selected_case_count == 4
    assert risk.usable_case_count == 3
    assert risk.ambiguous_case_count == 1
    assert (risk.true_positive, risk.false_positive, risk.false_negative, risk.true_negative) == (1, 1, 0, 1)
    assert risk.precision == pytest.approx(0.5)
    assert risk.recall == pytest.approx(1.0)
    assert risk.f1 == pytest.approx(2 / 3)

    evidence = by_id["legal-evidence-set"]
    assert evidence.selected_case_count == 1
    assert evidence.usable_case_count == 1
    assert evidence.ambiguous_case_count == 0
    assert (evidence.true_positive, evidence.false_positive, evidence.false_negative) == (1, 1, 1)
    assert evidence.true_negative is None
    assert evidence.precision == pytest.approx(0.5)
    assert evidence.recall == pytest.approx(0.5)
    assert evidence.f1 == pytest.approx(0.5)

    assert set(report.source_fingerprints) == {
        "protocol_sha256",
        "dataset_sha256",
        "observations_sha256",
        "label_audit_sha256",
    }
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
    assert "risk-positive-hit" not in rendered
    assert "LE-1" not in rendered


def test_expert_benchmark_rejects_tracked_repository_protocol(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    tracked = repo_root / "benchmarks" / "private-protocol.json"
    _write_json(tracked, protocol)

    with pytest.raises(ExpertBenchmarkError, match="tracked repository paths are forbidden"):
        run_expert_benchmark(repo_root, tracked)


def test_expert_benchmark_requires_private_external_provenance(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    dataset["cases"][0]["provenance"] = {
        "data_class": "PUBLIC_SYNTHETIC",
        "source_name": "invalid-public-label",
        "scope": "must be rejected",
    }
    audit["cases"] = _audit_cases(dataset["cases"])
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="PRIVATE_EXTERNAL"):
        run_expert_benchmark(repo_root, protocol_path)


def test_expert_benchmark_rejects_selective_observation_omission(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    observations["observations"] = observations["observations"][:-1]
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="selective omission is forbidden"):
        run_expert_benchmark(repo_root, protocol_path)


def test_expert_benchmark_rejects_selective_label_audit_omission(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    audit["cases"] = audit["cases"][:-1]
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="selective label auditing is forbidden"):
        run_expert_benchmark(repo_root, protocol_path)


def test_expert_benchmark_rejects_insufficient_reviewers(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    audit["cases"][0]["reviewer_count"] = 1
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="fewer expert reviewers"):
        run_expert_benchmark(repo_root, protocol_path)


def test_expert_benchmark_rejects_stale_label_fingerprint_after_truth_change(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    dataset["cases"][0]["expectations"][0]["expected"] = "NO_RISK"
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="label fingerprint is stale"):
        run_expert_benchmark(repo_root, protocol_path)


def test_expert_benchmark_rejects_partial_set_truth(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    set_case = next(case for case in dataset["cases"] if case["case_id"] == "legal-evidence-set")
    set_case["expectations"][0]["comparison"] = "SET_CONTAINS"
    audit["cases"] = _audit_cases(dataset["cases"])
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="requires exhaustive SET_EQUALS truth labels"):
        run_expert_benchmark(repo_root, protocol_path)


def test_expert_benchmark_rejects_degenerate_binary_truth(tmp_path: Path) -> None:
    repo_root, protocol_path, dataset, observations, audit, protocol = _write_bundle(tmp_path)
    for case in dataset["cases"]:
        if "finding" in case["tags"] and case["case_id"] != "risk-ambiguous":
            case["expectations"][0]["expected"] = "NO_RISK"
    audit["cases"] = _audit_cases(dataset["cases"])
    _rewrite_bundle(protocol_path, dataset, observations, audit, protocol)

    with pytest.raises(ExpertBenchmarkError, match="requires at least one expert-positive and one expert-negative"):
        run_expert_benchmark(repo_root, protocol_path)
