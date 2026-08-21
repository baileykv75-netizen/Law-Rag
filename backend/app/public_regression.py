from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .audit_plan_models import AuditPlanIssue, AuditPlanSource, ContractType, ReviewPriority
from .legal.corpus_packs import CorpusPackStatus, discover_corpus_packs
from .legal.domain_routing import LegalDomain, route_issue_to_corpus_packs, routing_catalog_fingerprint
from .legal.importer import import_manifest
from .legal.retrieval import build_retrieval_index, retrieve_legal_evidence
from .legal.retrieval_models import RetrievalRequest
from .public_regression_models import (
    PUBLIC_REGRESSION_EVALUATOR_VERSION,
    PublicRegressionProfile,
    PublicRegressionRunner,
    ThreeDomainRetrievalDataset,
)
from .quality import evaluate_quality_gates
from .quality_models import QualityDiagnostic, QualityGateProfile, QualityMetric, QualityRunReport


class PublicRegressionError(RuntimeError):
    pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise PublicRegressionError(f"Could not hash public regression input {path}: {exc}") from exc
    return digest.hexdigest()


def _repo_path(repo_root: Path, configured: str, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / configured).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PublicRegressionError(f"{label} must remain inside the repository: {configured}") from exc
    if not path.is_file():
        raise PublicRegressionError(f"{label} does not exist or is not a file: {path}")
    return path


def load_public_regression_profile(path: Path) -> PublicRegressionProfile:
    try:
        return PublicRegressionProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise PublicRegressionError(f"Invalid public regression profile {path}: {exc}") from exc


def load_three_domain_dataset(path: Path) -> ThreeDomainRetrievalDataset:
    try:
        return ThreeDomainRetrievalDataset.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise PublicRegressionError(f"Invalid three-domain regression dataset {path}: {exc}") from exc


def _normalized_case(case: Any) -> dict[str, Any]:
    if hasattr(case, "model_dump"):
        payload = case.model_dump(mode="json")
    else:
        payload = case
    return {
        "case_id": payload["case_id"],
        "topic": payload["topic"],
        "query": payload["query"],
        "contract_type": payload["contract_type"],
        "as_of": payload["as_of"],
        "expected_authority_id": payload["expected_authority_id"],
    }


def _validate_promoted_stage15_fixture(repo_root: Path, dataset: ThreeDomainRetrievalDataset) -> Path:
    source_path = _repo_path(repo_root, dataset.source_fixture_path, label="Stage 15 source fixture")
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicRegressionError(f"Invalid Stage 15 source fixture {source_path}: {exc}") from exc
    source_cases = [_normalized_case(case) for case in source.get("cases", [])]
    promoted_cases = [_normalized_case(case) for case in dataset.cases]
    if promoted_cases != source_cases:
        raise PublicRegressionError(
            "Stage 16 three-domain dataset diverges from the promoted Stage 15 fixture; "
            "change the dataset version/source evidence explicitly instead of silently relabeling cases."
        )
    return source_path


def _release_manifest_paths(repo_root: Path, release_path: Path) -> tuple[dict[str, Any], list[Path]]:
    try:
        release = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicRegressionError(f"Invalid Corpus Release {release_path}: {exc}") from exc
    paths: list[Path] = []
    seen: set[str] = set()
    for pack in release.get("packs", []):
        for configured in pack.get("authority_manifest_paths", []):
            if configured in seen:
                continue
            seen.add(configured)
            path = (repo_root / "legal_data" / configured).resolve()
            if not path.is_file():
                raise PublicRegressionError(f"Corpus Release Authority manifest is missing: {configured}")
            paths.append(path)
    if not paths:
        raise PublicRegressionError("Corpus Release contains no Authority manifest paths.")
    return release, paths


def _build_release_store(repo_root: Path, release_path: Path, legal_db: Path, index_db: Path) -> dict[str, Any]:
    release, manifests = _release_manifest_paths(repo_root, release_path)
    registry = repo_root / "legal_data" / "source_registry.json"
    for index, manifest in enumerate(manifests):
        report = import_manifest(
            manifest,
            legal_db,
            rebuild=index == 0,
            source_registry_path=registry,
        )
        if report.rejected_records:
            raise PublicRegressionError(
                f"Corpus Release import rejected {report.rejected_records} records from {manifest}."
            )
    summary = build_retrieval_index(legal_db, index_db)
    if not summary.ready:
        raise PublicRegressionError("Three-domain retrieval index did not become ready.")
    expected_articles = sum(
        int(version.get("expected_article_count") or 0) for version in release.get("versions", [])
    )
    if expected_articles and summary.article_count != expected_articles:
        raise PublicRegressionError(
            f"Corpus Release article count mismatch: release={expected_articles}, index={summary.article_count}."
        )
    return {
        "release": release,
        "article_count": summary.article_count,
        "manifest_count": len(manifests),
    }


def _issue(case_id: str, topic: str, query: str) -> AuditPlanIssue:
    return AuditPlanIssue(
        issue_id=case_id,
        topic=topic,
        priority=ReviewPriority.IMPORTANT,
        sources=[AuditPlanSource.BASELINE],
        why_review=[topic],
        questions=[topic],
        retrieval_queries=[query],
    )


def _first_authority_rank(response, authority_id: str) -> int | None:
    return next(
        (
            rank
            for rank, candidate in enumerate(response.candidates, start=1)
            if candidate.authority_id == authority_id
        ),
        None,
    )


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


def _routing_smokes(legal_db: Path, index_db: Path) -> tuple[dict[str, float], list[QualityDiagnostic]]:
    diagnostics: list[QualityDiagnostic] = []

    broad_route = route_issue_to_corpus_packs(
        _issue("stage16-unmapped", "其他合同问题", "一般性合同风险"),
        ContractType.UNKNOWN,
    )
    broad_ok = (
        broad_route.domain == LegalDomain.UNMAPPED
        and broad_route.fallback_all_ready_packs
        and len(broad_route.eligible_pack_ids) == 3
    )
    if not broad_ok:
        diagnostics.append(
            QualityDiagnostic(
                layer="LEGAL_RETRIEVAL",
                category="UNMAPPED_FALLBACK_CHANGED",
                case_id="stage16-unmapped",
                message="UNMAPPED Issue no longer preserves the all-READY-pack broad fallback.",
                expected={"domain": "UNMAPPED", "fallback_all_ready_packs": True, "pack_count": 3},
                observed={
                    "domain": broad_route.domain.value,
                    "fallback_all_ready_packs": broad_route.fallback_all_ready_packs,
                    "pack_ids": broad_route.eligible_pack_ids,
                },
            )
        )

    cross_route = route_issue_to_corpus_packs(
        _issue("stage16-cross-domain", "商标许可与个人信息处理", "商标许可 个人信息"),
        ContractType.TECHNOLOGY,
    )
    expected_cross_packs = {"cn-enterprise-compliance-core", "cn-intellectual-property-core"}
    cross_ok = (
        cross_route.domain == LegalDomain.CROSS_DOMAIN
        and set(cross_route.eligible_pack_ids) == expected_cross_packs
        and "cn-labor-dispute-core" not in cross_route.eligible_pack_ids
    )
    if not cross_ok:
        diagnostics.append(
            QualityDiagnostic(
                layer="LEGAL_RETRIEVAL",
                category="CROSS_DOMAIN_UNION_CHANGED",
                case_id="stage16-cross-domain",
                message="Cross-domain routing no longer preserves the expected IP + enterprise Pack union.",
                expected=sorted(expected_cross_packs),
                observed=cross_route.eligible_pack_ids,
            )
        )

    ip_route = route_issue_to_corpus_packs(
        _issue("stage16-trademark-version", "商标注册", "商标法第一条"),
        ContractType.UNKNOWN,
    )
    version_checks = [
        ("2026-12-31", "effective-2019-11-01"),
        ("2027-01-01", "effective-2027-01-01"),
    ]
    version_hits = 0
    for as_of, expected_version in version_checks:
        response = retrieve_legal_evidence(
            legal_db,
            index_db,
            RetrievalRequest(
                query="商标法第一条",
                as_of=__import__("datetime").date.fromisoformat(as_of),
                authority_id_hint="prc-trademark-law",
                article_token_hint="第一条",
                top_k=5,
                use_semantic=False,
                authority_ids_allowlist=ip_route.eligible_authority_ids,
            ),
        )
        candidate = response.candidates[0] if response.candidates else None
        if candidate is not None and candidate.version_id == expected_version and candidate.exact_hit:
            version_hits += 1
        else:
            diagnostics.append(
                QualityDiagnostic(
                    layer="LEGAL_RETRIEVAL",
                    category="AS_OF_VERSION_BOUNDARY_MISMATCH",
                    case_id=f"trademark-{as_of}",
                    message="Trademark exact-citation retrieval resolved the wrong Authority Version at an as_of boundary.",
                    expected=expected_version,
                    observed=(candidate.version_id if candidate is not None else None),
                )
            )

    return {
        "routing.unmapped_fallback_preserved": 1.0 if broad_ok else 0.0,
        "routing.cross_domain_union_preserved": 1.0 if cross_ok else 0.0,
        "retrieval.trademark_version_boundary_exact_rate": _ratio(version_hits, len(version_checks)),
    }, diagnostics


def _run_three_domain_retrieval(
    repo_root: Path,
    work_dir: Path,
    profile: PublicRegressionProfile,
    profile_path: Path,
) -> tuple[QualityRunReport, dict[str, str]]:
    dataset_path = _repo_path(repo_root, profile.benchmark_path, label="Three-domain benchmark")
    release_path = _repo_path(repo_root, profile.corpus_release_path, label="Corpus Release")
    dataset = load_three_domain_dataset(dataset_path)
    source_fixture_path = _validate_promoted_stage15_fixture(repo_root, dataset)

    work_dir.mkdir(parents=True, exist_ok=True)
    legal_db = work_dir / "legal.db"
    index_db = work_dir / "retrieval.db"
    store = _build_release_store(repo_root, release_path, legal_db, index_db)

    broad_hits = scoped_hits = 0
    broad_rr = scoped_rr = 0.0
    route_eligible = 0
    scoped_candidates = 0
    scoped_compliant = 0
    diagnostics: list[QualityDiagnostic] = []

    for case in dataset.cases:
        try:
            contract_type = ContractType(case.contract_type)
        except ValueError as exc:
            raise PublicRegressionError(
                f"Unsupported contract_type in public regression case {case.case_id}: {case.contract_type}"
            ) from exc
        route = route_issue_to_corpus_packs(_issue(case.case_id, case.topic, case.query), contract_type)
        if case.expected_authority_id in route.eligible_authority_ids:
            route_eligible += 1
        else:
            diagnostics.append(
                QualityDiagnostic(
                    layer="LEGAL_RETRIEVAL",
                    category="EXPECTED_AUTHORITY_OUTSIDE_ROUTE",
                    case_id=case.case_id,
                    message="The expected Authority is outside the deterministic Issue route.",
                    expected=case.expected_authority_id,
                    observed=route.eligible_authority_ids,
                )
            )

        broad = retrieve_legal_evidence(
            legal_db,
            index_db,
            RetrievalRequest(query=case.query, as_of=case.as_of, top_k=5, use_semantic=False),
        )
        scoped = retrieve_legal_evidence(
            legal_db,
            index_db,
            RetrievalRequest(
                query=case.query,
                as_of=case.as_of,
                top_k=5,
                use_semantic=False,
                authority_ids_allowlist=route.eligible_authority_ids,
            ),
        )
        broad_rank = _first_authority_rank(broad, case.expected_authority_id)
        scoped_rank = _first_authority_rank(scoped, case.expected_authority_id)
        if broad_rank is not None:
            broad_hits += 1
            broad_rr += 1.0 / broad_rank
        if scoped_rank is not None:
            scoped_hits += 1
            scoped_rr += 1.0 / scoped_rank
        else:
            diagnostics.append(
                QualityDiagnostic(
                    layer="LEGAL_RETRIEVAL",
                    category="EXPECTED_AUTHORITY_MISSED_SCOPED_TOP5",
                    case_id=case.case_id,
                    message="Scoped three-domain retrieval missed the expected Authority within top-5.",
                    expected=case.expected_authority_id,
                    observed=[candidate.authority_id for candidate in scoped.candidates],
                )
            )

        allowed = set(route.eligible_authority_ids)
        scoped_candidates += len(scoped.candidates)
        compliant = [candidate for candidate in scoped.candidates if candidate.authority_id in allowed]
        scoped_compliant += len(compliant)
        if len(compliant) != len(scoped.candidates):
            diagnostics.append(
                QualityDiagnostic(
                    layer="LEGAL_RETRIEVAL",
                    category="AUTHORITY_SCOPE_VIOLATION",
                    case_id=case.case_id,
                    message="Scoped retrieval returned an Authority outside the deterministic route allowlist.",
                    expected=sorted(allowed),
                    observed=[candidate.authority_id for candidate in scoped.candidates],
                )
            )

    case_count = len(dataset.cases)
    scoped_recall = _ratio(scoped_hits, case_count)
    broad_recall = _ratio(broad_hits, case_count)
    scoped_mrr = _ratio(scoped_rr, case_count)
    broad_mrr = _ratio(broad_rr, case_count)
    smoke_values, smoke_diagnostics = _routing_smokes(legal_db, index_db)
    diagnostics.extend(smoke_diagnostics)

    metric_values = {
        "retrieval.three_domain.scoped_recall_at_5": scoped_recall,
        "retrieval.three_domain.scoped_mrr": scoped_mrr,
        "retrieval.three_domain.broad_recall_at_5": broad_recall,
        "retrieval.three_domain.broad_mrr": broad_mrr,
        "retrieval.three_domain.scoped_recall_minus_broad": scoped_recall - broad_recall,
        "retrieval.three_domain.scoped_mrr_minus_broad": scoped_mrr - broad_mrr,
        "retrieval.three_domain.authority_scope_compliance_rate": _ratio(scoped_compliant, scoped_candidates),
        "routing.three_domain.expected_authority_eligible_rate": _ratio(route_eligible, case_count),
        "corpus.three_domain.article_count": float(store["article_count"]),
        **smoke_values,
    }
    labels = {
        "retrieval.three_domain.scoped_recall_at_5": "Three-domain scoped lexical Recall@5",
        "retrieval.three_domain.scoped_mrr": "Three-domain scoped lexical MRR",
        "retrieval.three_domain.broad_recall_at_5": "Three-domain broad lexical Recall@5",
        "retrieval.three_domain.broad_mrr": "Three-domain broad lexical MRR",
        "retrieval.three_domain.scoped_recall_minus_broad": "Scoped minus broad Recall@5",
        "retrieval.three_domain.scoped_mrr_minus_broad": "Scoped minus broad MRR",
        "retrieval.three_domain.authority_scope_compliance_rate": "Scoped candidate Authority-scope compliance rate",
        "routing.three_domain.expected_authority_eligible_rate": "Expected Authority eligible under deterministic route",
        "corpus.three_domain.article_count": "Three-domain release article count",
        "routing.unmapped_fallback_preserved": "UNMAPPED broad fallback preserved",
        "routing.cross_domain_union_preserved": "Cross-domain Pack union preserved",
        "retrieval.trademark_version_boundary_exact_rate": "Trademark as_of version-boundary exact-hit rate",
    }
    metrics = [
        QualityMetric(
            key=key,
            label=labels[key],
            value=value,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            scope=dataset.scope,
        )
        for key, value in metric_values.items()
    ]
    gate_profile = QualityGateProfile(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        title=profile.title,
        scope=profile.scope,
        gates=profile.gates,
    )
    gates = evaluate_quality_gates(gate_profile, metrics)
    report = QualityRunReport(
        evaluator_version=PUBLIC_REGRESSION_EVALUATOR_VERSION,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        all_gates_passed=all(gate.passed for gate in gates),
        metrics=metrics,
        gates=gates,
        diagnostics=diagnostics,
        warnings=[
            "Stage 16.2 public regression is deterministic repository-safe evidence, not a professional legal-accuracy claim.",
            "The runner uses lexical retrieval only and never calls DeepSeek, Kimi, OCR or another external model/provider.",
            f"Corpus Release evaluated: {store['release'].get('corpus_id')}@{store['release'].get('corpus_version')}.",
        ],
    )
    fingerprints = {
        "regression_profile_sha256": _file_sha256(profile_path),
        "regression_dataset_sha256": _file_sha256(dataset_path),
        "promoted_stage15_fixture_sha256": _file_sha256(source_fixture_path),
        "corpus_release_sha256": _file_sha256(release_path),
        "routing_catalog_sha256": routing_catalog_fingerprint(repo_root / "legal_data"),
    }
    return report, fingerprints


def run_public_regression_profile(
    repo_root: Path,
    profile_path: Path,
    work_dir: Path,
) -> tuple[QualityRunReport, dict[str, str]]:
    repo_root = repo_root.resolve()
    profile_path = profile_path.resolve()
    try:
        profile_path.relative_to((repo_root / "benchmarks" / "public").resolve())
    except ValueError as exc:
        raise PublicRegressionError("Public regression profiles must live under benchmarks/public/.") from exc
    profile = load_public_regression_profile(profile_path)
    if profile.runner == PublicRegressionRunner.THREE_DOMAIN_RETRIEVAL:
        return _run_three_domain_retrieval(repo_root, work_dir.resolve(), profile, profile_path)
    raise PublicRegressionError(f"Unsupported public regression runner: {profile.runner}")
