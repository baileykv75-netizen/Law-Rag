from __future__ import annotations

import importlib
import importlib.metadata as metadata
from dataclasses import asdict, dataclass

PADDLE_DISTRIBUTION = "paddlepaddle"
PADDLE_IMPORT = "paddle"
PADDLE_VERSION = "3.3.0"
PADDLEOCR_DISTRIBUTION = "paddleocr"
PADDLEOCR_IMPORT = "paddleocr"
PADDLEOCR_VERSION = "3.7.0"


@dataclass(frozen=True)
class OcrRuntimeProbe:
    ready: bool
    state: str
    paddle_version: str | None
    paddleocr_version: str | None
    modules_imported: bool
    native_check_run: bool
    detail: str
    error_type: str | None = None

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def probe_ocr_runtime(*, import_modules: bool = False, run_native_check: bool = False) -> OcrRuntimeProbe:
    """Inspect the pinned local OCR runtime without initializing OCR models.

    The shallow/default probe reads installed distribution metadata only. The
    deep probe imports Paddle/PaddleOCR and may run Paddle's local native-op
    self-check, but it never constructs ``PaddleOCR`` and therefore does not
    select, download, or load OCR model weights.
    """

    if run_native_check and not import_modules:
        raise ValueError("run_native_check requires import_modules=True")

    paddle_version = _version(PADDLE_DISTRIBUTION)
    paddleocr_version = _version(PADDLEOCR_DISTRIBUTION)
    missing = []
    if paddle_version is None:
        missing.append(PADDLE_DISTRIBUTION)
    if paddleocr_version is None:
        missing.append(PADDLEOCR_DISTRIBUTION)
    if missing:
        return OcrRuntimeProbe(
            ready=False,
            state="MISSING",
            paddle_version=paddle_version,
            paddleocr_version=paddleocr_version,
            modules_imported=False,
            native_check_run=False,
            detail=f"OCR runtime distribution(s) missing: {', '.join(missing)}.",
        )

    mismatches = []
    if paddle_version != PADDLE_VERSION:
        mismatches.append(f"paddlepaddle={paddle_version} (expected {PADDLE_VERSION})")
    if paddleocr_version != PADDLEOCR_VERSION:
        mismatches.append(f"paddleocr={paddleocr_version} (expected {PADDLEOCR_VERSION})")
    if mismatches:
        return OcrRuntimeProbe(
            ready=False,
            state="VERSION_MISMATCH",
            paddle_version=paddle_version,
            paddleocr_version=paddleocr_version,
            modules_imported=False,
            native_check_run=False,
            detail="Pinned OCR runtime version mismatch: " + "; ".join(mismatches),
        )

    if not import_modules:
        return OcrRuntimeProbe(
            ready=True,
            state="READY",
            paddle_version=paddle_version,
            paddleocr_version=paddleocr_version,
            modules_imported=False,
            native_check_run=False,
            detail="Pinned PaddlePaddle/PaddleOCR distributions are present. No model or network action was performed.",
        )

    try:
        paddle = importlib.import_module(PADDLE_IMPORT)
        importlib.import_module(PADDLEOCR_IMPORT)
        if run_native_check:
            paddle.utils.run_check()
    except Exception as exc:
        return OcrRuntimeProbe(
            ready=False,
            state="BROKEN",
            paddle_version=paddle_version,
            paddleocr_version=paddleocr_version,
            modules_imported=False,
            native_check_run=False,
            detail=f"Pinned OCR runtime failed local import/native validation: {type(exc).__name__}.",
            error_type=type(exc).__name__,
        )

    return OcrRuntimeProbe(
        ready=True,
        state="READY",
        paddle_version=paddle_version,
        paddleocr_version=paddleocr_version,
        modules_imported=True,
        native_check_run=run_native_check,
        detail=(
            "Pinned PaddlePaddle/PaddleOCR runtime imported and Paddle native self-check passed without initializing OCR models."
            if run_native_check
            else "Pinned PaddlePaddle/PaddleOCR runtime imported without initializing OCR models."
        ),
    )
