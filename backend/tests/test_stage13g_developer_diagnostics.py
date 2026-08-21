from __future__ import annotations

from app.main import app


READ_ONLY_DIAGNOSTIC_PATHS = (
    "/api/documents/{job_id}/architecture",
    "/api/documents/{job_id}/pipeline",
    "/api/documents/{job_id}/audit-plan",
    "/api/documents/{job_id}/issue-legal-context",
    "/api/documents/{job_id}/issue-primary-audit",
    "/api/documents/{job_id}/issue-secondary-review",
    "/api/documents/{job_id}/issue-review-report",
    "/api/documents/{job_id}/human-review",
)


def test_stage13g_developer_diagnostics_have_get_routes_for_every_authoritative_artifact() -> None:
    paths = app.openapi()["paths"]
    for path in READ_ONLY_DIAGNOSTIC_PATHS:
        assert path in paths, path
        assert "get" in paths[path], f"Developer diagnostic endpoint must remain GET-readable: {path}"


def test_stage13g_issue_artifact_get_operations_are_distinct_from_provider_execution_posts() -> None:
    """The Developer UI binds only GET methods; model execution remains an explicit POST action."""

    paths = app.openapi()["paths"]
    issue_paths = READ_ONLY_DIAGNOSTIC_PATHS[2:7]
    for path in issue_paths:
        get_operation = paths[path]["get"]
        assert get_operation["operationId"]
        # POST may exist on the same resource for explicit execution, but GET must
        # remain separately addressable so diagnostic reads never need to invoke it.
        if "post" in paths[path]:
            assert paths[path]["post"]["operationId"] != get_operation["operationId"]
