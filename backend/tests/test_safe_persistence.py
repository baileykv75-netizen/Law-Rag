from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.safe_persistence import AtomicWriteError, atomic_write_text
from app.storage import job_audit_rules_path, job_contract_path


def test_atomic_write_preserves_previous_file_when_replace_fails(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "artifact.json"
    target.write_text('{"version":"old"}', encoding="utf-8")
    previous = target.read_bytes()

    def fail_replace(src, dst):
        raise OSError("simulated interrupted replace")

    monkeypatch.setattr("app.safe_persistence.os.replace", fail_replace)

    with pytest.raises(AtomicWriteError, match="Atomic write failed"):
        atomic_write_text(target, '{"version":"new"}')

    assert target.read_bytes() == previous
    assert not list(tmp_path.glob(".artifact.json.*.tmp"))


def test_contract_and_rule_paths_use_atomic_write_without_leaving_temp_residue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LAW_RAG_RUNTIME_DIR", str(tmp_path / "runtime"))
    job_id = uuid4()
    contract = job_contract_path(job_id)
    rules = job_audit_rules_path(job_id)

    contract.write_text('{"kind":"contract"}', encoding="utf-8")
    rules.write_text('{"kind":"rules"}', encoding="utf-8")

    assert contract.read_text(encoding="utf-8") == '{"kind":"contract"}'
    assert rules.read_text(encoding="utf-8") == '{"kind":"rules"}'
    assert not list(contract.parent.glob(".*.tmp"))
