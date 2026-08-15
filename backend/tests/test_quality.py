from __future__ import annotations

from pathlib import Path

import pytest

from app.quality import (
    QualityError,
    compute_binary_classification_metrics,
    compute_set_extraction_metrics,
    evaluate_quality_gates,
    load_quality_gate_profile,
    run_public_quality_profile,
)
from app.quality_models import GateOperator, QualityGateDefinition, QualityGateProfile, QualityMetric


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_binary_classification_metrics_keep_precision_recall_and_f1_separate() -> None:
    metrics = compute_binary_classification_metrics(
        [True, True, True, False, False],
        [True, False, True, True, False],
    )

    assert metrics.true_positive == 2
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.true_negative == 1
    assert metrics.precision == pytest.approx(2 / 3)
    assert metrics.recall == pytest.approx(2 / 3)
    assert metrics.f1 == pytest.approx(2 / 3)


def test_set_extraction_metrics_are_micro_averaged_over_expected_and_observed_ids() -> None:
    metrics = compute_set_extraction_metrics(
        [{"E-1", "E-2"}, {"E-3"}],
        [{"E-1", "E-X"}, {"E-3"}],
    )

    assert metrics.true_positive == 2
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.precision == pytest.approx(2 / 3)
    assert metrics.recall == pytest.approx(2 / 3)
    assert metrics.f1 == pytest.approx(2 / 3)


def test_metric_helpers_reject_mismatched_case_counts() -> None:
    with pytest.raises(QualityError, match="same length"):
        compute_binary_classification_metrics([True], [True, False])

    with pytest.raises(QualityError, match="same length"):
        compute_set_extraction_metrics([{"E-1"}], [{"E-1"}, {"E-2"}])


def test_quality_gate_fails_loudly_when_metric_is_missing_or_below_threshold() -> None:
    profile = QualityGateProfile(
        profile_id="unit-profile",
        profile_version="1.0.0",
        title="Unit quality profile",
        scope="Synthetic unit test only",
        gates=[
            QualityGateDefinition(
                gate_id="minimum-recall",
                metric_key="audit.synthetic.recall",
                operator=GateOperator.GTE,
                threshold=0.9,
                rationale="Synthetic unit threshold",
            ),
            QualityGateDefinition(
                gate_id="missing-metric",
                metric_key="audit.synthetic.missing",
                operator=GateOperator.EQ,
                threshold=1.0,
                rationale="Missing metrics must fail closed",
            ),
        ],
    )
    metrics = [
        QualityMetric(
            key="audit.synthetic.recall",
            label="Synthetic recall",
            value=0.8,
            numerator=8,
            denominator=10,
            dataset_id="synthetic",
            dataset_version="1.0.0",
            scope="Unit test only",
        )
    ]

    results = evaluate_quality_gates(profile, metrics)

    assert results[0].passed is False
    assert results[0].reason == "THRESHOLD_NOT_MET"
    assert results[1].passed is False
    assert results[1].reason == "METRIC_MISSING"


def test_public_quality_profile_runs_real_local_retrieval_and_passes_named_gates(tmp_path: Path) -> None:
    repo_root = _repo_root()
    profile = load_quality_gate_profile(repo_root / "benchmarks" / "public" / "stage11b_quality_gates.json")

    report = run_public_quality_profile(repo_root, tmp_path / "quality", profile)

    assert report.all_gates_passed is True
    metric_map = {metric.key: metric for metric in report.metrics}
    assert metric_map["benchmark.schema_smoke.task_coverage_count"].value == 9
    assert metric_map["retrieval.public.recall_at_5"].value >= 0.9
    assert metric_map["retrieval.public.mrr"].value >= 0.8
    assert metric_map["retrieval.public.exact_citation_hit_rate"].value == 1.0
    assert all(gate.passed for gate in report.gates)
    assert any("not a general legal-accuracy claim" in warning for warning in report.warnings)


def test_public_quality_profile_metric_scope_names_dataset_version(tmp_path: Path) -> None:
    repo_root = _repo_root()
    profile = load_quality_gate_profile(repo_root / "benchmarks" / "public" / "stage11b_quality_gates.json")
    report = run_public_quality_profile(repo_root, tmp_path / "quality", profile)

    retrieval = next(metric for metric in report.metrics if metric.key == "retrieval.public.recall_at_5")
    assert retrieval.dataset_id == "stage7-public-retrieval-benchmark"
    assert retrieval.dataset_version == "1.0.0"
    assert "10-case" in retrieval.scope
