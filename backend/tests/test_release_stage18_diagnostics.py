from __future__ import annotations

from app.release_stage18_diagnostics import diagnose_packaged_report_renderers


def test_report_renderer_diagnostic_exercises_docx_and_pdf_without_network() -> None:
    payload = diagnose_packaged_report_renderers()

    assert payload["ready"] is True
    assert payload["network_used"] is False
    assert payload["synthetic_only"] is True
    assert payload["report_engine_version"] == "stage18.2-1.0.0"

    docx = payload["docx"]
    pdf = payload["pdf"]
    assert docx["ready"] is True
    assert pdf["ready"] is True
    assert docx["size_bytes"] > 0
    assert pdf["size_bytes"] > 0
    assert docx["signature"] == "504b0304"
    assert pdf["signature"] == "%PDF"
    assert len(docx["sha256"]) == 64
    assert len(pdf["sha256"]) == 64
