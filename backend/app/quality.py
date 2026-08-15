from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from .benchmark import evaluate_benchmark_files
from .legal.importer import import_manifest
from .legal.retrieval import build_retrieval_index, retrieve_legal_evidence
from .legal.retrieval_models import RetrievalRequest
from .quality_models import (
    BinaryClassificationMetrics,
    GateOperator,
    QualityDiagnostic,
    QualityGateProfile,
    QualityGateResult,
    QualityMetric,
    QualityRunReport,
    RankingMetrics,
    SetExtractionMetrics,
)


class QualityError(RuntimeError):
    pass


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def compute_binary_classification_metrics(
    expected_positive: Iterable[bool],
    observed_positive: Iterable[bool],
) -> BinaryClassificationMetrics:
    expected = list(expected_positive)
    observed = list(observed_positive)
    if len(expected) != len(observed):
        raise QualityError("Binary metric inputs must have the same length.")

    tp = fp = fn = tn = 0
    for expected_value, observed_value in zip(expected, observed, strict=True):
        if expected_value and observed_value:
            tp += 1
        elif not expected_value and observed_value:
            fp += 1
        elif expected_value and not observed_value:
            fn += 1
        else:
            tn += 1

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    return BinaryClassificationMetrics(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def compute_set_extraction_metrics(
    expected_sets: Iterable[set[str]],
    observed_sets: Iterable[set[str]],
) -> SetExtractionMetrics:
    expected = list(expected_sets)
    observed = list(observed_sets)
    if len(expected) != len(observed):
        raise QualityError("Set metric inputs must have the same length.")

    tp = fp = fn = 0
    for expected_values, observed_values in zip(expected, observed, strict=True):
        tp += len(expected_values & observed_values)
        fp += len(observed_values - expected_values)
        fn += len(expected_values - observed_values)

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    return SetExtractionMetrics(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def load_quality_gate_profile(path: Path) -> QualityGateProfile:
    try:
        return QualityGateProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise QualityError(f"Invalid quality gate profile {path}: {exc}") from exc


def _benchmark_smoke_metrics(repo_root: Path) -> tuple[list[QualityMetric], list[QualityDiagnostic]]:
    dataset_path = repo_root / "benchmarks" / "public" / "stage11a_schema_smoke.dataset.json"
    observations_path = repo_root / "benchmarks" / "public" / "stage11a_schema_smoke.observations.json"
    report = evaluate_benchmark_files(dataset_path, observations_path)

    passed_cases = sum(1 for result in report.case_results if result.passed)
    assertions = [assertion for result in report.case_results for assertion in result.assertions]
    passed_assertions = sum(1 for assertion in assertions if assertion.passed)

    metrics = [
        QualityMetric(
            key="benchmark.schema_smoke.case_pass_rate",
            label="Stage 11A schema-smoke case pass rate",
            value=_safe_ratio(passed_cases, report.case_count),
            numerator=passed_cases,
            denominator=report.case_count,
            dataset_id=report.dataset_id,
            dataset_version=report.dataset_version,
            scope="Harness-integrity smoke only; not a legal/OCR/model accuracy claim.",
        ),
        QualityMetric(
            key="benchmark.schema_smoke.assertion_pass_rate",
            label="Stage 11A schema-smoke assertion pass rate",
            value=_safe_ratio(passed_assertions, len(assertions)),
            numerator=passed_assertions,
            denominator=len(assertions),
            dataset_id=report.dataset_id,
            dataset_version=report.dataset_version,
            scope="Harness-integrity smoke only; not a product-quality claim.",
        ),
        QualityMetric(
            key="benchmark.schema_smoke.task_coverage_count",
            label="Stage 11A represented task families",
            value=float(len(report.task_summaries)),
            numerator=len(report.task_summaries),
            denominator=9,
            dataset_id=report.dataset_id,
            dataset_version=report.dataset_version,
            scope="Count of benchmark task families represented by the public schema smoke.",
        ),
    ]

    diagnostics: list[QualityDiagnostic] = []
    for result in report.case_results:
        for assertion in result.assertions:
            if assertion.passed:
                continue
            diagnostics.append(
                QualityDiagnostic(
                    layer=result.task_type.value,
                    case_id=result.case_id,
                    category=assertion.reason,
                    message=f"Benchmark assertion {assertion.assertion_id} failed at {assertion.pointer}.",
                    expected=assertion.expected,
                    observed=assertion.observed,
                )
            )
        for reason in result.failure_reasons:
            if result.assertions:
                continue
            diagnostics.append(
                QualityDiagnostic(
                    layer=result.task_type.value,
                    case_id=result.case_id,
                    category=reason.split(":", 1)[0],
                    message=reason,
                )
            )
    return metrics, diagnostics


def _public_retrieval_metrics(
    repo_root: Path,
    work_dir: Path,
) -> tuple[list[QualityMetric], RankingMetrics, list[QualityDiagnostic]]:
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    benchmark_path = repo_root / "legal_data" / "fixtures" / "retrieval_benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))

    legal_db = work_dir / "legal.db"
    retrieval_db = work_dir / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True)
    build_retrieval_index(legal_db, retrieval_db)

    hits = 0
    reciprocal_rank_sum = 0.0
    exact_case_count = 0
    exact_hit_count = 0
    diagnostics: list[QualityDiagnostic] = []

    for case in benchmark["cases"]:
        response = retrieve_legal_evidence(
            legal_db,
            retrieval_db,
            RetrievalRequest(
                query=case["query"],
                as_of=date.fromisoformat(case["as_of"]),
                top_k=case["top_k"],
                authority_id_hint=case.get("authority_id_hint"),
                article_token_hint=case.get("article_token_hint"),
                use_semantic=False,
            ),
        )
        returned = [candidate.legal_evidence_id for candidate in response.candidates]
        expected_ids = set(case["expected_evidence_ids"])
        first_rank = next(
            (rank for rank, evidence_id in enumerate(returned, start=1) if evidence_id in expected_ids),
            None,
        )
        if first_rank is None:
            diagnostics.append(
                QualityDiagnostic(
                    layer="LEGAL_RETRIEVAL",
                    case_id=case["case_id"],
                    category="EXPECTED_EVIDENCE_MISSED",
                    message=f"Expected Legal Evidence was not returned within top-{case['top_k']}.",
                    expected=case["expected_evidence_ids"],
                    observed=returned,
                )
            )
        else:
            hits += 1
            reciprocal_rank_sum += 1.0 / first_rank

        if case.get("article_token_hint"):
            exact_case_count += 1
            exact_match = next(
                (
                    candidate
                    for candidate in response.candidates
                    if candidate.legal_evidence_id in expected_ids and candidate.exact_hit
                ),
                None,
            )
            if exact_match is not None and response.candidates and response.candidates[0] == exact_match:
                exact_hit_count += 1
            else:
                diagnostics.append(
                    QualityDiagnostic(
                        layer="LEGAL_RETRIEVAL",
                        case_id=case["case_id"],
                        category="EXACT_CITATION_NOT_PINNED_FIRST",
                        message="Explicit article citation did not resolve to the expected exact candidate at rank 1.",
                        expected=case["expected_evidence_ids"],
                        observed=returned[:1],
                    )
                )

    case_count = len(benchmark["cases"])
    ranking = RankingMetrics(
        case_count=case_count,
        hit_count=hits,
        recall_at_k=_safe_ratio(hits, case_count),
        mrr=_safe_ratio(reciprocal_rank_sum, case_count),
        exact_case_count=exact_case_count,
        exact_hit_count=exact_hit_count,
        exact_citation_hit_rate=_safe_ratio(exact_hit_count, exact_case_count),
    )
    dataset_id = "stage7-public-retrieval-benchmark"
    dataset_version = benchmark["benchmark_version"]
    metrics = [
        QualityMetric(
            key="retrieval.public.recall_at_5",
            label="Public retrieval Recall@5",
            value=ranking.recall_at_k,
            numerator=ranking.hit_count,
            denominator=ranking.case_count,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            scope="10-case checked-in CURATED_EXCERPT retrieval regression benchmark only.",
        ),
        QualityMetric(
            key="retrieval.public.mrr",
            label="Public retrieval mean reciprocal rank",
            value=ranking.mrr,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            scope="10-case checked-in CURATED_EXCERPT retrieval regression benchmark only.",
        ),
        QualityMetric(
            key="retrieval.public.exact_citation_hit_rate",
            label="Explicit citation exact-hit rate",
            value=ranking.exact_citation_hit_rate,
            numerator=ranking.exact_hit_count,
            denominator=ranking.exact_case_count,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            scope="Only cases in the named benchmark containing an explicit article token hint.",
        ),
    ]
    return metrics, ranking, diagnostics


def _gate_passes(operator: GateOperator, observed: float, threshold: float) -> bool:
    if operator == GateOperator.GTE:
        return observed >= threshold
    if operator == GateOperator.LTE:
        return observed <= threshold
    if operator == GateOperator.EQ:
        return math.isclose(observed, threshold, rel_tol=0.0, abs_tol=1e-12)
    return False


def evaluate_quality_gates(
    profile: QualityGateProfile,
    metrics: list[QualityMetric],
) -> list[QualityGateResult]:
    metric_map = {metric.key: metric for metric in metrics}
    results: list[QualityGateResult] = []
    for gate in profile.gates:
        metric = metric_map.get(gate.metric_key)
        if metric is None:
            results.append(
                QualityGateResult(
                    gate_id=gate.gate_id,
                    metric_key=gate.metric_key,
                    operator=gate.operator,
                    threshold=gate.threshold,
                    observed=None,
                    passed=False,
                    reason="METRIC_MISSING",
                )
            )
            continue
        passed = _gate_passes(gate.operator, metric.value, gate.threshold)
        results.append(
            QualityGateResult(
                gate_id=gate.gate_id,
                metric_key=gate.metric_key,
                operator=gate.operator,
                threshold=gate.threshold,
                observed=metric.value,
                passed=passed,
                reason="PASS" if passed else "THRESHOLD_NOT_MET",
            )
        )
    return results


def run_public_quality_profile(
    repo_root: Path,
    work_dir: Path,
    profile: QualityGateProfile,
) -> QualityRunReport:
    work_dir.mkdir(parents=True, exist_ok=True)
    smoke_metrics, smoke_diagnostics = _benchmark_smoke_metrics(repo_root)
    retrieval_metrics, _ranking, retrieval_diagnostics = _public_retrieval_metrics(repo_root, work_dir)
    metrics = smoke_metrics + retrieval_metrics
    gates = evaluate_quality_gates(profile, metrics)
    diagnostics = smoke_diagnostics + retrieval_diagnostics

    return QualityRunReport(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        all_gates_passed=all(gate.passed for gate in gates),
        metrics=metrics,
        gates=gates,
        diagnostics=diagnostics,
        warnings=[
            "Public quality metrics are scoped regression evidence, not a general legal-accuracy claim.",
            "No paid DeepSeek/Kimi provider is called by this quality runner.",
        ],
    )
