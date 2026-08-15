from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PdfPageRenderer(Protocol):
    """Boundary for future PDF-to-image rendering used by OCR.

    Stage 2 intentionally provides only the interface. A concrete renderer will
    be selected later after capability, licensing, Windows packaging, and OCR
    integration requirements are evaluated.
    """

    def render_page(self, source_pdf: Path, page_number: int, output_path: Path) -> Path:
        """Render one 1-based PDF page to an image and return the output path."""
        ...
