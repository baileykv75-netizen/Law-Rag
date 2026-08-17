from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanPlanningMode,
    AuditPlanSource,
    ContractType,
    ContractTypeConfidence,
    ReviewPriority,
)
from app.issue_legal_context import (
    IssueLegalContextStaleError,
    build_issue_legal_context,
    load_issue_legal_context,
)
from app.issue_legal_context_models import IssueLegalSupportState
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.main import app
from app.storage import job_audit_plan_path

client = TestClient(app)


def _seed_legal(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / "legal_data" / "seed" / "manifest.json"
    legal_db = tmp_path / "legal" / "legal.db"
    index_db = tmp_path / "legal" / "retrieval.db"
    import_manifest(manifest, legal_db, rebuild=True)
    build_retrieval_index(legal_db, index_db)


def _plan(job_id, *, version: str = "fixture-v1") -> AuditPlan:
    return AuditPlan(
        job_id=job_id,
        contract_type=ContractType.UNKNOWN,
        contract_type_confidence=ContractTypeConfidence.LOW,
        contract_type_reasoning="fixture",
        provider="fixture",
        model="fixture",
        contract_source_fingerprint="source-fp",
        contract_content_fingerprint="content-fp",
        planner_input_fingerprint="input-fp",
        planner_response_hash=version,
        planning_mode=AuditPlanPlanningMode.DIRECT,
        coverage_complete=True,
        issues=[
            AuditPlanIssue(
                issue_id="plan-custom-liability",
                topic="责任上限与损失分配",
                priority=ReviewPriority.HIGH_ATTENTION,
                sources=[AuditPlanSource.LLM_DYNAMIC],
                why_review=["This topic is intentionally not one of the historical eight Stage 8 router topics."],
                contract_object_ids=["clause-009"],
                contract_evidence_ids=["contract-evidence-009"],
                questions=["责任限制与违约损失分配是否需要进一步审查？"],
                retrieval_queries=[
                    "违约金 过分高于损失 调整",
                    "约定违约金 过分高于造成的损失",
                ],
            ),
            AuditPlanIssue(
                issue_id="plan-no-local-hit",
                topic="本地语料覆盖探针",
                priority=ReviewPriority.NORMAL,
                sources=[AuditPlanSource.LLM_DYNAMIC],
                why_review=["fixture"],
                questions=["本地精选语料是否覆盖该主题？"],
                retrieval_queries=["火星殖民地量子遗嘱银河税务专属条款"],
            ),
        ],
    )


def _prepare(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    _seed_legal(tmp_path)
    job_id = uuid4()
    plan = _plan(job_id)
    job_audit_plan_path(job_id).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return job_id, plan


def test_issue_queries_drive_retrieval_without_legacy_topic_gate(tmp_path: Path, monkeypatch) -> None:
    job_id, _ = _prepare(tmp_path, monkeypatch)
    artifact = build_issue_legal_context(job_id, as_of=date(2026, 8, 15), use_semantic=False)

    package = next(item for item in artifact.issues if item.issue_id == "plan-custom-liability")
    evidence_ids = [item.legal_evidence_id for item in package.legal_evidence]
    assert "legal:prc-civil-code:effective-2021-01-01:article-585" in evidence_ids
    target = next(item for item in package.legal_evidence if item.legal_evidence_id.endswith(":article-585"))
    assert target.matched_query_indexes == [1, 2]
    assert target.candidate.version_id == "effective-2021-01-01"
    assert target.candidate.article_token == "第五百八十五条"
    assert package.contract_evidence_ids == ["contract-evidence-009"]
    assert package.support_state == IssueLegalSupportState.EVIDENCE_FOUND_WITH_LIMITATIONS
    assert artifact.total_issue_count == 2
    assert artifact.total_query_count == 3
    assert artifact.legal_source_fingerprint


def test_no_hit_is_explicitly_not_a_negative_legal_conclusion(tmp_path: Path, monkeypatch) -> None:
    job_id, _ = _prepare(tmp_path, monkeypatch)
    artifact = build_issue_legal_context(job_id, as_of=date(2026, 8, 15), use_semantic=False)
    package = next(item for item in artifact.issues if item.issue_id == "plan-no-local-hit")

    assert package.legal_evidence == []
    assert package.support_state == IssueLegalSupportState.NO_MATCH_IN_LOCAL_CORPUS
    assert any("not evidence that no applicable legal rule exists" in warning for warning in package.warnings)


def test_historical_as_of_date_preserves_version_resolution_failure(tmp_path: Path, monkeypatch) -> None:
    job_id, plan = _prepare(tmp_path, monkeypatch)
    plan.issues = [
        AuditPlanIssue(
            issue_id="plan-historical-version",
            topic="历史版本适用性",
            priority=ReviewPriority.IMPORTANT,
            sources=[AuditPlanSource.LLM_DYNAMIC],
            questions=["指定日期是否存在可适用的本地版本？"],
            retrieval_queries=["民法典第五百八十五条"],
        )
    ]
    job_audit_plan_path(job_id).write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    artifact = build_issue_legal_context(job_id, as_of=date(2020, 12, 31), use_semantic=False)
    package = artifact.issues[0]
    assert package.support_state == IssueLegalSupportState.VERSION_REVIEW_REQUIRED
    assert package.retrieval_runs[0].response.state.value == "NO_APPLICABLE_VERSION"
    assert package.legal_evidence == []


def test_persisted_context_is_stale_after_audit_plan_changes(tmp_path: Path, monkeypatch) -> None:
    job_id, plan = _prepare(tmp_path, monkeypatch)
    build_issue_legal_context(job_id, as_of=date(2026, 8, 15), use_semantic=False)

    plan.planner_response_hash = "changed-after-retrieval"
    job_audit_plan_path(job_id).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(IssueLegalContextStaleError, match="audit-plan.json changed"):
        load_issue_legal_context(job_id)


def test_planner_and_issue_legal_context_routes_are_mounted(tmp_path: Path, monkeypatch) -> None:
    job_id, _ = _prepare(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/documents/{job_id}/audit-plan" in paths
    assert "/api/documents/{job_id}/issue-legal-context" in paths

    created = client.post(
        f"/api/documents/{job_id}/issue-legal-context",
        json={"as_of": "2026-08-15", "use_semantic": False, "top_k_per_query": 5},
    )
    assert created.status_code == 200, created.text
    assert created.json()["total_issue_count"] == 2

    loaded = client.get(f"/api/documents/{job_id}/issue-legal-context")
    assert loaded.status_code == 200
    assert loaded.json()["artifact_fingerprint"] == created.json()["artifact_fingerprint"]
