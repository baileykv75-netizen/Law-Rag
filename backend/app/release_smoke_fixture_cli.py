from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfWriter


def build_smoke_pdf(output_path: Path) -> Path:
    """Create one synthetic blank PDF page for packaged native-PDF/PDFium smoke tests."""

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with output_path.open("wb") as handle:
        writer.write(handle)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a fictional public PDF for Stage 11D packaged smoke tests.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(build_smoke_pdf(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
