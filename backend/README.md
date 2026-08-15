# Backend

The backend is the local Python/FastAPI application for Law-Rag.

Backend responsibilities include local HTTP endpoints, job creation, validation, document ingestion, local persistence access, and stable interfaces to later OCR/RAG/rule/LLM components.

Provider-specific SDK details should remain behind adapters rather than leaking through endpoint/domain code.

## Stage 2 document ingestion

The current `POST /api/documents` flow:

```text
validate upload
  -> store source under ignored runtime/uploads/<job-id>/
  -> classify PDF vs image
  -> PDF: inspect each page with pypdf
  -> image: mark OCR_REQUIRED
  -> persist document summary + page evidence under runtime/jobs/<job-id>/
  -> return route summary to the local UI
```

Runtime outputs are intentionally outside Git tracking.

### PDF routing heuristic

Stage 2 does not claim to prove extraction correctness. It only makes a conservative deterministic routing decision.

A PDF page is currently marked `NATIVE_TEXT_USABLE` only when all of the following are true:

- at least 32 non-whitespace characters were extracted;
- suspicious/replacement characters are no more than 2% of non-whitespace characters;
- at least 45% of non-whitespace characters are alphanumeric/meaningful text characters.

Otherwise the page is marked `OCR_REQUIRED` for Stage 3.

The thresholds are intentionally explicit and regression-testable. They can be tuned later against the private legal benchmark instead of being changed by intuition.

### Evidence persistence

For every page, Stage 2 preserves:

- stable evidence ID scoped to the job;
- 1-based page number;
- extraction/source method;
- page text when available;
- character counts and routing metrics;
- route and reason;
- page source locator.

The persisted files are:

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
```

### PDF library

Stage 2 uses `pypdf>=6.14,<7` for page count and native text extraction. The rendering boundary is separate; no PDF-to-image renderer or OCR engine is introduced in this stage.

## Local run

From `backend/` with the root virtual environment active:

```text
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Tests:

```text
pytest -q
```
