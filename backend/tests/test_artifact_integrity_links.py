from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.artifact_integrity import inspect_job_artifact_integrity
from app.artifact_integrity_models import ArtifactIntegrityState
from app.audit_rule_models import AuditProfile, AuditRuleReport, RuleCounts
from app.contract_models import CanonicalContract


def test_individually_valid_contract_and_rules_with_different_source_fingerprint_are_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    job_id = uuid4()
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path))
    upload_dir = tmp_path / "uploads" / str(job_id)
    upload_dir.mkdir(parents=True)
    (upload_dir / "source.pdf").write_bytes(b"%PDF-1.4 fictional")
    job_dir = tmp_path / "jobs" / str(job_id)
    job_dir.mkdir(parents=True)

    contract = CanonicalContract(
        job_id=job_id,
        filename="fictional.pdf",
        source_fingerprint="source-A",
        evidence_unit_count=0,
    )
    rules = AuditRuleReport(
        job_id=job_id,
        contract_schema_version=contract.schema_version,
        contract_source_fingerprint="source-B",
        contract_content_fingerprint="content-B",
        profile=AuditProfile(
            profile_id="integrity-fixture",
            version="1.0.0",
            title="Integrity fixture",
        ),
        counts=RuleCounts(total=0, passed=0, failed=0, review=0, not_applicable=0),
    )
    (job_dir / "contract.json").write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    (job_dir / "audit-rules.json").write_text(rules.model_dump_json(indent=2), encoding="utf-8")

    report = inspect_job_artifact_integrity(job_id)
    link = next(item for item in report.links if item.link_id == "contract-to-rules-source")

    assert link.state == ArtifactIntegrityState.MISMATCH
    assert report.all_present_artifacts_valid is False
    assert report.action_required is True
