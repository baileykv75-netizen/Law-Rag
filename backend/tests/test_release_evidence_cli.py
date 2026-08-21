from __future__ import annotations

import sys

from app import release_evidence_cli
from app.release_evidence_models import Stage16ReleaseEvidenceMatrix


def _report(*, engineering_ready: bool, evidence_complete: bool) -> Stage16ReleaseEvidenceMatrix:
    return Stage16ReleaseEvidenceMatrix(
        engineering_ready=engineering_ready,
        stage16_evidence_complete=evidence_complete,
        pending_evidence_classes=[] if evidence_complete else ["PRIVATE_EXPERT", "REAL_PROVIDER_UAT"],
        evidence=[],
        warnings=[],
    )


def test_cli_default_allows_engineering_ready_with_external_evidence_pending(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        release_evidence_cli,
        "_run",
        lambda _args, _work_dir: _report(engineering_ready=True, evidence_complete=False),
    )
    monkeypatch.setattr(sys, "argv", ["release-evidence"])

    assert release_evidence_cli.main() == 0
    stdout = capsys.readouterr().out
    assert '"engineering_ready": true' in stdout
    assert '"stage16_evidence_complete": false' in stdout


def test_cli_require_complete_evidence_blocks_pending_external_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        release_evidence_cli,
        "_run",
        lambda _args, _work_dir: _report(engineering_ready=True, evidence_complete=False),
    )
    monkeypatch.setattr(sys, "argv", ["release-evidence", "--require-complete-evidence"])

    assert release_evidence_cli.main() == 1


def test_cli_require_complete_evidence_passes_when_matrix_is_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        release_evidence_cli,
        "_run",
        lambda _args, _work_dir: _report(engineering_ready=True, evidence_complete=True),
    )
    monkeypatch.setattr(sys, "argv", ["release-evidence", "--require-complete-evidence"])

    assert release_evidence_cli.main() == 0


def test_cli_fails_when_public_engineering_evidence_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        release_evidence_cli,
        "_run",
        lambda _args, _work_dir: _report(engineering_ready=False, evidence_complete=False),
    )
    monkeypatch.setattr(sys, "argv", ["release-evidence"])

    assert release_evidence_cli.main() == 1
