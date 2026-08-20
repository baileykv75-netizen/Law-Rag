from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from app.audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanPlanningMode,
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ReviewPriority,
)
from app.issue_legal_context import build_issue_legal_context
from app.legal.corpus_packs import CorpusPackStatus, discover_corpus_packs
from app.legal.domain_routing import LegalDomain, route_issue_to_corpus_packs, routing_catalog_fingerprint
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index, retrieve_legal_evidence
from app.legal.retrieval_models import RetrievalRequest
from app.storage import job_audit_plan_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _issue(topic: str, query: str) -> AuditPlanIssue:
    return AuditPlanIssue(
        issue_id="stage15-domain-fixture",
        topic=topic,
        priority=ReviewPriority.IMPORTANT,
        sources=[AuditPlanSource.LLM_DYNAMIC],
        why_review=[topic],
        questions=[topic],
        retrieval_queries=[query],
    )


def _three_domain_manifests(root: Path) -> list[Path]:
    corpus_root = root / "legal_data"
    ordered: list[Path] = []
    seen: set[str] = set()
    for pack in discover_corpus_packs(corpus_root):
        if pack.manifest.status != CorpusPackStatus.READY:
            continue
        for configured in pack.manifest.authority_manifest_paths:
            if configured in seen:
                continue
            seen.add(configured)
            ordered.append(corpus_root / configured)
    assert len(ordered) == 15
    return ordered


def _build_three_domain_store(root: Path, legal_db: Path, index_db: Path) -> None:
    registry = root / "legal_data" / "source_registry.json"
    for index, manifest in enumerate(_three_domain_manifests(root)):
        report = import_manifest(
            manifest,
            legal_db,
            rebuild=index == 0,
            source_registry_path=registry,
        )
        assert report.rejected_records == 0
    summary = build_retrieval_index(legal_db, index_db)
    assert summary.ready is True
    assert summary.article_count == 1274


def test_deterministic_issue_router_selects_single_cross_and_fallback_pack_sets() -> None:
    labor = route_issue_to_corpus_packs(
        _issue("劳动合同解除与经济补偿", "劳动合同解除经济补偿"),
        ContractType.UNKNOWN,
    )
    assert labor.domain == LegalDomain.LABOR_DISPUTE
    assert labor.eligible_pack_ids == ["cn-labor-dispute-core"]
    assert "prc-labor-contract-law" in labor.eligible_authority_ids
    assert "prc-company-law" not in labor.eligible_authority_ids

    cross = route_issue_to_corpus_packs(
        _issue("商标许可与个人信息处理", "商标许可 个人信息"),
        ContractType.TECHNOLOGY,
    )
    assert cross.domain == LegalDomain.CROSS_DOMAIN
    assert cross.eligible_pack_ids == [
        "cn-enterprise-compliance-core",
        "cn-intellectual-property-core",
    ]
    assert "prc-trademark-law" in cross.eligible_authority_ids
    assert "prc-personal-information-protection-law" in cross.eligible_authority_ids
    assert "cn-labor-dispute-core" not in cross.eligible_pack_ids

    employment_fallback = route_issue_to_corpus_packs(
        _issue("履约安排", "双方后续履约安排"),
        ContractType.EMPLOYMENT,
    )
    assert employment_fallback.domain == LegalDomain.LABOR_DISPUTE
    assert employment_fallback.fallback_all_ready_packs is False

    broad = route_issue_to_corpus_packs(
        _issue("其他合同问题", "一般性合同风险"),
        ContractType.UNKNOWN,
    )
    assert broad.domain == LegalDomain.UNMAPPED
    assert broad.fallback_all_ready_packs is True
    assert broad.eligible_pack_ids == [
        "cn-enterprise-compliance-core",
        "cn-intellectual-property-core",
        "cn-labor-dispute-core",
    ]
    assert len(routing_catalog_fingerprint()) == 64


def test_authority_scope_filters_exact_and_lexical_channels_before_fusion(tmp_path: Path) -> None:
    root = _repo_root()
    legal_db = tmp_path / "legal.db"
    index_db = tmp_path / "retrieval.db"
    _build_three_domain_store(root, legal_db, index_db)

    labor = route_issue_to_corpus_packs(
        _issue("劳动合同解除与经济补偿", "劳动合同解除经济补偿"),
        ContractType.UNKNOWN,
    )
    response = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="劳动合同解除 经济补偿",
            as_of=date(2026, 8, 20),
            top_k=8,
            use_semantic=False,
            authority_ids_allowlist=labor.eligible_authority_ids,
        ),
    )
    assert response.candidates
    assert {item.authority_id for item in response.candidates} <= set(labor.eligible_authority_ids)
    assert not any(item.authority_id == "prc-company-law" for item in response.candidates)
    assert not any(item.authority_id == "prc-trademark-law" for item in response.candidates)

    blocked_exact = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="个人信息保护法第十三条",
            as_of=date(2026, 8, 20),
            legal_evidence_id_hint=(
                "legal:prc-personal-information-protection-law:effective-2021-11-01:article-13"
            ),
            top_k=5,
            use_semantic=False,
            authority_ids_allowlist=labor.eligible_authority_ids,
        ),
    )
    assert all(
        item.authority_id in labor.eligible_authority_ids for item in blocked_exact.candidates
    )
    assert not any(
        item.authority_id == "prc-personal-information-protection-law"
        for item in blocked_exact.candidates
    )
    assert any("outside the eligible Authority scope" in warning for warning in blocked_exact.warnings)


def test_domain_scope_preserves_trademark_as_of_version_resolution(tmp_path: Path) -> None:
    root = _repo_root()
    legal_db = tmp_path / "legal.db"
    index_db = tmp_path / "retrieval.db"
    _build_three_domain_store(root, legal_db, index_db)

    ip = route_issue_to_corpus_packs(
        _issue("商标注册", "商标法第一条"),
        ContractType.UNKNOWN,
    )
    current = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="商标法第一条",
            as_of=date(2026, 12, 31),
            authority_id_hint="prc-trademark-law",
            article_token_hint="第一条",
            use_semantic=False,
            authority_ids_allowlist=ip.eligible_authority_ids,
        ),
    )
    future = retrieve_legal_evidence(
        legal_db,
        index_db,
        RetrievalRequest(
            query="商标法第一条",
            as_of=date(2027, 1, 1),
            authority_id_hint="prc-trademark-law",
            article_token_hint="第一条",
            use_semantic=False,
            authority_ids_allowlist=ip.eligible_authority_ids,
        ),
    )
    assert current.candidates[0].version_id == "effective-2019-11-01"
    assert future.candidates[0].version_id == "effective-2027-01-01"
    assert current.candidates[0].exact_hit is True
    assert future.candidates[0].exact_hit is True


def test_issue_legal_context_persists_applied_domain_scope_on_three_domain_store(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repo_root()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    legal_db = tmp_path / "legal" / "legal.db"
    index_db = tmp_path / "legal" / "retrieval.db"
    _build_three_domain_store(root, legal_db, index_db)

    job_id = uuid4()
    issue = _issue("劳动合同解除与经济补偿", "劳动合同解除 经济补偿")
    plan = AuditPlan(
        job_id=job_id,
        contract_type=ContractType.EMPLOYMENT,
        contract_type_confidence=ContractTypeConfidence.HIGH,
        contract_type_reasoning="Stage 15.4 fixture",
        provider="fixture",
        model="fixture",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        planner_input_fingerprint="input-fp",
        planner_response_hash="response-fp",
        planning_mode=AuditPlanPlanningMode.DIRECT,
        coverage_complete=True,
        issues=[issue],
    )
    job_audit_plan_path(job_id).write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    artifact = build_issue_legal_context(
        job_id,
        as_of=date(2026, 8, 20),
        use_semantic=False,
        top_k_per_query=8,
    )
    package = artifact.issues[0]
    assert package.domain_route is not None
    assert package.domain_route.domain == LegalDomain.LABOR_DISPUTE
    assert package.domain_route.scope_applied is True
    assert package.domain_route.retrieval_authority_ids == package.domain_route.eligible_authority_ids
    assert package.legal_evidence
    assert {
        hit.candidate.authority_id for hit in package.legal_evidence
    } <= set(package.domain_route.retrieval_authority_ids)
    assert artifact.domain_routing_fingerprint == routing_catalog_fingerprint()
