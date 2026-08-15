from __future__ import annotations

import json
import math
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .benchmark_models import (
    BenchmarkAssertionResult,
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkDataset,
    BenchmarkExpectation,
    BenchmarkObservation,
    BenchmarkObservationSet,
    BenchmarkRunReport,
    BenchmarkTaskSummary,
    BenchmarkTaskType,
    ComparisonMode,
)


class BenchmarkError(RuntimeError):
    pass


_MISSING = object()


def load_benchmark_dataset(path: Path) -> BenchmarkDataset:
    try:
        return BenchmarkDataset.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise BenchmarkError(f"Invalid benchmark dataset {path}: {exc}") from exc


def load_benchmark_observations(path: Path) -> BenchmarkObservationSet:
    try:
        return BenchmarkObservationSet.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise BenchmarkError(f"Invalid benchmark observations {path}: {exc}") from exc


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(payload: Any, pointer: str) -> Any:
    current = payload
    for raw_token in pointer.split("/")[1:]:
        token = _decode_pointer_token(raw_token)
        if isinstance(current, dict):
            if token not in current:
                return _MISSING
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit():
                return _MISSING
            index = int(token)
            if index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _as_stable_set(value: Any) -> set[str] | None:
    if not isinstance(value, list):
        return None
    return {_stable_json(item) for item in value}


def _normalized_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def _compare(expectation: BenchmarkExpectation, observed: Any) -> tuple[bool, str]:
    if observed is _MISSING:
        return False, "OBSERVED_POINTER_MISSING"

    mode = expectation.comparison
    expected = expectation.expected

    if mode == ComparisonMode.EXACT:
        return observed == expected, "MATCH" if observed == expected else "EXACT_MISMATCH"

    if mode == ComparisonMode.ONE_OF:
        passed = any(observed == candidate for candidate in expected)
        return passed, "MATCH" if passed else "NOT_IN_ALLOWED_ALTERNATIVES"

    if mode in {ComparisonMode.SET_EQUALS, ComparisonMode.SET_CONTAINS}:
        expected_set = _as_stable_set(expected)
        observed_set = _as_stable_set(observed)
        if expected_set is None or observed_set is None:
            return False, "SET_COMPARISON_REQUIRES_ARRAYS"
        if mode == ComparisonMode.SET_EQUALS:
            passed = observed_set == expected_set
            return passed, "MATCH" if passed else "SET_MISMATCH"
        passed = expected_set.issubset(observed_set)
        return passed, "MATCH" if passed else "EXPECTED_SET_NOT_CONTAINED"

    if mode == ComparisonMode.NUMERIC_WITHIN:
        if isinstance(expected, bool) or isinstance(observed, bool):
            return False, "NUMERIC_COMPARISON_REQUIRES_NUMBERS"
        if not isinstance(expected, (int, float)) or not isinstance(observed, (int, float)):
            return False, "NUMERIC_COMPARISON_REQUIRES_NUMBERS"
        if not math.isfinite(float(expected)) or not math.isfinite(float(observed)):
            return False, "NUMERIC_COMPARISON_REQUIRES_FINITE_VALUES"
        tolerance = expectation.tolerance or 0.0
        passed = abs(float(observed) - float(expected)) <= tolerance
        return passed, "MATCH" if passed else "OUTSIDE_TOLERANCE"

    if mode == ComparisonMode.NORMALIZED_TEXT_EQUALS:
        expected_text = _normalized_text(expected)
        observed_text = _normalized_text(observed)
        if expected_text is None or observed_text is None:
            return False, "TEXT_COMPARISON_REQUIRES_STRINGS"
        passed = observed_text == expected_text
        return passed, "MATCH" if passed else "NORMALIZED_TEXT_MISMATCH"

    return False, "UNSUPPORTED_COMPARISON_MODE"


def _evaluate_case(case: BenchmarkCase, observation: BenchmarkObservation | None) -> BenchmarkCaseResult:
    if observation is None:
        return BenchmarkCaseResult(
            case_id=case.case_id,
            case_version=case.case_version,
            task_type=case.task_type,
            passed=False,
            failure_reasons=["MISSING_OBSERVATION"],
        )

    if observation.case_version != case.case_version:
        return BenchmarkCaseResult(
            case_id=case.case_id,
            case_version=case.case_version,
            task_type=case.task_type,
            passed=False,
            producer=observation.producer,
            failure_reasons=[
                f"CASE_VERSION_MISMATCH expected={case.case_version} observed={observation.case_version}"
            ],
        )

    assertion_results: list[BenchmarkAssertionResult] = []
    failure_reasons: list[str] = []
    for expectation in case.expectations:
        observed = _resolve_pointer(observation.observed, expectation.pointer)
        passed, reason = _compare(expectation, observed)
        assertion_results.append(
            BenchmarkAssertionResult(
                assertion_id=expectation.assertion_id,
                pointer=expectation.pointer,
                comparison=expectation.comparison,
                passed=passed,
                expected=expectation.expected,
                observed=None if observed is _MISSING else observed,
                reason=reason,
            )
        )
        if not passed:
            failure_reasons.append(f"{expectation.assertion_id}:{reason}")

    return BenchmarkCaseResult(
        case_id=case.case_id,
        case_version=case.case_version,
        task_type=case.task_type,
        passed=not failure_reasons,
        producer=observation.producer,
        assertions=assertion_results,
        failure_reasons=failure_reasons,
    )


def evaluate_benchmark(
    dataset: BenchmarkDataset,
    observations: BenchmarkObservationSet,
) -> BenchmarkRunReport:
    if observations.dataset_id != dataset.dataset_id or observations.dataset_version != dataset.dataset_version:
        raise BenchmarkError(
            "Observation set dataset identity/version does not match benchmark dataset: "
            f"expected {dataset.dataset_id}@{dataset.dataset_version}, "
            f"observed {observations.dataset_id}@{observations.dataset_version}."
        )

    observation_map = {item.case_id: item for item in observations.observations}
    case_results = [_evaluate_case(case, observation_map.get(case.case_id)) for case in dataset.cases]

    dataset_case_ids = {case.case_id for case in dataset.cases}
    extra_observation_ids = sorted(set(observation_map) - dataset_case_ids)
    warnings = [f"UNUSED_OBSERVATION:{case_id}" for case_id in extra_observation_ids]

    summaries: list[BenchmarkTaskSummary] = []
    for task_type in BenchmarkTaskType:
        task_results = [result for result in case_results if result.task_type == task_type]
        if not task_results:
            continue
        passed = sum(1 for result in task_results if result.passed)
        summaries.append(
            BenchmarkTaskSummary(
                task_type=task_type,
                case_count=len(task_results),
                passed=passed,
                failed=len(task_results) - passed,
            )
        )

    return BenchmarkRunReport(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        case_count=len(case_results),
        all_cases_passed=all(result.passed for result in case_results),
        task_summaries=summaries,
        case_results=case_results,
        warnings=warnings,
    )


def evaluate_benchmark_files(dataset_path: Path, observations_path: Path) -> BenchmarkRunReport:
    return evaluate_benchmark(
        load_benchmark_dataset(dataset_path),
        load_benchmark_observations(observations_path),
    )
