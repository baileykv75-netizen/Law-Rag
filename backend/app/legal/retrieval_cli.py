from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.legal.embeddings import BgeSmallZhProvider
from app.legal.retrieval import build_retrieval_index, retrieve_legal_evidence
from app.legal.retrieval_models import RetrievalEvaluationCase, RetrievalEvaluationReport, RetrievalRequest
from app.storage import legal_db_path, legal_retrieval_index_path


def _evaluate(cases_path: Path, *, use_semantic: bool) -> RetrievalEvaluationReport:
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = [RetrievalEvaluationCase.model_validate(item) for item in payload["cases"]]
    passed = 0
    reciprocal_rank_sum = 0.0
    details: list[dict] = []
    for case in cases:
        response = retrieve_legal_evidence(
            legal_db_path(),
            legal_retrieval_index_path(),
            RetrievalRequest(
                query=case.query,
                as_of=case.as_of,
                top_k=case.top_k,
                authority_id_hint=case.authority_id_hint,
                article_token_hint=case.article_token_hint,
                use_semantic=use_semantic,
            ),
        )
        returned = [item.legal_evidence_id for item in response.candidates]
        first_rank = None
        for index, evidence_id in enumerate(returned, start=1):
            if evidence_id in case.expected_evidence_ids:
                first_rank = index
                break
        hit = first_rank is not None
        if hit:
            passed += 1
            reciprocal_rank_sum += 1.0 / first_rank
        details.append(
            {
                "case_id": case.case_id,
                "hit": hit,
                "first_relevant_rank": first_rank,
                "expected": case.expected_evidence_ids,
                "returned": returned,
                "state": response.state.value,
            }
        )
    count = len(cases)
    return RetrievalEvaluationReport(
        case_count=count,
        recall_at_k=(passed / count) if count else 0.0,
        mrr=(reciprocal_rank_sum / count) if count else 0.0,
        passed_cases=passed,
        case_results=details,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Law-Rag Stage 7 legal retrieval utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rebuild = subparsers.add_parser("rebuild", help="Rebuild local retrieval index from legal.db")
    rebuild.add_argument("--semantic", action="store_true", help="Also build local BGE semantic vectors")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate retrieval benchmark")
    evaluate.add_argument("--cases", required=True, type=Path)
    evaluate.add_argument("--semantic", action="store_true")

    args = parser.parse_args()
    if args.command == "rebuild":
        provider = BgeSmallZhProvider() if args.semantic else None
        summary = build_retrieval_index(legal_db_path(), legal_retrieval_index_path(), semantic_provider=provider)
        print(summary.model_dump_json(indent=2))
        return 0
    if args.command == "evaluate":
        report = _evaluate(args.cases.resolve(), use_semantic=args.semantic)
        print(report.model_dump_json(indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
