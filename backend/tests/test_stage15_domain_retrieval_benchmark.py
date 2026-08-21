from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.audit_plan_models import AuditPlanIssue, AuditPlanSource, ContractType, ReviewPriority
from app.legal.corpus_packs import CorpusPackStatus, discover_corpus_packs
from app.legal.domain_routing import route_issue_to_corpus_packs
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index, retrieve_legal_evidence
from app.legal.retrieval_models import RetrievalRequest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_three_domain_store(root: Path, legal_db: Path, index_db: Path) -> None:
    corpus_root = root / "legal_data"
    registry = corpus_root / "source_registry.json"
    manifests: list[Path] = []
    seen: set[str] = set()
    for pack in discover_corpus_packs(corpus_root):
        if pack.manifest.status != CorpusPackStatus.READY:
            continue
        for relative in pack.manifest.authority_manifest_paths:
            if relative in seen:
                continue
            seen.add(relative)
            manifests.append(corpus_root / relative)
    assert len(manifests) == 15
    for index, manifest in enumerate(manifests):
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


def _first_authority_rank(response, authority_id: str) -> int | None:
    return next(
        (
            rank
            for rank, candidate in enumerate(response.candidates, start=1)
            if candidate.authority_id == authority_id
        ),
        None,
    )


def test_three_domain_routing_does_not_reduce_lexical_recall_or_mrr(tmp_path: Path) -> None:
    root = _repo_root()
    benchmark = json.loads(
        (root / "legal_data" / "fixtures" / "stage15_domain_retrieval_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    legal_db = tmp_path / "legal.db"
    index_db = tmp_path / "retrieval.db"
    _build_three_domain_store(root, legal_db, index_db)

    broad_hits = 0
    scoped_hits = 0
    broad_rr = 0.0
    scoped_rr = 0.0

    for case in benchmark["cases"]:
        issue = AuditPlanIssue(
            issue_id=case["case_id"],
            topic=case["topic"],
            priority=ReviewPriority.IMPORTANT,
            sources=[AuditPlanSource.BASELINE],
            why_review=[case["topic"]],
            questions=[case["topic"]],
            retrieval_queries=[case["query"]],
        )
        route = route_issue_to_corpus_packs(issue, ContractType(case["contract_type"]))
        as_of = date.fromisoformat(case["as_of"])

        broad = retrieve_legal_evidence(
            legal_db,
            index_db,
            RetrievalRequest(
                query=case["query"],
                as_of=as_of,
                top_k=5,
                use_semantic=False,
            ),
        )
        scoped = retrieve_legal_evidence(
            legal_db,
            index_db,
            RetrievalRequest(
                query=case["query"],
                as_of=as_of,
                top_k=5,
                use_semantic=False,
                authority_ids_allowlist=route.eligible_authority_ids,
            ),
        )

        expected = case["expected_authority_id"]
        broad_rank = _first_authority_rank(broad, expected)
        scoped_rank = _first_authority_rank(scoped, expected)
        if broad_rank is not None:
            broad_hits += 1
            broad_rr += 1.0 / broad_rank
        if scoped_rank is not None:
            scoped_hits += 1
            scoped_rr += 1.0 / scoped_rank

        assert scoped.candidates, case["case_id"]
        assert {item.authority_id for item in scoped.candidates} <= set(route.eligible_authority_ids)

    case_count = len(benchmark["cases"])
    broad_recall = broad_hits / case_count
    scoped_recall = scoped_hits / case_count
    broad_mrr = broad_rr / case_count
    scoped_mrr = scoped_rr / case_count

    assert scoped_recall >= 0.90
    assert scoped_mrr >= 0.80
    assert scoped_recall >= broad_recall
    assert scoped_mrr >= broad_mrr
