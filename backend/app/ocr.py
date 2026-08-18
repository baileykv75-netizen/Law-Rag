from __future__ import annotations

import importlib.metadata
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from PIL import Image

from .models import (
    DocumentInspection,
    DocumentKind,
    OcrBlockEvidence,
    OcrPageEvidence,
    OcrPageState,
    OcrRunResult,
    PageRoute,
    SourceMethod,
)
from .ocr_models import (
    OcrModelIntegrityError,
    OcrPipelineConfigError,
    resolve_ocr_model_paths,
    resolve_ocr_pipeline_config_path,
)
from .rendering import PdfPageRenderer, PdfRenderError, PdfiumPageRenderer
from .storage import (
    find_source_path,
    job_document_path,
    job_evidence_path,
    job_ocr_path,
    job_rendered_dir,
)

LOW_CONFIDENCE_THRESHOLD = 0.85
DEFAULT_PADDLE_DETECTION_MODEL = "PP-OCRv6_medium_det"
DEFAULT_PADDLE_RECOGNITION_MODEL = "PP-OCRv6_medium_rec"


class OcrProviderUnavailable(RuntimeError):
    pass


class OcrProviderError(RuntimeError):
    pass


class OcrProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderOcrBlock:
    text: str
    confidence: float | None
    bbox: list[int] | None
    polygon: list[list[int]] | None


class OcrProvider(Protocol):
    provider_name: str
    model_name: str
    provider_version: str

    def recognize(self, image_path: Path, page_number: int) -> list[ProviderOcrBlock]:
        ...


def _python_value(value: Any) -> Any:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    return value


def _mapping_get(candidate: Any, key: str) -> Any:
    if isinstance(candidate, Mapping):
        if key in candidate:
            return candidate[key]
        nested = candidate.get("res")
        if isinstance(nested, Mapping) and key in nested:
            return nested[key]

    try:
        return candidate[key]
    except Exception:
        pass

    try:
        nested = candidate["res"]
        return nested[key]
    except Exception:
        pass

    json_value = getattr(candidate, "json", None)
    if callable(json_value):
        try:
            json_value = json_value()
        except Exception:
            json_value = None
    if isinstance(json_value, str):
        try:
            json_value = json.loads(json_value)
        except json.JSONDecodeError:
            json_value = None
    if isinstance(json_value, Mapping):
        if key in json_value:
            return json_value[key]
        nested = json_value.get("res")
        if isinstance(nested, Mapping):
            return nested.get(key)
    return None


def _normalize_polygon(value: Any) -> list[list[int]] | None:
    value = _python_value(value)
    if not isinstance(value, (list, tuple)) or not value:
        return None
    points: list[list[int]] = []
    for point in value:
        point = _python_value(point)
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            points.append([int(round(float(point[0]))), int(round(float(point[1])))])
        except (TypeError, ValueError):
            return None
    return points or None


def _normalize_bbox(value: Any) -> list[int] | None:
    value = _python_value(value)
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return [int(round(float(value[index]))) for index in range(4)]
    except (TypeError, ValueError):
        return None


def _bbox_from_polygon(polygon: list[list[int]] | None) -> list[int] | None:
    if not polygon:
        return None
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


class PaddleOcrProvider:
    """Provider-neutral adapter around the verified local PaddleOCR pipeline.

    Paddle-specific imports and result-shape normalization remain inside this
    adapter. The pipeline is initialized lazily so native-text-only documents
    do not pay OCR startup cost. The production path accepts only the pinned,
    SHA-256-verified local model directories and Law-Rag's fixed PaddleX OCR
    pipeline config; it never asks PaddleOCR/PaddleX to resolve or download
    model weights.
    """

    provider_name = "paddleocr"

    def __init__(
        self,
        *,
        pipeline_factory: Callable[[], Any] | None = None,
        provider_version: str | None = None,
        detection_model_name: str = DEFAULT_PADDLE_DETECTION_MODEL,
        recognition_model_name: str = DEFAULT_PADDLE_RECOGNITION_MODEL,
        model_root: Path | None = None,
        model_manifest_path: Path | None = None,
        pipeline_config_path: Path | None = None,
    ) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None
        self._model_root = model_root
        self._model_manifest_path = model_manifest_path
        self._pipeline_config_path = pipeline_config_path
        self.detection_model_name = detection_model_name
        self.recognition_model_name = recognition_model_name
        self.model_name = f"{detection_model_name}+{recognition_model_name}"
        if provider_version is not None:
            self.provider_version = provider_version
        else:
            try:
                self.provider_version = importlib.metadata.version("paddleocr")
            except importlib.metadata.PackageNotFoundError:
                self.provider_version = "not-installed"

    def _build_pipeline(self) -> Any:
        if self._pipeline_factory is not None:
            return self._pipeline_factory()

        if (
            self.detection_model_name != DEFAULT_PADDLE_DETECTION_MODEL
            or self.recognition_model_name != DEFAULT_PADDLE_RECOGNITION_MODEL
        ):
            raise OcrProviderUnavailable(
                "The packaged OCR path only permits the pinned PP-OCRv6 medium detection and recognition models."
            )

        try:
            model_paths = resolve_ocr_model_paths(
                model_root=self._model_root,
                manifest_path=self._model_manifest_path,
            )
            pipeline_config_path = resolve_ocr_pipeline_config_path(
                config_path=self._pipeline_config_path,
            )
        except (OcrModelIntegrityError, OcrPipelineConfigError) as exc:
            raise OcrProviderUnavailable(str(exc)) from exc

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrProviderUnavailable(
                "The packaged PaddleOCR runtime is missing or broken. Reinstall the verified Law-Rag Windows bundle."
            ) from exc

        try:
            return PaddleOCR(
                paddlex_config=str(pipeline_config_path),
                text_detection_model_name=self.detection_model_name,
                text_detection_model_dir=str(model_paths.detection),
                text_recognition_model_name=self.recognition_model_name,
                text_recognition_model_dir=str(model_paths.recognition),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
                engine="paddle_static",
            )
        except Exception as exc:
            raise OcrProviderUnavailable(
                "PaddleOCR could not initialize with the verified packaged local model assets and fixed OCR pipeline config."
            ) from exc

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            self._pipeline = self._build_pipeline()
        return self._pipeline

    def recognize(self, image_path: Path, page_number: int) -> list[ProviderOcrBlock]:
        try:
            predictions = list(self._get_pipeline().predict(str(image_path)))
        except OcrProviderUnavailable:
            raise
        except Exception as exc:
            raise OcrProviderError(f"PaddleOCR failed on page {page_number}.") from exc

        blocks: list[ProviderOcrBlock] = []
        for prediction in predictions:
            texts = _python_value(_mapping_get(prediction, "rec_texts")) or []
            scores = _python_value(_mapping_get(prediction, "rec_scores")) or []
            boxes = _python_value(_mapping_get(prediction, "rec_boxes")) or []
            polygons = _python_value(_mapping_get(prediction, "rec_polys")) or []

            for index, raw_text in enumerate(texts):
                text = str(raw_text).strip()
                if not text:
                    continue

                confidence: float | None = None
                if index < len(scores):
                    try:
                        confidence = max(0.0, min(1.0, float(scores[index])))
                    except (TypeError, ValueError):
                        confidence = None

                polygon = _normalize_polygon(polygons[index]) if index < len(polygons) else None
                bbox = _normalize_bbox(boxes[index]) if index < len(boxes) else None
                if bbox is None:
                    bbox = _bbox_from_polygon(polygon)

                blocks.append(
                    ProviderOcrBlock(
                        text=text,
                        confidence=confidence,
                        bbox=bbox,
                        polygon=polygon,
                    )
                )
        return blocks


def _load_inspection(job_id: UUID) -> DocumentInspection:
    document_path = job_document_path(job_id)
    evidence_path = job_evidence_path(job_id)
    if not document_path.exists() or not evidence_path.exists():
        raise OcrProcessingError(f"Document job {job_id} does not exist or is incomplete.")

    try:
        document_payload = json.loads(document_path.read_text(encoding="utf-8"))
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        return DocumentInspection.model_validate({**document_payload, "pages": evidence_payload})
    except Exception as exc:
        raise OcrProcessingError("Persisted document evidence could not be loaded safely.") from exc


def _image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            return int(width), int(height)
    except Exception as exc:
        raise OcrProcessingError(f"Could not read OCR source image {path.name}.") from exc


def _source_locator(page_number: int, bbox: list[int] | None) -> str:
    if bbox:
        return f"page:{page_number};pixel_bbox:{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    return f"page:{page_number}"


def _block_evidence(
    *,
    job_id: UUID,
    page_number: int,
    block_index: int,
    block: ProviderOcrBlock,
    provider: OcrProvider,
) -> OcrBlockEvidence:
    low_confidence = block.confidence is None or block.confidence < LOW_CONFIDENCE_THRESHOLD
    if block.confidence is None:
        reason = "OCR provider did not return a recognition confidence."
    elif low_confidence:
        reason = (
            f"Recognition confidence {block.confidence:.3f} is below the Stage 3 review threshold "
            f"of {LOW_CONFIDENCE_THRESHOLD:.2f}."
        )
    else:
        reason = None

    return OcrBlockEvidence(
        evidence_id=f"ocr-{job_id}-p{page_number:04d}-b{block_index:04d}",
        page_number=page_number,
        block_index=block_index,
        text=block.text,
        confidence=block.confidence,
        bbox=block.bbox,
        polygon=block.polygon,
        provider=provider.provider_name,
        model=provider.model_name,
        provider_version=provider.provider_version,
        low_confidence=low_confidence,
        low_confidence_reason=reason,
        source_locator=_source_locator(page_number, block.bbox),
    )


def _persist_ocr(result: OcrRunResult) -> None:
    job_ocr_path(result.job_id).write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_ocr_for_job(
    job_id: UUID,
    *,
    provider: OcrProvider | None = None,
    renderer: PdfPageRenderer | None = None,
) -> OcrRunResult:
    inspection = _load_inspection(job_id)
    source_path = find_source_path(job_id)
    ocr_pages = [page for page in inspection.pages if page.route == PageRoute.OCR_REQUIRED]

    active_provider: OcrProvider
    if provider is not None:
        active_provider = provider
    elif ocr_pages:
        active_provider = PaddleOcrProvider()
    else:
        class _NoopProvider:
            provider_name = "none"
            model_name = "not-required"
            provider_version = "n/a"

            def recognize(self, image_path: Path, page_number: int) -> list[ProviderOcrBlock]:
                return []

        active_provider = _NoopProvider()

    active_renderer = renderer or PdfiumPageRenderer()
    pages: list[OcrPageEvidence] = []

    for page in inspection.pages:
        if page.route == PageRoute.NATIVE_TEXT_USABLE:
            pages.append(
                OcrPageEvidence(
                    page_number=page.page_number,
                    state=OcrPageState.NATIVE_RETAINED,
                    source_method=SourceMethod.NATIVE_PDF_TEXT,
                    text=page.text,
                    native_evidence_id=page.evidence_id,
                )
            )
            continue

        source_image: Path | None = None
        try:
            if inspection.document_kind == DocumentKind.IMAGE:
                source_image = source_path
                source_image_locator = "source-image"
            else:
                source_image = job_rendered_dir(job_id) / f"page-{page.page_number:04d}.png"
                active_renderer.render_page(source_path, page.page_number, source_image)
                source_image_locator = f"rendered/page-{page.page_number:04d}.png"

            width, height = _image_size(source_image)
            provider_blocks = active_provider.recognize(source_image, page.page_number)
            blocks = [
                _block_evidence(
                    job_id=job_id,
                    page_number=page.page_number,
                    block_index=index,
                    block=block,
                    provider=active_provider,
                )
                for index, block in enumerate(provider_blocks, start=1)
            ]

            if not blocks:
                pages.append(
                    OcrPageEvidence(
                        page_number=page.page_number,
                        state=OcrPageState.OCR_NO_TEXT,
                        source_method=SourceMethod.OCR,
                        text="",
                        source_image_locator=source_image_locator,
                        width_px=width,
                        height_px=height,
                        error="OCR completed but returned no recognized text.",
                    )
                )
                continue

            low_count = sum(block.low_confidence for block in blocks)
            confidences = [block.confidence for block in blocks if block.confidence is not None]
            mean_confidence = sum(confidences) / len(confidences) if confidences else None
            state = (
                OcrPageState.OCR_LOW_CONFIDENCE
                if low_count
                else OcrPageState.OCR_COMPLETE
            )
            pages.append(
                OcrPageEvidence(
                    page_number=page.page_number,
                    state=state,
                    source_method=SourceMethod.OCR,
                    text="\n".join(block.text for block in blocks),
                    source_image_locator=source_image_locator,
                    width_px=width,
                    height_px=height,
                    blocks=blocks,
                    mean_confidence=mean_confidence,
                    low_confidence_blocks=low_count,
                )
            )
        except OcrProviderUnavailable:
            raise
        except (OcrProviderError, PdfRenderError, OcrProcessingError, OSError) as exc:
            pages.append(
                OcrPageEvidence(
                    page_number=page.page_number,
                    state=OcrPageState.OCR_FAILED,
                    source_method=SourceMethod.OCR,
                    text="",
                    source_image_locator=(source_image.name if source_image else None),
                    error=str(exc),
                )
            )
        except Exception as exc:
            pages.append(
                OcrPageEvidence(
                    page_number=page.page_number,
                    state=OcrPageState.OCR_FAILED,
                    source_method=SourceMethod.OCR,
                    text="",
                    source_image_locator=(source_image.name if source_image else None),
                    error=f"Unexpected OCR processing failure: {type(exc).__name__}.",
                )
            )

    native_pages = sum(page.state == OcrPageState.NATIVE_RETAINED for page in pages)
    complete_pages = sum(
        page.state in {OcrPageState.OCR_COMPLETE, OcrPageState.OCR_LOW_CONFIDENCE}
        for page in pages
    )
    low_pages = sum(page.state == OcrPageState.OCR_LOW_CONFIDENCE for page in pages)
    failed_pages = sum(page.state == OcrPageState.OCR_FAILED for page in pages)
    no_text_pages = sum(page.state == OcrPageState.OCR_NO_TEXT for page in pages)
    attempted = len(ocr_pages)

    if attempted and failed_pages == attempted and native_pages == 0:
        run_status = "failed"
    elif failed_pages or no_text_pages:
        run_status = "partial"
    else:
        run_status = "complete"

    result = OcrRunResult(
        job_id=job_id,
        provider=active_provider.provider_name,
        model=active_provider.model_name,
        provider_version=active_provider.provider_version,
        status=run_status,
        page_count=inspection.page_count,
        native_pages=native_pages,
        ocr_pages_attempted=attempted,
        ocr_pages_complete=complete_pages,
        low_confidence_pages=low_pages,
        failed_pages=failed_pages,
        no_text_pages=no_text_pages,
        pages=pages,
    )
    _persist_ocr(result)
    return result