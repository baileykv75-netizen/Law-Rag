from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.document_ingestion import classify_native_text
from app.models import PageRoute
from app.release_smoke_fixture_cli import SMOKE_LINES, build_smoke_pdf


def test_release_smoke_fixture_has_real_native_text_layer(tmp_path: Path) -> None:
    path = build_smoke_pdf(tmp_path / "smoke-native.pdf")
    reader = PdfReader(str(path))

    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text() or ""
    for expected in (SMOKE_LINES[0], "1. Parties", "5. Effective Date"):
        assert expected in text

    route, reason, non_whitespace, suspicious, meaningful_ratio = classify_native_text(text)
    assert route == PageRoute.NATIVE_TEXT_USABLE, reason
    assert non_whitespace >= 32
    assert suspicious == 0
    assert meaningful_ratio >= 0.45
