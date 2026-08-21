from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation_suite import run_evaluation_suite
from app.public_regression import (
    PublicRegressionError,
    _validate_promoted_stage15_fixture,
    _validate_release_routing_catalog,
    load_public_regression_profile,
    load_three_domain_dataset,
    run_public_regression_profile,
)
from app.public_regression_models import PublicRegressionProfile, ThreeDomainRetrievalDataset


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_stage16b_three_domain_public_regression_passes_named_gates(tmp_path: Path) -> None:
    root = _repo_root()
    profile_path = root / "benchmarks" / "public" / "stage16b_three_domain_regression.json"

    report, fingerprints = run_public_regression_profile(root, profile_path, tmp_path / "work")

    assert report.evaluator_version == "stage16b-1.0.0"
    assert report.all_gates_passed is True
    assert len(report.gates) == 10
    assert all(gate.passed for gate in report.gates)
    metrics = {metric.key: metric.value for metric in report.metrics}
    assert metrics["retrieval.three_domain.scoped_recall_at_5"] >= 0.90
    assert metrics["retrieval.three_domain.scoped_mrr"] >= 0.80
    assert metrics["retrieval.three_domain.scoped_recall_minus_broad"] >= 0.0
    assert metrics["retrieval.three_domain.scoped_mrr_minus_broad"] >= 0.0
    assert metrics["retrieval.three_domain.authority_scope_compliance_rate"] == 1.0
    assert metrics["routing.three_domain.expected_authority_eligible_rate"] == 1.0
    assert metrics["corpus.three_domain.article_count"] == 1274.0
    assert metrics["routing.unmapped_fallback_preserved"] == 1.0
    assert metrics["routing.cross_domain_union_preserved"] == 1.0
    assert metrics["retrieval.trademark_version_boundary_exact_rate"] == 1.0
    assert report.diagnostics == []
    assert set(fingerprints) == {
        "regression_profile_sha256",
        "regression_dataset_sha256",
        "promoted_stage15_fixture_sha256",
        "corpus_release_sha256",
        "routing_catalog_sha256",
    }
    assert all(len(value) == 64 for value in fingerprints.values())


def test_stage16b_dataset_is_semantically_identical_to_promoted_stage15_fixture() -> None:
    root = _repo_root()
    dataset_path = root / "benchmarks" / "public" / "stage16b_three_domain_retrieval.dataset.json"
    dataset = load_three_domain_dataset(dataset_path)

    source_path = _validate_promoted_stage15_fixture(root, dataset)

    assert source_path == (root / "legal_data" / "fixtures" / "stage15_domain_retrieval_benchmark.json").resolve()
    assert len(dataset.cases) == 9


def test_stage16b_dataset_divergence_from_promoted_fixture_fails_closed() -> None:
    root = _repo_root()
    dataset_path = root / "benchmarks" / "public" / "stage16b_three_domain_retrieval.dataset.json"
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_authority_id"] = "prc-company-law"
    changed = ThreeDomainRetrievalDataset.model_validate(payload)

    with pytest.raises(PublicRegressionError, match="diverges from the promoted Stage 15 fixture"):
        _validate_promoted_stage15_fixture(root, changed)


def test_public_regression_profile_rejects_path_traversal() -> None:
    root = _repo_root()
    payload = json.loads(
        (root / "benchmarks" / "public" / "stage16b_three_domain_regression.json").read_text(
            encoding="utf-8"
        )
    )
    payload["benchmark_path"] = "../private/labels.json"

    with pytest.raises(ValidationError, match="traversal-free"):
        PublicRegressionProfile.model_validate(payload)


def test_release_identity_and_ready_routing_catalog_must_match_profile() -> None:
    root = _repo_root()
    profile = load_public_regression_profile(
        root / "benchmarks" / "public" / "stage16b_three_domain_regression.json"
    )
    release = json.loads(
        (root / "legal_data" / "releases" / "three-domain-core" / "1.0.0" / "release.json").read_text(
            encoding="utf-8"
        )
    )

    _validate_release_routing_catalog(root, release, profile)

    wrong_identity = deepcopy(release)
    wrong_identity["corpus_version"] = "9.9.9"
    with pytest.raises(PublicRegressionError, match="identity mismatch"):
        _validate_release_routing_catalog(root, wrong_identity, profile)

    drifted_pack = deepcopy(release)
    drifted_pack["packs"][0]["pack_version"] = "9.9.9"
    with pytest.raises(PublicRegressionError, match="no longer matches the READY routing catalog"):
        _validate_release_routing_catalog(root, drifted_pack, profile)


def test_stage16b_suite_adds_three_domain_entry_without_mutating_stage16a_smoke(tmp_path: Path) -> None:
    root = _repo_root()
    old_report = run_evaluation_suite(
        root,
        root / "benchmarks" / "public" / "stage16a_evaluation_suite.json",
        tmp_path / "old",
    )
    new_report = run_evaluation_suite(
        root,
        root / "benchmarks" / "public" / "stage16b_evaluation_suite.json",
        tmp_path / "new",
    )

    assert old_report.all_entries_passed is True
    assert [entry.entry_id for entry in old_report.entries] == [
        "stage11-schema-smoke",
        "stage11-public-quality-gates",
    ]
    assert new_report.all_entries_passed is True
    assert [entry.entry_id for entry in new_report.entries] == [
        "stage11-schema-smoke",
        "stage11-public-quality-gates",
        "stage16b-three-domain-regression",
    ]
    stage16b = new_report.entries[-1]
    assert stage16b.kind.value == "PUBLIC_REGRESSION_PROFILE"
    assert stage16b.evaluator_version == "stage16b-1.0.0"
    assert stage16b.unit_label == "gates"
    assert stage16b.unit_count == 10
    assert stage16b.failed_count == 0
