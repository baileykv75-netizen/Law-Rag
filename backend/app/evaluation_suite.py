from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import ValidationError

from .benchmark import BenchmarkError, evaluate_benchmark, load_benchmark_dataset, load_benchmark_observations
from .benchmark_models import BENCHMARK_EVALUATOR_VERSION, BenchmarkDataClass, BenchmarkObservationSet
from .evaluation_suite_models import (
    EVALUATION_SUITE_EVALUATOR_VERSION,
    EvaluationProducerSummary,
    EvaluationSuiteClass,
    EvaluationSuiteEntry,
    EvaluationSuiteEntryKind,
    EvaluationSuiteEntryResult,
    EvaluationSuiteManifest,
    EvaluationSuiteRunReport,
)
from .public_regression import PublicRegressionError, run_public_regression_profile
from .quality import QualityError, load_quality_gate_profile, run_public_quality_profile
from .quality_models import QUALITY_EVALUATOR_VERSION
from .uat_capture import UATCaptureError, load_issue_v1_uat_observation
from .uat_capture_models import UATCaptureMode, UATChainState, UATProviderStage

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_FAKE_TOKEN_RE = re.compile(r"(^|[-_.])(fake|test|stub|mock|double|dummy)($|[-_.])", re.IGNORECASE)
_REAL_UAT_PROVIDERS = frozenset({"deepseek", "kimi"})
_UAT_STAGE_ARTIFACT = {
    UATProviderStage.PLANNER: "audit-plan.json",
    UATProviderStage.PRIMARY: "issue-primary-audit.json",
    UATProviderStage.SECONDARY: "issue-secondary-review.json",
}


class EvaluationSuiteError(RuntimeError):
    pass


def load_evaluation_suite(path: Path) -> EvaluationSuiteManifest:
    try:
        return EvaluationSuiteManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise EvaluationSuiteError(f"Invalid evaluation suite manifest {path}: {exc}") from exc


def _canonical_model_fingerprint(model: EvaluationSuiteManifest) -> str:
    payload = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise EvaluationSuiteError(f"Could not hash evaluation input {path}: {exc}") from exc
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_class(path: Path, repo_root: Path) -> str:
    public_root = (repo_root / "benchmarks" / "public").resolve()
    private_root = (repo_root / "benchmark_private").resolve()
    if _is_within(path, public_root):
        return "PUBLIC"
    if _is_within(path, private_root):
        return "PRIVATE"
    if _is_within(path, repo_root):
        return "TRACKED_OTHER"
    return "PRIVATE"


def _resolve_reference(reference: str, *, repo_root: Path, suite_path: Path) -> Path:
    raw = Path(reference)
    if raw.is_absolute():
        return raw.resolve()
    suite_location_class = _path_class(suite_path, repo_root)
    base = repo_root if suite_location_class == "PUBLIC" else suite_path.parent
    return (base / raw).resolve()


def _require_file(path: Path, *, label: str) -> None:
    if not path.is_file():
        raise EvaluationSuiteError(f"{label} does not exist or is not a file: {path}")


def _validate_suite_location(manifest: EvaluationSuiteManifest, suite_path: Path, repo_root: Path) -> None:
    location_class = _path_class(suite_path, repo_root)
    if manifest.suite_class == EvaluationSuiteClass.PUBLIC_REGRESSION:
        if location_class != "PUBLIC":
            raise EvaluationSuiteError(
                "PUBLIC_REGRESSION suite manifests must live under checked-in benchmarks/public/."
            )
        return
    if location_class != "PRIVATE":
        raise EvaluationSuiteError(
            f"{manifest.suite_class.value} suite manifests must be external or under ignored benchmark_private/."
        )


def _validate_benchmark_paths(
    suite_class: EvaluationSuiteClass,
    dataset_path: Path,
    observations_path: Path,
    repo_root: Path,
) -> tuple[str, str]:
    dataset_class = _path_class(dataset_path, repo_root)
    observations_class = _path_class(observations_path, repo_root)

    if suite_class == EvaluationSuiteClass.PUBLIC_REGRESSION:
        if dataset_class != "PUBLIC" or observations_class != "PUBLIC":
            raise EvaluationSuiteError(
                "PUBLIC_REGRESSION benchmark dataset and observations must both stay under benchmarks/public/."
            )
    elif suite_class == EvaluationSuiteClass.PRIVATE_EXPERT:
        if dataset_class != "PRIVATE" or observations_class != "PRIVATE":
            raise EvaluationSuiteError(
                "PRIVATE_EXPERT benchmark inputs must be external or under ignored benchmark_private/."
            )
    elif suite_class == EvaluationSuiteClass.REAL_PROVIDER_UAT:
        if dataset_class not in {"PUBLIC", "PRIVATE"}:
            raise EvaluationSuiteError(
                "REAL_PROVIDER_UAT datasets must be public benchmark data or external/ignored private data."
            )
        if observations_class != "PRIVATE":
            raise EvaluationSuiteError(
                "REAL_PROVIDER_UAT observations must be external or under ignored benchmark_private/."
            )
    return dataset_class, observations_class


def _validate_dataset_provenance(
    suite_class: EvaluationSuiteClass,
    dataset_path_class: str,
    dataset,
) -> None:
    data_classes = {case.provenance.data_class for case in dataset.cases}
    if suite_class == EvaluationSuiteClass.PUBLIC_REGRESSION:
        if BenchmarkDataClass.PRIVATE_EXTERNAL in data_classes:
            raise EvaluationSuiteError("PUBLIC_REGRESSION dataset contains PRIVATE_EXTERNAL benchmark cases.")
        return
    if suite_class == EvaluationSuiteClass.PRIVATE_EXPERT:
        if data_classes != {BenchmarkDataClass.PRIVATE_EXTERNAL}:
            raise EvaluationSuiteError(
                "PRIVATE_EXPERT datasets must label every case provenance as PRIVATE_EXTERNAL."
            )
        return
    if suite_class == EvaluationSuiteClass.REAL_PROVIDER_UAT and dataset_path_class == "PUBLIC":
        if BenchmarkDataClass.PRIVATE_EXTERNAL in data_classes:
            raise EvaluationSuiteError(
                "A REAL_PROVIDER_UAT dataset stored under benchmarks/public/ cannot contain PRIVATE_EXTERNAL cases."
            )


def _looks_fake(value: str) -> bool:
    return bool(_FAKE_TOKEN_RE.search(value.strip()))


def _uat_producer_summaries(observations: BenchmarkObservationSet) -> list[EvaluationProducerSummary]:
    if not observations.observations:
        raise EvaluationSuiteError("REAL_PROVIDER_UAT requires at least one real-provider observation.")

    unique: dict[tuple[str, str, str], EvaluationProducerSummary] = {}
    for item in observations.observations:
        producer = item.producer
        producer_id = producer.producer_id.strip()
        provider = (producer.provider or "").strip()
        model = (producer.model or "").strip()
        artifact_fingerprint = (producer.artifact_fingerprint or "").strip()
        if not provider or not model:
            raise EvaluationSuiteError(
                "Every REAL_PROVIDER_UAT observation must record producer.provider and producer.model."
            )
        normalized_provider = provider.lower()
        if normalized_provider not in _REAL_UAT_PROVIDERS:
            raise EvaluationSuiteError(
                "REAL_PROVIDER_UAT provider must be one of the current production providers: deepseek or kimi."
            )
        if _looks_fake(producer_id) or _looks_fake(provider) or _looks_fake(model):
            raise EvaluationSuiteError(
                "Fake producer identities/providers/models cannot be accepted as REAL_PROVIDER_UAT evidence."
            )
        if not _SHA256_RE.fullmatch(artifact_fingerprint):
            raise EvaluationSuiteError(
                "Every REAL_PROVIDER_UAT observation must record a SHA-256 artifact_fingerprint."
            )
        key = (normalized_provider, model, artifact_fingerprint.lower())
        unique[key] = EvaluationProducerSummary(
            provider=normalized_provider,
            model=model,
            artifact_fingerprint=artifact_fingerprint.lower(),
        )
    return [unique[key] for key in sorted(unique)]


def _run_benchmark_entry(
    entry: EvaluationSuiteEntry,
    *,
    suite_class: EvaluationSuiteClass,
    repo_root: Path,
    suite_path: Path,
) -> EvaluationSuiteEntryResult:
    assert entry.dataset_path is not None
    assert entry.observations_path is not None
    dataset_path = _resolve_reference(entry.dataset_path, repo_root=repo_root, suite_path=suite_path)
    observations_path = _resolve_reference(entry.observations_path, repo_root=repo_root, suite_path=suite_path)
    _require_file(dataset_path, label="Benchmark dataset")
    _require_file(observations_path, label="Benchmark observations")
    dataset_path_class, _ = _validate_benchmark_paths(
        suite_class, dataset_path, observations_path, repo_root
    )

    try:
        dataset = load_benchmark_dataset(dataset_path)
        observations = load_benchmark_observations(observations_path)
        _validate_dataset_provenance(suite_class, dataset_path_class, dataset)
        producers = (
            _uat_producer_summaries(observations)
            if suite_class == EvaluationSuiteClass.REAL_PROVIDER_UAT
            else []
        )
        report = evaluate_benchmark(dataset, observations)
    except BenchmarkError as exc:
        raise EvaluationSuiteError(str(exc)) from exc

    passed_count = sum(1 for result in report.case_results if result.passed)
    return EvaluationSuiteEntryResult(
        entry_id=entry.entry_id,
        kind=entry.kind,
        passed=report.all_cases_passed,
        evaluator_version=BENCHMARK_EVALUATOR_VERSION,
        identity_id=report.dataset_id,
        identity_version=report.dataset_version,
        unit_label="cases",
        unit_count=report.case_count,
        passed_count=passed_count,
        failed_count=report.case_count - passed_count,
        source_fingerprints={
            "dataset_sha256": _file_sha256(dataset_path),
            "observations_sha256": _file_sha256(observations_path),
        },
        producers=producers,
        warnings=[
            "Suite summary intentionally omits assertion-level expected/observed payloads; use the underlying benchmark report in its permitted data boundary for diagnostics."
        ],
    )


def _public_quality_source_fingerprints(repo_root: Path, profile_path: Path) -> dict[str, str]:
    sources = {
        "quality_profile_sha256": profile_path,
        "schema_dataset_sha256": repo_root / "benchmarks" / "public" / "stage11a_schema_smoke.dataset.json",
        "schema_observations_sha256": repo_root
        / "benchmarks"
        / "public"
        / "stage11a_schema_smoke.observations.json",
        "legal_seed_manifest_sha256": repo_root / "legal_data" / "seed" / "manifest.json",
        "retrieval_benchmark_sha256": repo_root / "legal_data" / "fixtures" / "retrieval_benchmark.json",
    }
    for label, path in sources.items():
        _require_file(path, label=label)
    return {label: _file_sha256(path) for label, path in sources.items()}


def _run_quality_entry(
    entry: EvaluationSuiteEntry,
    *,
    repo_root: Path,
    suite_path: Path,
    work_dir: Path,
) -> EvaluationSuiteEntryResult:
    assert entry.quality_profile_path is not None
    profile_path = _resolve_reference(entry.quality_profile_path, repo_root=repo_root, suite_path=suite_path)
    _require_file(profile_path, label="Quality profile")
    if _path_class(profile_path, repo_root) != "PUBLIC":
        raise EvaluationSuiteError("PUBLIC_QUALITY_PROFILE input must stay under benchmarks/public/.")
    try:
        profile = load_quality_gate_profile(profile_path)
        report = run_public_quality_profile(repo_root, work_dir, profile)
    except QualityError as exc:
        raise EvaluationSuiteError(str(exc)) from exc

    passed_count = sum(1 for gate in report.gates if gate.passed)
    return EvaluationSuiteEntryResult(
        entry_id=entry.entry_id,
        kind=entry.kind,
        passed=report.all_gates_passed,
        evaluator_version=QUALITY_EVALUATOR_VERSION,
        identity_id=report.profile_id,
        identity_version=report.profile_version,
        unit_label="gates",
        unit_count=len(report.gates),
        passed_count=passed_count,
        failed_count=len(report.gates) - passed_count,
        source_fingerprints=_public_quality_source_fingerprints(repo_root, profile_path),
        warnings=[
            "Public quality gates are scoped deterministic regression evidence and are not a general legal-accuracy claim."
        ],
    )


def _run_public_regression_entry(
    entry: EvaluationSuiteEntry,
    *,
    repo_root: Path,
    suite_path: Path,
    work_dir: Path,
) -> EvaluationSuiteEntryResult:
    assert entry.public_regression_profile_path is not None
    profile_path = _resolve_reference(
        entry.public_regression_profile_path,
        repo_root=repo_root,
        suite_path=suite_path,
    )
    _require_file(profile_path, label="Public regression profile")
    if _path_class(profile_path, repo_root) != "PUBLIC":
        raise EvaluationSuiteError("PUBLIC_REGRESSION_PROFILE input must stay under benchmarks/public/.")
    try:
        report, fingerprints = run_public_regression_profile(repo_root, profile_path, work_dir)
    except PublicRegressionError as exc:
        raise EvaluationSuiteError(str(exc)) from exc

    passed_count = sum(1 for gate in report.gates if gate.passed)
    return EvaluationSuiteEntryResult(
        entry_id=entry.entry_id,
        kind=entry.kind,
        passed=report.all_gates_passed,
        evaluator_version=report.evaluator_version,
        identity_id=report.profile_id,
        identity_version=report.profile_version,
        unit_label="gates",
        unit_count=len(report.gates),
        passed_count=passed_count,
        failed_count=len(report.gates) - passed_count,
        source_fingerprints=fingerprints,
        warnings=[
            "Stage 16 public deterministic regression gates are scoped repository-safe evidence, not professional legal accuracy."
        ],
    )


def _uat_capture_producer_summaries(observation) -> list[EvaluationProducerSummary]:
    artifacts = {item.artifact: item for item in observation.artifacts}
    summaries: dict[tuple[str, str, str], EvaluationProducerSummary] = {}
    stages_seen: set[UATProviderStage] = set()

    for call in observation.provider_calls:
        provider = call.provider.strip().lower()
        model = call.model.strip()
        expected_provider = "kimi" if call.stage == UATProviderStage.SECONDARY else "deepseek"
        if provider != expected_provider:
            raise EvaluationSuiteError(
                f"UAT_CAPTURE expected {expected_provider} for {call.stage.value}, got {call.provider!r}."
            )
        if provider not in _REAL_UAT_PROVIDERS or _looks_fake(provider) or _looks_fake(model):
            raise EvaluationSuiteError("Fake or non-production provider/model identity in UAT_CAPTURE evidence.")
        artifact_name = _UAT_STAGE_ARTIFACT[call.stage]
        artifact = artifacts.get(artifact_name)
        if artifact is None:
            raise EvaluationSuiteError(
                f"UAT_CAPTURE provider stage {call.stage.value} is missing authoritative {artifact_name} provenance."
            )
        fingerprint = artifact.embedded_fingerprint or artifact.file_sha256
        key = (provider, model, fingerprint)
        summaries[key] = EvaluationProducerSummary(
            provider=provider,
            model=model,
            artifact_fingerprint=fingerprint,
        )
        stages_seen.add(call.stage)

    if UATProviderStage.PLANNER not in stages_seen:
        raise EvaluationSuiteError("UAT_CAPTURE must preserve at least one Audit Planner provider call.")
    return [summaries[key] for key in sorted(summaries)]


def _run_uat_capture_entry(
    entry: EvaluationSuiteEntry,
    *,
    repo_root: Path,
    suite_path: Path,
) -> EvaluationSuiteEntryResult:
    assert entry.uat_observation_path is not None
    observation_path = _resolve_reference(
        entry.uat_observation_path,
        repo_root=repo_root,
        suite_path=suite_path,
    )
    _require_file(observation_path, label="UAT capture observation")
    if _path_class(observation_path, repo_root) != "PRIVATE":
        raise EvaluationSuiteError(
            "UAT_CAPTURE observations must remain external or under ignored benchmark_private/."
        )
    try:
        observation = load_issue_v1_uat_observation(observation_path)
    except UATCaptureError as exc:
        raise EvaluationSuiteError(str(exc)) from exc

    if observation.capture_mode != UATCaptureMode.REAL_PROVIDER:
        raise EvaluationSuiteError(
            "UAT_CAPTURE suite entries accept only explicitly captured REAL_PROVIDER observations."
        )
    if observation.architecture != "ISSUE_V1":
        raise EvaluationSuiteError("UAT_CAPTURE currently accepts only architecture=ISSUE_V1.")
    if len(observation.issue_coverage) != observation.audit_plan_issue_count:
        raise EvaluationSuiteError("UAT_CAPTURE Issue coverage count does not reconcile with the AuditPlan count.")
    issue_ids = [item.issue_id for item in observation.issue_coverage]
    if len(issue_ids) != len(set(issue_ids)):
        raise EvaluationSuiteError("UAT_CAPTURE contains duplicate Issue coverage records.")

    if observation.chain_state == UATChainState.COMPLETE:
        if (
            observation.primary_completed_issue_count != observation.audit_plan_issue_count
            or observation.secondary_completed_issue_count != observation.audit_plan_issue_count
            or observation.compared_issue_count != observation.audit_plan_issue_count
        ):
            raise EvaluationSuiteError("A COMPLETE UAT_CAPTURE must reconcile all authoritative Issue counts.")
        if not all(item.primary_result_present and item.secondary_result_present and item.comparison_present for item in observation.issue_coverage):
            raise EvaluationSuiteError("A COMPLETE UAT_CAPTURE must preserve complete Issue result/comparison coverage.")
    elif observation.chain_state == UATChainState.PRIMARY_INTERRUPTED:
        if observation.secondary_completed_issue_count != 0 or observation.compared_issue_count != 0:
            raise EvaluationSuiteError("PRIMARY_INTERRUPTED UAT_CAPTURE cannot contain downstream completion counts.")
    elif observation.chain_state == UATChainState.SECONDARY_INTERRUPTED:
        if observation.primary_completed_issue_count != observation.audit_plan_issue_count:
            raise EvaluationSuiteError("SECONDARY_INTERRUPTED UAT_CAPTURE requires complete primary Issue coverage.")
        if observation.compared_issue_count != 0:
            raise EvaluationSuiteError("SECONDARY_INTERRUPTED UAT_CAPTURE cannot contain final comparisons.")

    producers = _uat_capture_producer_summaries(observation)
    source_fingerprints = {
        "uat_observation_sha256": _file_sha256(observation_path),
        "uat_observation_fingerprint": observation.observation_fingerprint,
    }
    for artifact in observation.artifacts:
        source_fingerprints[f"artifact.{artifact.artifact}.file_sha256"] = artifact.file_sha256
        if artifact.embedded_fingerprint:
            source_fingerprints[
                f"artifact.{artifact.artifact}.embedded_fingerprint"
            ] = artifact.embedded_fingerprint

    complete = observation.chain_state == UATChainState.COMPLETE
    return EvaluationSuiteEntryResult(
        entry_id=entry.entry_id,
        kind=entry.kind,
        passed=complete,
        evaluator_version=observation.capture_version,
        identity_id=observation.architecture,
        identity_version=observation.capture_version,
        unit_label="uat_capture",
        unit_count=1,
        passed_count=1 if complete else 0,
        failed_count=0 if complete else 1,
        source_fingerprints=source_fingerprints,
        producers=producers,
        warnings=[
            f"Captured provider chain state: {observation.chain_state.value}.",
            "UAT_CAPTURE pass means the captured ISSUE_V1 provider chain reached COMPLETE; it is not a professional legal-correctness judgment.",
            "Detailed job, Issue, request and raw-response provenance remains only in the private observation file.",
        ],
    )


def run_evaluation_suite(
    repo_root: Path,
    suite_path: Path,
    work_dir: Path,
) -> EvaluationSuiteRunReport:
    repo_root = repo_root.resolve()
    suite_path = suite_path.resolve()
    work_dir = work_dir.resolve()
    _require_file(suite_path, label="Evaluation suite manifest")
    manifest = load_evaluation_suite(suite_path)
    _validate_suite_location(manifest, suite_path, repo_root)
    work_dir.mkdir(parents=True, exist_ok=True)

    results: list[EvaluationSuiteEntryResult] = []
    for index, entry in enumerate(manifest.entries, start=1):
        if entry.kind == EvaluationSuiteEntryKind.BENCHMARK:
            result = _run_benchmark_entry(
                entry,
                suite_class=manifest.suite_class,
                repo_root=repo_root,
                suite_path=suite_path,
            )
        elif entry.kind == EvaluationSuiteEntryKind.PUBLIC_QUALITY_PROFILE:
            result = _run_quality_entry(
                entry,
                repo_root=repo_root,
                suite_path=suite_path,
                work_dir=work_dir / f"quality-{index}",
            )
        elif entry.kind == EvaluationSuiteEntryKind.PUBLIC_REGRESSION_PROFILE:
            result = _run_public_regression_entry(
                entry,
                repo_root=repo_root,
                suite_path=suite_path,
                work_dir=work_dir / f"regression-{index}",
            )
        elif entry.kind == EvaluationSuiteEntryKind.UAT_CAPTURE:
            if manifest.suite_class != EvaluationSuiteClass.REAL_PROVIDER_UAT:
                raise EvaluationSuiteError("UAT_CAPTURE is valid only in REAL_PROVIDER_UAT suites.")
            result = _run_uat_capture_entry(
                entry,
                repo_root=repo_root,
                suite_path=suite_path,
            )
        else:
            raise EvaluationSuiteError(f"Unsupported evaluation suite entry kind: {entry.kind}")
        results.append(result)

    class_warning = {
        EvaluationSuiteClass.PUBLIC_REGRESSION: (
            "PUBLIC_REGRESSION results are checked-in regression evidence only; they are not a professional legal-accuracy claim."
        ),
        EvaluationSuiteClass.PRIVATE_EXPERT: (
            "PRIVATE_EXPERT labels and detailed diagnostics remain outside tracked Git paths; this suite report is summary-only."
        ),
        EvaluationSuiteClass.REAL_PROVIDER_UAT: (
            "REAL_PROVIDER_UAT evidence is provider/model specific and must not be interpreted as deterministic reproducibility of model behavior or professional correctness."
        ),
    }[manifest.suite_class]

    return EvaluationSuiteRunReport(
        evaluator_version=EVALUATION_SUITE_EVALUATOR_VERSION,
        suite_id=manifest.suite_id,
        suite_version=manifest.suite_version,
        suite_class=manifest.suite_class,
        manifest_fingerprint=_canonical_model_fingerprint(manifest),
        all_entries_passed=all(result.passed for result in results),
        entries=results,
        warnings=[
            class_warning,
            "No cross-task overall_accuracy or legal_accuracy score is produced by the evaluation-suite layer.",
            "The evaluation-suite runner never invokes paid/network DeepSeek or Kimi provider calls.",
        ],
    )
