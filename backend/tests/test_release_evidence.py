from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import release_evidence
from app.evaluation_suite_models import (
    EvaluationSuiteClass,
    EvaluationSuiteEntryKind,
    EvaluationSuiteEntryResult,
    EvaluationSuiteRunReport,
)
from app.release_evidence import ReleaseEvidenceError, build_stage16_release_evidence_matrix
from app.release_evidence_models import ReleaseEvidenceClass, ReleaseEvidenceStatus


def _write(path: Path, payload: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        path.write_text("{}\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _contains_key(value, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(_contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def _public_report(*, passed: bool = True) -> EvaluationSuiteRunReport:
    return EvaluationSuiteRunReport(
        evaluator_version="stage16d-1.0.0",
        suite_id="law-rag-stage16-public-evaluation",
        suite_version="1.1.0",
        suite_class=EvaluationSuiteClass.PUBLIC_REGRESSION,
        manifest_fingerprint="1" * 64,
        all_entries_passed=passed,
        entries=[
            EvaluationSuiteEntryResult(
                entry_id="public",
                kind=EvaluationSuiteEntryKind.PUBLIC_REGRESSION_PROFILE,
                passed=passed,
                evaluator_version="stage16b-1.0.0",
                identity_id="law-rag-stage16b-three-domain-public-regression",
                identity_version="1.0.0",
                unit_label="gates",
                unit_count=1,
                passed_count=1 if passed else 0,
                failed_count=0 if passed else 1,
            )
        ],
    )


def _uat_report(*, passed: bool = True) -> EvaluationSuiteRunReport:
    return EvaluationSuiteRunReport(
        evaluator_version="stage16d-1.0.0",
        suite_id="private-uat-suite",
        suite_version="1.0.0",
        suite_class=EvaluationSuiteClass.REAL_PROVIDER_UAT,
        manifest_fingerprint="2" * 64,
        all_entries_passed=passed,
        entries=[
            EvaluationSuiteEntryResult(
                entry_id="issue-v1-capture",
                kind=EvaluationSuiteEntryKind.UAT_CAPTURE,
                passed=passed,
                evaluator_version="stage16d-1.0.0",
                identity_id="ISSUE_V1",
                identity_version="stage16d-1.0.0",
                unit_label="uat_capture",
                unit_count=1,
                passed_count=1 if passed else 0,
                failed_count=0 if passed else 1,
            )
        ],
    )


def _expert_report_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "evaluator_version": "stage16c-1.0.0",
        "protocol_id": "private-protocol-secret-id",
        "protocol_version": "1.0.0",
        "dataset_id": "private-dataset-secret-id",
        "dataset_version": "1.0.0",
        "label_quality": {
            "total_case_count": 2,
            "agreed_case_count": 2,
            "adjudicated_case_count": 0,
            "ambiguous_case_count": 0,
            "usable_case_count": 2,
            "agreement_rate": 1.0,
            "adjudication_rate": 0.0,
            "ambiguity_rate": 0.0,
            "usable_rate": 1.0,
            "minimum_reviewer_count_required": 2,
            "minimum_reviewer_count_observed": 2,
        },
        "metrics": [
            {
                "metric_id": "finding-present",
                "label": "Private scoped finding metric",
                "metric_type": "BINARY_CLASSIFICATION",
                "scope": "Private fixture only",
                "selected_case_count": 2,
                "usable_case_count": 2,
                "ambiguous_case_count": 0,
                "true_positive": 1,
                "false_positive": 0,
                "false_negative": 0,
                "true_negative": 1,
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
            }
        ],
        "source_fingerprints": {
            "protocol_sha256": "a" * 64,
            "dataset_sha256": "b" * 64,
            "observations_sha256": "c" * 64,
            "label_audit_sha256": "d" * 64,
        },
        "warnings": [],
    }


def test_matrix_keeps_external_evidence_pending_without_blocking_engineering_ci(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    public_suite = _write(repo_root / "benchmarks" / "public" / "stage16b.json")
    monkeypatch.setattr(release_evidence, "run_evaluation_suite", lambda *_args, **_kwargs: _public_report())

    report = build_stage16_release_evidence_matrix(
        repo_root,
        public_suite,
        tmp_path / "work",
    )

    assert report.engineering_ready is True
    assert report.stage16_evidence_complete is False
    assert report.pending_evidence_classes == [
        ReleaseEvidenceClass.PRIVATE_EXPERT,
        ReleaseEvidenceClass.REAL_PROVIDER_UAT,
    ]
    assert [item.status for item in report.evidence] == [
        ReleaseEvidenceStatus.PASS,
        ReleaseEvidenceStatus.PENDING,
        ReleaseEvidenceStatus.PENDING,
    ]
    payload = report.model_dump(mode="json")
    assert not _contains_key(payload, "overall_accuracy")
    assert not _contains_key(payload, "legal_accuracy")


def test_matrix_rejects_expert_report_from_tracked_repository_path(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    public_suite = _write(repo_root / "benchmarks" / "public" / "stage16b.json")
    tracked_expert = _write(repo_root / "tracked-expert-report.json", _expert_report_payload())
    monkeypatch.setattr(release_evidence, "run_evaluation_suite", lambda *_args, **_kwargs: _public_report())

    with pytest.raises(ReleaseEvidenceError, match="tracked repository paths"):
        build_stage16_release_evidence_matrix(
            repo_root,
            public_suite,
            tmp_path / "work",
            expert_report_path=tracked_expert,
        )


def test_matrix_accepts_sanitized_expert_and_complete_uat_without_leaking_private_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    public_suite = _write(repo_root / "benchmarks" / "public" / "stage16b.json")
    expert_report = _write(tmp_path / "private" / "expert-report.json", _expert_report_payload())
    uat_suite = _write(tmp_path / "private" / "uat-suite.json")

    def fake_run(_repo_root, suite_path, _work_dir):
        return _uat_report() if Path(suite_path) == uat_suite.resolve() else _public_report()

    monkeypatch.setattr(release_evidence, "run_evaluation_suite", fake_run)

    report = build_stage16_release_evidence_matrix(
        repo_root,
        public_suite,
        tmp_path / "work",
        expert_report_path=expert_report,
        uat_suite_path=uat_suite,
    )

    assert report.engineering_ready is True
    assert report.stage16_evidence_complete is True
    assert report.pending_evidence_classes == []
    assert [item.status for item in report.evidence] == [
        ReleaseEvidenceStatus.PASS,
        ReleaseEvidenceStatus.PRESENT,
        ReleaseEvidenceStatus.PASS,
    ]
    rendered = report.model_dump_json()
    assert "private-protocol-secret-id" not in rendered
    assert "private-dataset-secret-id" not in rendered


def test_matrix_preserves_interrupted_real_uat_as_fail(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    public_suite = _write(repo_root / "benchmarks" / "public" / "stage16b.json")
    expert_report = _write(tmp_path / "private" / "expert-report.json", _expert_report_payload())
    uat_suite = _write(tmp_path / "private" / "uat-suite.json")

    def fake_run(_repo_root, suite_path, _work_dir):
        return _uat_report(passed=False) if Path(suite_path) == uat_suite.resolve() else _public_report()

    monkeypatch.setattr(release_evidence, "run_evaluation_suite", fake_run)

    report = build_stage16_release_evidence_matrix(
        repo_root,
        public_suite,
        tmp_path / "work",
        expert_report_path=expert_report,
        uat_suite_path=uat_suite,
    )

    assert report.engineering_ready is True
    assert report.stage16_evidence_complete is False
    assert report.evidence[2].status == ReleaseEvidenceStatus.FAIL
    assert report.pending_evidence_classes == []


def test_matrix_public_regression_failure_blocks_engineering_ready(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    public_suite = _write(repo_root / "benchmarks" / "public" / "stage16b.json")
    monkeypatch.setattr(
        release_evidence,
        "run_evaluation_suite",
        lambda *_args, **_kwargs: _public_report(passed=False),
    )

    report = build_stage16_release_evidence_matrix(repo_root, public_suite, tmp_path / "work")

    assert report.engineering_ready is False
    assert report.stage16_evidence_complete is False
    assert report.evidence[0].status == ReleaseEvidenceStatus.FAIL
