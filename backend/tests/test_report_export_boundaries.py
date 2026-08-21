from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.report_export as report_export
from app.report_export import ReportExportError
from app.workspace_models import WorkspaceOverallState


def _items(*ids: str):
    return [SimpleNamespace(issue_id=value) for value in ids]


def test_report_rejects_duplicate_issue_identity() -> None:
    plan = SimpleNamespace(issues=_items("ISSUE-1", "ISSUE-1"))
    legal = SimpleNamespace(issues=_items("ISSUE-1"))
    primary = SimpleNamespace(results=_items("ISSUE-1"))
    secondary = SimpleNamespace(results=_items("ISSUE-1"))
    review = SimpleNamespace(comparisons=_items("ISSUE-1"))

    with pytest.raises(ReportExportError, match="duplicate Issue IDs"):
        report_export._assert_exact_issue_coverage(plan, legal, primary, secondary, review)


def test_report_rejects_missing_or_extra_issue_identity() -> None:
    plan = SimpleNamespace(issues=_items("ISSUE-1", "ISSUE-2"))
    legal = SimpleNamespace(issues=_items("ISSUE-1", "ISSUE-2"))
    primary = SimpleNamespace(results=_items("ISSUE-1"))
    secondary = SimpleNamespace(results=_items("ISSUE-1", "ISSUE-2"))
    review = SimpleNamespace(comparisons=_items("ISSUE-1", "ISSUE-2"))

    with pytest.raises(ReportExportError, match="does not exactly cover"):
        report_export._assert_exact_issue_coverage(plan, legal, primary, secondary, review)


def test_incomplete_workspace_is_rejected_before_artifact_read(monkeypatch) -> None:
    job_id = uuid4()
    workspace = SimpleNamespace(overall_state=WorkspaceOverallState.INCOMPLETE)
    monkeypatch.setattr(report_export, "load_issue_workspace_summary", lambda _: workspace)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("authoritative artifact loader must not run for incomplete workspace")

    monkeypatch.setattr(report_export, "load_contract_structure", forbidden)

    with pytest.raises(ReportExportError, match="validated ISSUE_V1 comparison state"):
        report_export.build_audit_report(job_id)
