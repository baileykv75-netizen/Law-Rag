from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydantic import ValidationError

from .evaluation_suite import EvaluationSuiteError, run_evaluation_suite
from .evaluation_suite_models import EvaluationSuiteClass, EvaluationSuiteEntryKind
from .expert_benchmark_models import ExpertBenchmarkRunReport
from .release_evidence_models import (
    RELEASE_EVIDENCE_EVALUATOR_VERSION,
    ReleaseEvidenceClass,
    ReleaseEvidenceItem,
    ReleaseEvidenceStatus,
    Stage16ReleaseEvidenceMatrix,
)

_EXPECTED_PUBLIC_SUITE_ID = "law-rag-stage16-public-evaluation"
_EXPECTED_PUBLIC_SUITE_VERSION = "1.1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReleaseEvidenceError(RuntimeError):
    pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise ReleaseEvidenceError(f"Could not hash evidence file {path}: {exc}") from exc
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_path(path: Path, *, repo_root: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _require_file(path: Path, *, label: str) -> None:
    if not path.is_file():
        raise ReleaseEvidenceError(f"{label} does not exist or is not a file: {path}")


def _require_private_or_external(path: Path, *, repo_root: Path, label: str) -> None:
    private_root = (repo_root / "benchmark_private").resolve()
    if _is_within(path, private_root):
        return
    if _is_within(path, repo_root):
        raise ReleaseEvidenceError(
            f"{label} must remain external or under ignored benchmark_private/; tracked repository paths are forbidden."
        )


def _public_regression_item(repo_root: Path, suite_path: Path, work_dir: Path) -> ReleaseEvidenceItem:
    try:
        report = run_evaluation_suite(repo_root, suite_path, work_dir / "public-regression")
    except EvaluationSuiteError as exc:
        raise ReleaseEvidenceError(str(exc)) from exc

    if report.suite_class != EvaluationSuiteClass.PUBLIC_REGRESSION:
        raise ReleaseEvidenceError("Stage 16.5 public evidence must use a PUBLIC_REGRESSION suite.")
    if report.suite_id != _EXPECTED_PUBLIC_SUITE_ID or report.suite_version != _EXPECTED_PUBLIC_SUITE_VERSION:
        raise ReleaseEvidenceError(
            "Stage 16.5 public evidence must use the pinned Stage 16b evaluation suite "
            f"{_EXPECTED_PUBLIC_SUITE_ID}@{_EXPECTED_PUBLIC_SUITE_VERSION}."
        )

    return ReleaseEvidenceItem(
        evidence_id="stage16-public-regression",
        evidence_class=ReleaseEvidenceClass.PUBLIC_REGRESSION,
        status=ReleaseEvidenceStatus.PASS if report.all_entries_passed else ReleaseEvidenceStatus.FAIL,
        source_fingerprint=_file_sha256(suite_path),
        summary=(
            "Pinned Stage 16 public deterministic evaluation suite passed."
            if report.all_entries_passed
            else "Pinned Stage 16 public deterministic evaluation suite contains failed entries."
        ),
        warnings=[
            "Public deterministic regression is repository-safe engineering evidence, not professional legal correctness."
        ],
    )


def _private_expert_item(repo_root: Path, report_path: Path | None) -> ReleaseEvidenceItem:
    if report_path is None:
        return ReleaseEvidenceItem(
            evidence_id="stage16-private-expert",
            evidence_class=ReleaseEvidenceClass.PRIVATE_EXPERT,
            status=ReleaseEvidenceStatus.PENDING,
            summary="No real private expert benchmark report was supplied to this evidence-matrix run.",
            warnings=[
                "Stage 16.3 evaluator mechanics are validated, but synthetic fixtures are not professional expert evidence."
            ],
        )

    path = _resolve_path(report_path, repo_root=repo_root)
    _require_file(path, label="Private expert benchmark report")
    _require_private_or_external(path, repo_root=repo_root, label="Private expert benchmark report")
    try:
        report = ExpertBenchmarkRunReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ReleaseEvidenceError(f"Invalid private expert benchmark report {path}: {exc}") from exc

    invalid_fingerprints = [
        key for key, value in report.source_fingerprints.items() if not _SHA256_RE.fullmatch(value)
    ]
    if invalid_fingerprints:
        raise ReleaseEvidenceError(
            "Private expert benchmark report contains invalid source fingerprints: "
            + ", ".join(sorted(invalid_fingerprints))
        )

    usable = report.label_quality.usable_case_count > 0 and bool(report.metrics)
    usable = usable and all(metric.usable_case_count > 0 for metric in report.metrics)
    return ReleaseEvidenceItem(
        evidence_id="stage16-private-expert",
        evidence_class=ReleaseEvidenceClass.PRIVATE_EXPERT,
        status=ReleaseEvidenceStatus.PRESENT if usable else ReleaseEvidenceStatus.FAIL,
        source_fingerprint=_file_sha256(path),
        summary=(
            "A sanitized real private expert benchmark report is present with usable scoped metrics."
            if usable
            else "A private expert benchmark report is present but does not contain usable scoped expert evidence."
        ),
        warnings=[
            "Presence of expert evidence does not create an unstated release threshold or cross-task legal-accuracy score."
        ],
    )


def _real_provider_uat_item(
    repo_root: Path,
    suite_path: Path | None,
    work_dir: Path,
) -> ReleaseEvidenceItem:
    if suite_path is None:
        return ReleaseEvidenceItem(
            evidence_id="stage16-real-provider-uat",
            evidence_class=ReleaseEvidenceClass.REAL_PROVIDER_UAT,
            status=ReleaseEvidenceStatus.PENDING,
            summary="No real-provider ISSUE_V1 UAT suite was supplied to this evidence-matrix run.",
            warnings=[
                "Provider-free UAT capture mechanics are validated; actual paid/network UAT remains a separate explicit action."
            ],
        )

    path = _resolve_path(suite_path, repo_root=repo_root)
    _require_file(path, label="Real-provider UAT suite")
    _require_private_or_external(path, repo_root=repo_root, label="Real-provider UAT suite")
    try:
        report = run_evaluation_suite(repo_root, path, work_dir / "real-provider-uat")
    except EvaluationSuiteError as exc:
        raise ReleaseEvidenceError(str(exc)) from exc

    if report.suite_class != EvaluationSuiteClass.REAL_PROVIDER_UAT:
        raise ReleaseEvidenceError("Stage 16.5 UAT evidence must use a REAL_PROVIDER_UAT suite.")
    if not report.entries or any(entry.kind != EvaluationSuiteEntryKind.UAT_CAPTURE for entry in report.entries):
        raise ReleaseEvidenceError(
            "Stage 16.5 accepts only Stage 16.4 UAT_CAPTURE entries for real-provider ISSUE_V1 evidence."
        )
    if any(entry.identity_id != "ISSUE_V1" for entry in report.entries):
        raise ReleaseEvidenceError("Stage 16.5 UAT evidence must preserve architecture=ISSUE_V1.")

    return ReleaseEvidenceItem(
        evidence_id="stage16-real-provider-uat",
        evidence_class=ReleaseEvidenceClass.REAL_PROVIDER_UAT,
        status=ReleaseEvidenceStatus.PASS if report.all_entries_passed else ReleaseEvidenceStatus.FAIL,
        source_fingerprint=_file_sha256(path),
        summary=(
            "Real-provider ISSUE_V1 UAT capture reached COMPLETE through the sanitized UAT suite."
            if report.all_entries_passed
            else "Real-provider UAT evidence is present, but at least one captured provider chain did not reach COMPLETE."
        ),
        warnings=[
            "UAT completion proves provider-chain execution/provenance only; it is not professional legal correctness."
        ],
    )


def build_stage16_release_evidence_matrix(
    repo_root: Path,
    public_suite_path: Path,
    work_dir: Path,
    *,
    expert_report_path: Path | None = None,
    uat_suite_path: Path | None = None,
) -> Stage16ReleaseEvidenceMatrix:
    repo_root = repo_root.resolve()
    public_suite = _resolve_path(public_suite_path, repo_root=repo_root)
    work_dir = work_dir.resolve()
    _require_file(public_suite, label="Stage 16 public evaluation suite")
    work_dir.mkdir(parents=True, exist_ok=True)

    evidence = [
        _public_regression_item(repo_root, public_suite, work_dir),
        _private_expert_item(repo_root, expert_report_path),
        _real_provider_uat_item(repo_root, uat_suite_path, work_dir),
    ]

    public_item, expert_item, uat_item = evidence
    engineering_ready = public_item.status == ReleaseEvidenceStatus.PASS
    stage16_evidence_complete = (
        engineering_ready
        and expert_item.status == ReleaseEvidenceStatus.PRESENT
        and uat_item.status == ReleaseEvidenceStatus.PASS
    )
    pending = [
        item.evidence_class for item in evidence if item.status == ReleaseEvidenceStatus.PENDING
    ]

    return Stage16ReleaseEvidenceMatrix(
        evaluator_version=RELEASE_EVIDENCE_EVALUATOR_VERSION,
        engineering_ready=engineering_ready,
        stage16_evidence_complete=stage16_evidence_complete,
        pending_evidence_classes=pending,
        evidence=evidence,
        warnings=[
            "This matrix assembles evidence classes; it does not invent overall_accuracy, legal_accuracy, or an expert-derived release threshold.",
            "engineering_ready means the pinned public deterministic suite passed; it is not final product release authorization.",
            "stage16_evidence_complete means required Stage 16 evidence artifacts are present and structurally usable, not that Law-Rag is professionally correct in all cases.",
            "The release-evidence runner never invokes DeepSeek, Kimi, OCR, or another paid/network provider."
        ],
    )
