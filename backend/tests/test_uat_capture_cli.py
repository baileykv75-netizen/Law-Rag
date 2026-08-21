from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from app import uat_capture_cli
from app.uat_capture_cli import build_parser
from app.uat_capture_models import UATCaptureMode


def test_uat_capture_cli_parser_keeps_real_provider_opt_in_explicit(tmp_path: Path) -> None:
    job_id = uuid4()
    args = build_parser().parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--job-id",
            str(job_id),
            "--output",
            str(tmp_path / "observation.json"),
            "--mode",
            UATCaptureMode.REAL_PROVIDER.value,
        ]
    )

    assert args.mode == UATCaptureMode.REAL_PROVIDER.value
    assert args.confirm_real_provider_uat is False


def test_uat_capture_cli_real_provider_without_confirmation_fails_before_job_read(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    job_id = uuid4()
    output = tmp_path / "observation.json"
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "uat-capture",
            "--repo-root",
            str(repo_root),
            "--job-id",
            str(job_id),
            "--output",
            str(output),
            "--mode",
            UATCaptureMode.REAL_PROVIDER.value,
        ],
    )

    assert uat_capture_cli.main() == 2
    stdout = capsys.readouterr().out
    assert "explicit confirm_real_provider_uat=True" in stdout
    assert not output.exists()


def test_uat_capture_cli_forwards_explicit_real_provider_confirmation(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    job_id = uuid4()
    output = tmp_path / "observation.json"
    captured: dict[str, object] = {}

    class FakeReport:
        def model_dump_json(self, indent: int = 2) -> str:
            return '{"capture_mode":"REAL_PROVIDER"}'

    def fake_capture(repo_root, received_job_id, received_output, *, capture_mode, confirm_real_provider_uat):
        captured.update(
            repo_root=repo_root,
            job_id=received_job_id,
            output=received_output,
            capture_mode=capture_mode,
            confirm=confirm_real_provider_uat,
        )
        return object(), FakeReport()

    monkeypatch.setattr(uat_capture_cli, "capture_issue_v1_uat", fake_capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "uat-capture",
            "--repo-root",
            str(tmp_path),
            "--job-id",
            str(job_id),
            "--output",
            str(output),
            "--mode",
            UATCaptureMode.REAL_PROVIDER.value,
            "--confirm-real-provider-uat",
        ],
    )

    assert uat_capture_cli.main() == 0
    assert captured["job_id"] == job_id
    assert captured["output"] == output
    assert captured["capture_mode"] == UATCaptureMode.REAL_PROVIDER
    assert captured["confirm"] is True
    assert '"capture_mode":"REAL_PROVIDER"' in capsys.readouterr().out
