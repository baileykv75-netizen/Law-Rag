from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.ocr import PaddleOcrProvider


@pytest.mark.ocr_smoke
def test_real_paddleocr_adapter_on_local_image() -> None:
    """Opt-in integration smoke test; intentionally skipped by normal CI.

    Set LAW_RAG_OCR_SMOKE_IMAGE to a local PNG/JPG containing readable text
    after running setup-ocr-cpu.bat. The test verifies the real PaddleOCR
    adapter/model path rather than the deterministic fake provider used by CI.
    """

    configured = os.getenv("LAW_RAG_OCR_SMOKE_IMAGE")
    if not configured:
        pytest.skip("Set LAW_RAG_OCR_SMOKE_IMAGE to run the real PaddleOCR smoke test.")

    image_path = Path(configured).expanduser().resolve()
    if not image_path.exists():
        pytest.fail(f"Smoke-test image does not exist: {image_path}")

    provider = PaddleOcrProvider()
    blocks = provider.recognize(image_path, page_number=1)

    assert blocks, "PaddleOCR ran but returned no recognized text blocks."
    assert any(block.text.strip() for block in blocks)
