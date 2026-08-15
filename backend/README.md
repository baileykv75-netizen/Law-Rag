# Backend

The backend is the local Python/FastAPI application for Law-Rag.

Backend responsibilities include local HTTP endpoints, job creation, validation, document ingestion, OCR evidence processing, local persistence access, and stable interfaces to later RAG/rule/LLM components.

Provider-specific SDK details remain behind adapters rather than leaking through endpoint/domain code.

## Stage 2 document ingestion

`POST /api/documents`:

```text
validate upload
  -> store source under ignored runtime/uploads/<job-id>/
  -> classify PDF vs image
  -> PDF: inspect each page with pypdf
  -> image: mark OCR_REQUIRED
  -> persist document summary + page evidence under runtime/jobs/<job-id>/
  -> return route summary to the local UI
```

### PDF routing heuristic

A PDF page is marked `NATIVE_TEXT_USABLE` only when the deterministic Stage 2 heuristic considers its native text sufficiently usable. Otherwise it is marked `OCR_REQUIRED`.

The current thresholds are:

- at least 32 non-whitespace characters;
- suspicious/replacement characters no more than 2% of non-whitespace characters;
- at least 45% alphanumeric/meaningful characters.

These thresholds are routing heuristics, not accuracy guarantees.

## Stage 3 OCR evidence layer

`POST /api/documents/{job_id}/ocr` runs OCR only for pages already marked `OCR_REQUIRED`.

```text
NATIVE_TEXT_USABLE page
  -> retain existing native evidence

OCR_REQUIRED PDF page
  -> render only that page with pypdfium2/PDFium
  -> run OCR provider
  -> preserve text + confidence + bbox/polygon + provider provenance

image document
  -> OCR original image
```

The concrete Stage 3 provider is local PaddleOCR behind the `OcrProvider` protocol. Paddle-specific imports and result normalization live in `app/ocr.py`; FastAPI and document-domain code do not depend on Paddle SDK objects.

### OCR evidence

OCR results are persisted under:

```text
runtime/jobs/<job-id>/ocr.json
runtime/rendered/<job-id>/page-0001.png   # only PDF pages that require OCR
```

Each OCR block retains:

- stable block evidence ID;
- 1-based page number;
- recognized text;
- recognition confidence when supplied;
- rectangle and polygon coordinates when supplied;
- provider/model/version provenance;
- low-confidence flag/reason;
- pixel source locator.

The current review threshold is `0.85`. A block below this threshold, or a block without a provider confidence, is explicitly marked low-confidence. This threshold is only a review-routing rule and must not be interpreted as a calibrated probability that the text is correct.

### PDF renderer

Stage 3 uses `pypdfium2==5.12.1` with a default render scale of `2.0` (roughly 144 DPI for standard PDF points). Native-text pages are not rendered by default.

### Optional OCR installation on Windows

Base Law-Rag setup does not install PaddleOCR because electronic/native-text PDFs should remain usable without heavyweight OCR dependencies.

First run:

```text
setup-dev.bat
```

Then install the local CPU OCR runtime from the repository root:

```text
setup-ocr-cpu.bat
```

That script installs:

- PaddlePaddle CPU 3.3.0 from the official PaddlePaddle CPU index;
- PaddleOCR 3.7.0.

PaddleOCR models are downloaded on first OCR use. If the default model source is inaccessible, set the environment variable below before starting Law-Rag:

```text
PADDLE_PDX_MODEL_SOURCE=BOS
```

### Real PaddleOCR smoke test

Normal CI intentionally does not download OCR models. After the OCR runtime is installed, an opt-in real-provider smoke test can be run against a local test image:

```bat
cd backend
set PYTHONPATH=.
set LAW_RAG_OCR_SMOKE_IMAGE=C:\path\to\fictional-test-image.png
..\.venv\Scripts\python.exe -m pytest -q -m ocr_smoke
```

Use only fictional or appropriately private/local test material. The test image is never committed automatically.

## Local run

From `backend/` with the root virtual environment active:

```text
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Deterministic tests:

```text
pytest -q
```
