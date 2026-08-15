# Law-Rag Backend

The backend is the local Python/FastAPI application for Law-Rag. Provider-specific OCR/LLM SDK details must remain behind adapters instead of leaking into API or domain code.

## Current pipeline

```text
POST /api/documents
  -> validate/store local source
  -> inspect native PDF text or mark image/OCR pages

POST /api/documents/{job_id}/ocr
  -> OCR only OCR_REQUIRED pages
  -> persist OCR blocks/provenance

POST /api/documents/{job_id}/structure
  -> consume native + OCR evidence
  -> build versioned canonical contract
  -> persist contract.json

GET /api/documents/{job_id}/structure
  -> return persisted canonical contract
```

No external LLM API is required through the current Stage 5 work.

## Runtime files

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/jobs/<job-id>/contract.json
runtime/rendered/<job-id>/page-0001.png
```

All runtime artifacts are local/ignored and must not be committed.

## Stage 2 — document ingestion

PDF pages are inspected with `pypdf`. A page becomes `NATIVE_TEXT_USABLE` only when the deterministic routing heuristic considers the extracted text substantial enough and not suspicious. Otherwise it is `OCR_REQUIRED`.

Current routing thresholds are explicit/testable rather than claimed accuracy guarantees:

- at least 32 non-whitespace characters;
- suspicious/replacement characters no more than 2%;
- at least 45% meaningful/alphanumeric characters.

## Stage 3 — OCR evidence

`POST /api/documents/{job_id}/ocr` preserves native pages and OCRs only required pages.

The local provider boundary is `OcrProvider`; the concrete first adapter is PaddleOCR. PDF rasterization uses `pypdfium2/PDFium` only for pages requiring OCR.

Default accuracy-oriented OCR pair:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

Each OCR block retains stable Evidence ID, page, text, confidence, bbox/polygon and provider/model/version. The `0.85` threshold is a review-routing threshold only.

Optional Windows OCR runtime:

```text
setup-ocr-cpu.bat
```

Pinned path:

- PaddlePaddle CPU 3.3.0;
- PaddleOCR 3.7.0.

## Stage 4 — canonical contract structure

Stage 4 is implemented in dedicated modules:

```text
app/contract_models.py
app/contract_structure.py
```

The canonical schema version is `1.0.0`.

### Unified evidence

Native PDF text and OCR blocks are transformed into one ordered `EvidenceUnit` stream:

- native units keep page Evidence IDs and page-text character offsets;
- OCR units keep OCR block IDs, bbox/polygon and recognition confidence;
- OCR is never substituted for a page already trusted as native text.

Reusable `SourceSpan` objects carry derived items back to exact evidence.

### Deterministic structure

The current parser conservatively reconstructs:

- title candidates;
- clause/section hierarchy;
- cross-page clause continuation;
- party-role/name mentions;
- explicit dates and safe ISO normalization;
- explicit money amounts using `Decimal`;
- explicit percentages;
- labelled contract/project/agreement identifiers;
- attachment/clause references;
- conservative table candidates;
- warnings and unresolved/ambiguous states.

Common clause forms include:

```text
第一条
一、
（一）
1.
1、
1.1
1.1.1
(1) / （1）
```

The original numbering token is retained.

### Incomplete OCR gate

If a required OCR page is missing, `OCR_FAILED`, or `OCR_NO_TEXT`, structure generation returns an explicit incomplete error. It never creates a complete-looking `contract.json` with silently omitted pages.

### Determinism

The canonical structure stores a fingerprint of the exact persisted source evidence. Re-running the structure stage against unchanged inputs produces idempotent output.

### Current limitations

Stage 4 intentionally does not:

- fuzzy-merge entity/company names;
- make legal-risk judgments;
- call an LLM;
- infer missing dates/amounts;
- fabricate table cells;
- globally compare money/percentages without context.

These boundaries protect later deterministic rule and legal-RAG stages from hidden assumptions.

## Local run

From `backend/` with the root virtual environment active:

```text
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Deterministic tests:

```text
pytest -q
```

Optional real PaddleOCR smoke test:

```bat
set PYTHONPATH=.
set LAW_RAG_OCR_SMOKE_IMAGE=C:\path\to\fictional-test-image.png
..\.venv\Scripts\python.exe -m pytest -q -m ocr_smoke
```
