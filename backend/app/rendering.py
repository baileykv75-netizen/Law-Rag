from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PdfRenderError(RuntimeError):
    pass


class PdfPageRenderer(Protocol):
    def render_page(self, source_pdf: Path, page_number: int, output_path: Path) -> Path:
        """Render one 1-based PDF page to an image and return the output path."""
        ...


class PdfiumPageRenderer:
    """Render one PDF page with pypdfium2/PDFium.

    A scale of 2.0 corresponds to roughly 144 DPI for standard PDF points and
    is the Stage 3 CPU-friendly default. OCR callers render only pages already
    routed to OCR_REQUIRED.
    """

    def __init__(self, scale: float = 2.0) -> None:
        if scale <= 0:
            raise ValueError("PDF render scale must be positive.")
        self.scale = scale

    def render_page(self, source_pdf: Path, page_number: int, output_path: Path) -> Path:
        if page_number < 1:
            raise PdfRenderError("PDF page numbers are 1-based and must be positive.")

        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover - guarded by installed base dependency
            raise PdfRenderError(
                "pypdfium2 is not installed; PDF OCR pages cannot be rendered."
            ) from exc

        document = None
        page = None
        bitmap = None
        image = None
        try:
            document = pdfium.PdfDocument(str(source_pdf))
            page_index = page_number - 1
            if page_index >= len(document):
                raise PdfRenderError(
                    f"PDF page {page_number} does not exist; document has {len(document)} pages."
                )

            page = document[page_index]
            bitmap = page.render(scale=self.scale)
            image = bitmap.to_pil()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, format="PNG")
            return output_path
        except PdfRenderError:
            raise
        except Exception as exc:
            raise PdfRenderError(f"Failed to render PDF page {page_number}.") from exc
        finally:
            for resource in (image, bitmap, page, document):
                close = getattr(resource, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
