from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


SMOKE_LINES = (
    "LAW RAG SYNTHETIC CONTRACT AGREEMENT",
    "1. Parties Alpha Company and Beta Company enter this fictional contract for release testing only.",
    "2. Payment Buyer shall pay Seller 1000 units within 30 days after written acceptance.",
    "3. Performance Each party shall perform agreed obligations and provide written notice before material changes.",
    "4. Liability A breaching party shall compensate direct losses subject to later human review.",
    "5. Effective Date This fictional agreement is effective on 2026-08-17 and contains no private data.",
)


def _pdf_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_smoke_pdf(output_path: Path) -> Path:
    """Create a deterministic synthetic PDF with a real native text layer.

    The original Stage 11D fixture was a blank page, which was sufficient for
    parser/PDFium smoke but correctly routed to OCR by Stage 2. Stage 12F also
    needs to exercise the automatic provider boundary without bundling OCR, so
    this fixture intentionally contains enough clean ASCII contract-like text to
    pass the deterministic native-text heuristic.
    """

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )

    commands = ["BT", "/F1 10 Tf", "54 738 Td"]
    for index, line in enumerate(SMOKE_LINES):
        if index:
            commands.append("0 -26 Td")
        commands.append(f"({_pdf_literal(line)}) Tj")
    commands.append("ET")

    content = DecodedStreamObject()
    content.set_data(("\n".join(commands) + "\n").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)

    with output_path.open("wb") as handle:
        writer.write(handle)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a fictional native-text PDF for packaged release smoke tests.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(build_smoke_pdf(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
