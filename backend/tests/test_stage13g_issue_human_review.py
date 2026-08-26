from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.audit_planner import run_audit_planner
from app.audit_planner_provider import FakeAuditPlannerProvider
from app.audit_rules import run_audit_rules
from app.contract_models import CanonicalContract, Clause, ExtractionConfidence, ExtractionProvenance, SourceSpan
from app.issue_legal_context import build_issue_legal_context
from app.issue_primary_audit import run_issue_primary_audit
from app.issue_review_report import build_issue_review_report
from app.issue_secondary_review import run_issue_secondary_review
from app.legal.importer import import_manifest
from app.legal.retrieval import build_retrieval_index
from app.main import app
from app.models import DocumentKind, DocumentRoute, PageEvidence, PageRoute, SourceMethod
from app.pipeline_control import set_provider_mode
from app.pipeline_control_models import ProviderExecutionMode
from app.storage import (
    job_contract_path,
    job_human_review_path,
    legal_db_path,
    legal_retrieval_index_path,
)


client = TestClient(app)


def _forbid_network(monkeypatch) -> None:
    class ForbiddenHttpClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("Issue human review regression attempted outbound HTTP.")

    monkeypatch.setattr(httpx, "Client", ForbiddenHttpClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenHttpClient)


def _contract() -> CanonicalContract:
    job_id = uuid4()
    provenance = ExtractionProvenance(
        extractor_id="stage13g-human-review-fixture",
        confidence=ExtractionConfidence.HIGH,
    )
    text = (
        "本条为甲方预先拟定条款。乙方逾期履行的，应按合同总金额的50%支付违约金；"
        "甲方对该责任限制条款负有提示说明义务。"
    )
    quote = f"第八条 违约责任\n{text}"
    span = SourceSpan(
        page_number=1,
        evidence_ids=["evidence-stage13g-human-8"],
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )
    return CanonicalContract(
        job_id=job_id,
        filename="stage13g-human-review-fixture.pdf",
        source_fingerprint="stage13g-human-review-source",
        evidence_unit_count=1,
        clauses=[
            Clause(
                clause_id="clause-008",
                heading_token="第八条",
                heading_text="违约责任",
                body_text=text,
                level=1,
                page_start=1,
                page_end=1,
                source_spans=[span],
                provenance=provenance,
            )
        ],
    )


def _seed_workspace_source(tmp_path: Path, contract: CanonicalContract) -> None:
    job_dir = tmp_path / "jobs" / str(contract.job_id)
    upload_dir = tmp_path / "uploads" / str(contract.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    quote = contract.clauses[0].source_spans[0].quote
    page = PageEvidence(
        evidence_id="evidence-stage13g-human-8",
        page_number=1,
        source_method=SourceMethod.NATIVE_PDF_TEXT,
        text=quote,
        character_count=len(quote),
        non_whitespace_count=len("".join(quote.split())),
        meaningful_ratio=1.0,
        suspicious_character_count=0,
        route=PageRoute.NATIVE_TEXT_USABLE,
        route_reason="issue human review fixture",
        source_locator="source.pdf#page=1",
    )
    document = {
        "job_id": str(contract.job_id),
        "filename": contract.filename,
        "media_type": "application/pdf",
        "document_kind": DocumentKind.PDF.value,
        "page_count": 1,
        "route": DocumentRoute.NATIVE_TEXT.value,
        "native_text_pages": 1,
        "ocr_required_pages": 0,
        "status": "inspected",
    }
    (job_dir / "document.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "evidence.json").write_text(
        json.dumps([page.model_dump(mode="json")], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.7\n% stage13g human review fixture\n")


def _run_chain(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_AI_PROVIDER", "1")
    monkeypatch.setenv("LAW_RAG_ALLOW_FAKE_ISSUE_SECONDARY", "1")
    _forbid_network(monkeypatch)

    contract = _contract()
    _seed_workspace_source(tmp_path, contract)
    job_contract_path(contract.job_id).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    run_audit_rules(contract.job_id)

    repo_root = Path(__file__).resolve().parents[2]
    import_manifest(
        repo_root / "legal_data" / "seed" / "manifest.json",
        legal_db_path(),
        rebuild=True,
    )
    build_retrieval_index(legal_db_path(), legal_retrieval_index_path())
    set_provider_mode(contract.job_id, ProviderExecutionMode.AUTO_CONTINUE)

    plan = run_audit_planner(contract.job_id, provider=FakeAuditPlannerProvider())
    legal = build_issue_legal_context(contract.job_id, as_of=date(2026, 8, 18), use_semantic=False)
    primary = run_issue_primary_audit(contract.job_id, provider_name="fake")
    secondary = run_issue_secondary_review(contract.job_id, provider_name="fake")
    report = build_issue_review_report(contract.job_id)
    return contract, plan, legal, primary, secondary, report


def _required_issue_ids(report) -> list[str]:
    return [item.issue_id for item in report.comparisons if item.requires_human_review]


def _post_issue_decision(job_id, issue_id: str, state: str = "CONFIRMED"):
    return client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "issue",
            "target_id": issue_id,
            "state": state,
            "reviewer_note": f"fixture decision for {issue_id}",
        },
    )


def test_issue_human_review_is_issue_keyed_and_server_snapshots_evidence(tmp_path: Path, monkeypatch) -> None:
    contract, plan, legal, primary, secondary, report = _run_chain(tmp_path, monkeypatch)
    job_id = contract.job_id
    required_ids = _required_issue_ids(report)
    assert required_ids

    empty = client.get(f"/api/documents/{job_id}/human-review")
    assert empty.status_code == 200, empty.text
    assert empty.json()["authoritative_architecture"] == "ISSUE_V1"
    assert empty.json()["current_review_report_artifact"] == "issue-review-report.json"
    assert empty.json()["revisions"] == []
    assert not job_human_review_path(job_id).exists()

    wrong_identity = client.post(
        f"/api/documents/{job_id}/human-review/decisions",
        json={
            "target_type": "finding",
            "target_id": "legacy-finding-invented",
            "state": "CONFIRMED",
            "reviewer_note": "must not cross architecture boundary",
        },
    )
    assert wrong_identity.status_code == 409
    assert not job_human_review_path(job_id).exists()

    issue_id = required_ids[0]
    response = _post_issue_decision(job_id, issue_id)
    assert response.status_code == 200, response.text
    body = response.json()
    revision = body["latest_by_target"][f"issue:{issue_id}"]
    assert revision["target_type"] == "issue"
    assert revision["target_id"] == issue_id
    assert revision["revision"] == 1
    assert revision["is_stale"] is False
    assert revision["review_report_fingerprint"] == report.artifact_fingerprint

    plan_issue = next(item for item in plan.issues if item.issue_id == issue_id)
    legal_issue = next(item for item in legal.issues if item.issue_id == issue_id)
    primary_issue = next(item for item in primary.results if item.issue_id == issue_id)
    secondary_issue = next(item for item in secondary.results if item.issue_id == issue_id)
    assert set(plan_issue.contract_evidence_ids).issubset(revision["contract_evidence_ids"])
    assert set(primary_issue.contract_evidence_ids).issubset(revision["contract_evidence_ids"])
    assert set(secondary_issue.contract_evidence_ids).issubset(revision["contract_evidence_ids"])
    assert {item.legal_evidence_id for item in legal_issue.legal_evidence}.issubset(revision["legal_evidence_ids"])


def test_workspace_closes_mandatory_issue_review_only_after_fresh_final_decisions(tmp_path: Path, monkeypatch) -> None:
    contract, _, _, _, _, report = _run_chain(tmp_path, monkeypatch)
    job_id = contract.job_id
    required_ids = _required_issue_ids(report)
    assert required_ids

    before = client.get(f"/api/documents/{job_id}/workspace")
    assert before.status_code == 200, before.text
    before_body = before.json()
    assert before_body["overall_state"] == "HUMAN_REVIEW_REQUIRED"
    assert before_body["review"]["human_review_outstanding_required_count"] == len(required_ids)
    assert {item["stage"]: item for item in before_body["stages"]}["13G.6"]["state"] == "MISSING"

    for issue_id in required_ids:
        saved = _post_issue_decision(job_id, issue_id)
        assert saved.status_code == 200, saved.text

    after = client.get(f"/api/documents/{job_id}/workspace")
    assert after.status_code == 200, after.text
    after_body = after.json()
    assert after_body["review"]["human_review_resolved_required_count"] == len(required_ids)
    assert after_body["review"]["human_review_outstanding_required_count"] == 0
    assert {item["stage"]: item for item in after_body["stages"]}["13G.6"]["state"] == "READY"
    assert after_body["overall_state"] == "COMPLETE"
    issue_rows = {item["issue_id"]: item for item in after_body["issues"]}
    for issue_id in required_ids:
        assert issue_rows[issue_id]["human_decision_state"] == "CONFIRMED"
        assert issue_rows[issue_id]["human_decision_stale"] is False


def test_issue_handling_decision_new_statuses_are_resolved(tmp_path: Path, monkeypatch) -> None:
    contract, _, _, _, _, report = _run_chain(tmp_path, monkeypatch)
    job_id = contract.job_id
    issue_id = _required_issue_ids(report)[0]

    saved = _post_issue_decision(job_id, issue_id, state="MODIFIED")

    assert saved.status_code == 200, saved.text
    assert saved.json()["latest_by_target"][f"issue:{issue_id}"]["state"] == "MODIFIED"
    workspace = client.get(f"/api/documents/{job_id}/workspace")
    assert workspace.status_code == 200, workspace.text
    body = workspace.json()
    assert body["review"]["human_review_outstanding_required_count"] == len(_required_issue_ids(report)) - 1



def test_issue_revision_becomes_stale_after_a_valid_new_issue_report(tmp_path: Path, monkeypatch) -> None:
    contract, _, _, _, _, report = _run_chain(tmp_path, monkeypatch)
    job_id = contract.job_id
    issue_id = _required_issue_ids(report)[0]

    saved = _post_issue_decision(job_id, issue_id)
    assert saved.status_code == 200, saved.text
    old_fingerprint = saved.json()["current_review_report_fingerprint"]

    # Produce a complete, fresh successor Stage 13D-G chain with a different as_of.
    build_issue_legal_context(job_id, as_of=date(2026, 8, 19), use_semantic=False)
    run_issue_primary_audit(job_id, provider_name="fake")
    run_issue_secondary_review(job_id, provider_name="fake")
    new_report = build_issue_review_report(job_id)
    assert new_report.artifact_fingerprint != old_fingerprint

    refreshed = client.get(f"/api/documents/{job_id}/human-review")
    assert refreshed.status_code == 200, refreshed.text
    stale = refreshed.json()["latest_by_target"][f"issue:{issue_id}"]
    assert stale["is_stale"] is True

    workspace = client.get(f"/api/documents/{job_id}/workspace")
    assert workspace.status_code == 200, workspace.text
    workspace_body = workspace.json()
    assert workspace_body["review"]["human_review_stale_latest_count"] >= 1
    assert workspace_body["review"]["human_review_outstanding_required_count"] > 0
    assert workspace_body["overall_state"] == "HUMAN_REVIEW_REQUIRED"


def test_historical_legacy_revision_stays_readable_and_stale_in_issue_v1_artifact(tmp_path: Path, monkeypatch) -> None:
    contract, _, _, _, _, report = _run_chain(tmp_path, monkeypatch)
    job_id = contract.job_id
    issue_id = _required_issue_ids(report)[0]

    legacy_revision = {
        "schema_version": "1.0.0",
        "decision_id": "human-legacy-preserved",
        "revision": 1,
        "job_id": str(job_id),
        "target_type": "finding",
        "target_id": "finding-legacy-001",
        "state": "CONFIRMED",
        "reviewer_note": "preserved RC2 decision",
        "decided_at": "2026-08-17T00:00:00Z",
        "contract_evidence_ids": ["legacy-contract-evidence"],
        "legal_evidence_ids": ["legacy-legal-evidence"],
        "review_report_fingerprint": "a" * 64,
    }
    path = job_human_review_path(job_id)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "job_id": str(job_id),
                "revisions": [legacy_revision],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    historical = client.get(f"/api/documents/{job_id}/human-review")
    assert historical.status_code == 200, historical.text
    historical_body = historical.json()
    old = historical_body["latest_by_target"]["finding:finding-legacy-001"]
    assert old["target_type"] == "finding"
    assert old["target_id"] == "finding-legacy-001"
    assert old["is_stale"] is True

    added = _post_issue_decision(job_id, issue_id)
    assert added.status_code == 200, added.text
    revisions = added.json()["revisions"]
    assert len(revisions) == 2
    assert revisions[0]["decision_id"] == "human-legacy-preserved"
    assert revisions[0]["target_type"] == "finding"
    assert revisions[0]["target_id"] == "finding-legacy-001"
    assert revisions[1]["target_type"] == "issue"
    assert revisions[1]["target_id"] == issue_id
