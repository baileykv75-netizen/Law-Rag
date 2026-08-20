from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from app.audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ReviewPriority,
)
from app.issue_legal_context import build_issue_legal_context
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.storage import job_audit_plan_path


def test_legacy_seed_without_stage15_pack_overlap_remains_retrievable(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    legal_db = tmp_path / "legal" / "legal.db"
    index_db = tmp_path / "legal" / "retrieval.db"
    import_manifest(root / "legal_data" / "seed" / "manifest.json", legal_db, rebuild=True)
    build_retrieval_index(legal_db, index_db)

    job_id = uuid4()
    plan = AuditPlan(
        job_id=job_id,
        contract_type=ContractType.UNKNOWN,
        contract_type_confidence=ContractTypeConfidence.LOW,
        contract_type_reasoning="legacy compatibility fixture",
        provider="fixture",
        model="fixture",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        planner_input_fingerprint="input-fp",
        planner_response_hash="response-fp",
        coverage_complete=True,
        issues=[
            AuditPlanIssue(
                issue_id="legacy-civil-code",
                topic="违约金调整",
                priority=ReviewPriority.IMPORTANT,
                sources=[AuditPlanSource.BASELINE],
                questions=["约定违约金过高如何处理？"],
                retrieval_queries=["约定违约金 过分高于造成的损失"],
            )
        ],
    )
    job_audit_plan_path(job_id).write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    artifact = build_issue_legal_context(job_id, as_of=date(2026, 8, 20), use_semantic=False)
    package = artifact.issues[0]
    assert package.domain_route is not None
    assert package.domain_route.scope_applied is False
    assert package.domain_route.retrieval_authority_ids == []
    assert any(
        hit.legal_evidence_id == "legal:prc-civil-code:effective-2021-01-01:article-585"
        for hit in package.legal_evidence
    )
    assert any("legacy/development corpus behavior remains available" in warning for warning in package.warnings)
