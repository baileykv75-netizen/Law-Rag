from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .benchmark import load_benchmark_dataset, load_benchmark_observations
from .benchmark_models import BenchmarkCase, BenchmarkDataClass, ComparisonMode
from .expert_benchmark_models import (
    EXPERT_BENCHMARK_EVALUATOR_VERSION,
    ExpertBenchmarkProtocol,
    ExpertBenchmarkRunReport,
    ExpertCaseLabelAudit,
    ExpertLabelAuditArtifact,
    ExpertLabelQualitySummary,
    ExpertLabelStatus,
    ExpertMetricDefinition,
    ExpertMetricResult,
    ExpertMetricType,
)
from .quality import compute_binary_classification_metrics, compute_set_extraction_metrics


class ExpertBenchmarkError(RuntimeError):
    pass


_MISSING = object()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ExpertBenchmarkError(f"Could not hash expert benchmark input {path}: {exc}") from exc
    return digest.hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def expert_case_label_fingerprint(case: BenchmarkCase) -> str:
    expectations = sorted(case.expectations, key=lambda item: item.assertion_id)
    payload = {
        "case_id": case.case_id,
        "case_version": case.case_version,
        "expectations": [
            {
                "assertion_id": item.assertion_id,
                "pointer": item.pointer,
                "comparison": item.comparison.value,
                "expected": item.expected,
                "tolerance": item.tolerance,
            }
            for item in expectations
        ],
    }
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _private_path_class(path: Path, repo_root: Path) -> str:
    private_root = (repo_root / "benchmark_private").resolve()
    if _is_within(path, private_root):
        return "PRIVATE"
    if _is_within(path, repo_root):
        return "TRACKED_REPOSITORY"
    return "PRIVATE"


def _require_private_file(path: Path, *, repo_root: Path, label: str) -> None:
    if _private_path_class(path, repo_root) != "PRIVATE":
        raise ExpertBenchmarkError(
            f"{label} must remain external or under ignored benchmark_private/; tracked repository paths are forbidden."
        )
    if not path.is_file():
        raise ExpertBenchmarkError(f"{label} does not exist or is not a file: {path}")


def _resolve_private_reference(reference: str, *, protocol_path: Path) -> Path:
    raw = Path(reference)
    return raw.resolve() if raw.is_absolute() else (protocol_path.parent / raw).resolve()


def load_expert_benchmark_protocol(path: Path) -> ExpertBenchmarkProtocol:
    try:
        return ExpertBenchmarkProtocol.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ExpertBenchmarkError(f"Invalid expert benchmark protocol {path}: {exc}") from exc


def load_expert_label_audit(path: Path) -> ExpertLabelAuditArtifact:
    try:
        return ExpertLabelAuditArtifact.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ExpertBenchmarkError(f"Invalid expert label audit {path}: {exc}") from exc


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


def _validate_private_dataset(dataset) -> None:
    non_private = [
        case.case_id
        for case in dataset.cases
        if case.provenance.data_class != BenchmarkDataClass.PRIVATE_EXTERNAL
    ]
    if non_private:
        raise ExpertBenchmarkError(
            "Every private expert benchmark case must declare PRIVATE_EXTERNAL provenance."
        )


def _validate_identity_and_coverage(protocol, dataset, observations, audit) -> None:
    expected_identity = (protocol.dataset_id, protocol.dataset_version)
    if (dataset.dataset_id, dataset.dataset_version) != expected_identity:
        raise ExpertBenchmarkError("Expert protocol dataset identity/version does not match BenchmarkDataset.")
    if (observations.dataset_id, observations.dataset_version) != expected_identity:
        raise ExpertBenchmarkError("Expert protocol dataset identity/version does not match ObservationSet.")
    if (audit.dataset_id, audit.dataset_version) != expected_identity:
        raise ExpertBenchmarkError("Expert protocol dataset identity/version does not match label audit.")
    if (audit.protocol_id, audit.protocol_version) != (protocol.protocol_id, protocol.protocol_version):
        raise ExpertBenchmarkError("Expert label audit protocol identity/version does not match protocol.")

    dataset_map = {case.case_id: case for case in dataset.cases}
    observation_map = {item.case_id: item for item in observations.observations}
    audit_map = {item.case_id: item for item in audit.cases}
    expected_ids = set(dataset_map)
    if set(observation_map) != expected_ids:
        raise ExpertBenchmarkError(
            "Private expert ObservationSet must cover exactly the BenchmarkDataset case IDs; selective omission is forbidden."
        )
    if set(audit_map) != expected_ids:
        raise ExpertBenchmarkError(
            "Expert label audit must cover exactly the BenchmarkDataset case IDs; selective label auditing is forbidden."
        )

    for case_id, case in dataset_map.items():
        observation = observation_map[case_id]
        audited = audit_map[case_id]
        if observation.case_version != case.case_version:
            raise ExpertBenchmarkError(f"Observation case_version mismatch for private case {case_id}.")
        if audited.case_version != case.case_version:
            raise ExpertBenchmarkError(f"Label-audit case_version mismatch for private case {case_id}.")
        if audited.reviewer_count < protocol.minimum_reviewer_count:
            raise ExpertBenchmarkError(
                f"Private case {case_id} has fewer expert reviewers than protocol minimum."
            )
        if audited.label_fingerprint != expert_case_label_fingerprint(case):
            raise ExpertBenchmarkError(
                f"Expert label fingerprint is stale or does not match current expected labels for private case {case_id}."
            )


def _case_selected(case: BenchmarkCase, metric: ExpertMetricDefinition) -> bool:
    if metric.task_types and case.task_type not in metric.task_types:
        return False
    tags = set(case.tags)
    return all(tag in tags for tag in metric.include_tags_all)


def _expectation_for_metric(case: BenchmarkCase, metric: ExpertMetricDefinition):
    matches = [item for item in case.expectations if item.assertion_id == metric.assertion_id]
    if len(matches) != 1:
        raise ExpertBenchmarkError(
            f"Metric {metric.metric_id} requires exactly one assertion_id={metric.assertion_id} in each selected private case."
        )
    return matches[0]


def _binary_metric(
    metric: ExpertMetricDefinition,
    selected: list[tuple[BenchmarkCase, Any, ExpertCaseLabelAudit]],
) -> ExpertMetricResult:
    positive = {_stable_json(value) for value in metric.positive_values}
    negative = {_stable_json(value) for value in metric.negative_values}
    expected_positive: list[bool] = []
    observed_positive: list[bool] = []
    ambiguous_count = 0

    for case, observation, audited in selected:
        if audited.status == ExpertLabelStatus.AMBIGUOUS:
            ambiguous_count += 1
            continue
        expectation = _expectation_for_metric(case, metric)
        if expectation.comparison != ComparisonMode.EXACT:
            raise ExpertBenchmarkError(
                f"Binary expert metric {metric.metric_id} requires EXACT benchmark expectations."
            )
        observed = _resolve_pointer(observation.observed, expectation.pointer)
        if observed is _MISSING:
            raise ExpertBenchmarkError(
                f"Binary expert metric {metric.metric_id} observed pointer is missing for private case {case.case_id}."
            )
        expected_key = _stable_json(expectation.expected)
        observed_key = _stable_json(observed)
        allowed = positive | negative
        if expected_key not in allowed or observed_key not in allowed:
            raise ExpertBenchmarkError(
                f"Binary expert metric {metric.metric_id} encountered a value outside declared positive/negative classes."
            )
        expected_positive.append(expected_key in positive)
        observed_positive.append(observed_key in positive)

    if not expected_positive:
        raise ExpertBenchmarkError(f"Binary expert metric {metric.metric_id} has no usable expert-labeled cases.")
    if all(expected_positive) or not any(expected_positive):
        raise ExpertBenchmarkError(
            f"Binary expert metric {metric.metric_id} requires at least one expert-positive and one expert-negative usable case."
        )
    result = compute_binary_classification_metrics(expected_positive, observed_positive)
    return ExpertMetricResult(
        metric_id=metric.metric_id,
        label=metric.label,
        metric_type=metric.metric_type,
        scope=metric.scope,
        selected_case_count=len(selected),
        usable_case_count=len(expected_positive),
        ambiguous_case_count=ambiguous_count,
        true_positive=result.true_positive,
        false_positive=result.false_positive,
        false_negative=result.false_negative,
        true_negative=result.true_negative,
        precision=result.precision,
        recall=result.recall,
        f1=result.f1,
    )


def _set_metric(
    metric: ExpertMetricDefinition,
    selected: list[tuple[BenchmarkCase, Any, ExpertCaseLabelAudit]],
) -> ExpertMetricResult:
    expected_sets: list[set[str]] = []
    observed_sets: list[set[str]] = []
    ambiguous_count = 0

    for case, observation, audited in selected:
        if audited.status == ExpertLabelStatus.AMBIGUOUS:
            ambiguous_count += 1
            continue
        expectation = _expectation_for_metric(case, metric)
        if expectation.comparison != ComparisonMode.SET_EQUALS:
            raise ExpertBenchmarkError(
                f"Set-extraction expert metric {metric.metric_id} requires exhaustive SET_EQUALS truth labels."
            )
        observed = _resolve_pointer(observation.observed, expectation.pointer)
        if observed is _MISSING:
            raise ExpertBenchmarkError(
                f"Set-extraction expert metric {metric.metric_id} observed pointer is missing for private case {case.case_id}."
            )
        if not isinstance(expectation.expected, list) or not isinstance(observed, list):
            raise ExpertBenchmarkError(
                f"Set-extraction expert metric {metric.metric_id} requires list expected/observed values."
            )
        expected_sets.append({_stable_json(value) for value in expectation.expected})
        observed_sets.append({_stable_json(value) for value in observed})

    if not expected_sets:
        raise ExpertBenchmarkError(f"Set-extraction expert metric {metric.metric_id} has no usable cases.")
    if not set().union(*expected_sets):
        raise ExpertBenchmarkError(
            f"Set-extraction expert metric {metric.metric_id} requires at least one expert-labeled expected item."
        )
    result = compute_set_extraction_metrics(expected_sets, observed_sets)
    return ExpertMetricResult(
        metric_id=metric.metric_id,
        label=metric.label,
        metric_type=metric.metric_type,
        scope=metric.scope,
        selected_case_count=len(selected),
        usable_case_count=len(expected_sets),
        ambiguous_case_count=ambiguous_count,
        true_positive=result.true_positive,
        false_positive=result.false_positive,
        false_negative=result.false_negative,
        true_negative=None,
        precision=result.precision,
        recall=result.recall,
        f1=result.f1,
    )


def run_expert_benchmark(
    repo_root: Path,
    protocol_path: Path,
) -> ExpertBenchmarkRunReport:
    repo_root = repo_root.resolve()
    protocol_path = protocol_path.resolve()
    _require_private_file(protocol_path, repo_root=repo_root, label="Expert benchmark protocol")
    protocol = load_expert_benchmark_protocol(protocol_path)

    dataset_path = _resolve_private_reference(protocol.dataset_path, protocol_path=protocol_path)
    observations_path = _resolve_private_reference(protocol.observations_path, protocol_path=protocol_path)
    audit_path = _resolve_private_reference(protocol.label_audit_path, protocol_path=protocol_path)
    for label, path in (
        ("Expert BenchmarkDataset", dataset_path),
        ("Expert ObservationSet", observations_path),
        ("Expert label audit", audit_path),
    ):
        _require_private_file(path, repo_root=repo_root, label=label)

    try:
        dataset = load_benchmark_dataset(dataset_path)
        observations = load_benchmark_observations(observations_path)
    except RuntimeError as exc:
        raise ExpertBenchmarkError(str(exc)) from exc
    audit = load_expert_label_audit(audit_path)
    _validate_private_dataset(dataset)
    _validate_identity_and_coverage(protocol, dataset, observations, audit)

    observation_map = {item.case_id: item for item in observations.observations}
    audit_map = {item.case_id: item for item in audit.cases}
    metrics: list[ExpertMetricResult] = []
    for metric in protocol.metrics:
        selected = [
            (case, observation_map[case.case_id], audit_map[case.case_id])
            for case in dataset.cases
            if _case_selected(case, metric)
        ]
        if not selected:
            raise ExpertBenchmarkError(
                f"Expert metric {metric.metric_id} selects zero cases; metric scope/labels must be explicit."
            )
        if metric.metric_type == ExpertMetricType.BINARY_CLASSIFICATION:
            metrics.append(_binary_metric(metric, selected))
        elif metric.metric_type == ExpertMetricType.SET_EXTRACTION:
            metrics.append(_set_metric(metric, selected))
        else:
            raise ExpertBenchmarkError(f"Unsupported expert metric type: {metric.metric_type}")

    statuses = [item.status for item in audit.cases]
    reviewer_counts = [item.reviewer_count for item in audit.cases]
    agreed = sum(1 for status in statuses if status == ExpertLabelStatus.AGREED)
    adjudicated = sum(1 for status in statuses if status == ExpertLabelStatus.ADJUDICATED)
    ambiguous = sum(1 for status in statuses if status == ExpertLabelStatus.AMBIGUOUS)

    return ExpertBenchmarkRunReport(
        evaluator_version=EXPERT_BENCHMARK_EVALUATOR_VERSION,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        label_quality=ExpertLabelQualitySummary(
            total_case_count=len(dataset.cases),
            agreed_case_count=agreed,
            adjudicated_case_count=adjudicated,
            ambiguous_case_count=ambiguous,
            usable_case_count=agreed + adjudicated,
            minimum_reviewer_count_required=protocol.minimum_reviewer_count,
            minimum_reviewer_count_observed=min(reviewer_counts) if reviewer_counts else 0,
        ),
        metrics=metrics,
        source_fingerprints={
            "protocol_sha256": _file_sha256(protocol_path),
            "dataset_sha256": _file_sha256(dataset_path),
            "observations_sha256": _file_sha256(observations_path),
            "label_audit_sha256": _file_sha256(audit_path),
        },
        warnings=[
            "Expert benchmark metrics are valid only for the exact private dataset/protocol versions and label audit represented by these fingerprints.",
            "AMBIGUOUS expert cases remain visible in denominator-quality counts and are excluded from professional performance metrics rather than silently relabeled.",
            "This runner defines no release threshold and no cross-task legal_accuracy/overall_accuracy score.",
            "Real-provider UAT provenance/execution is a separate Stage 16.4 evidence class.",
        ],
    )
