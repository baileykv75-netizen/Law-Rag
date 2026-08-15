# Law-Rag Backend

The backend is the local Python/FastAPI application for Law-Rag. Provider-specific OCR/LLM details remain behind adapters instead of leaking into API or domain code.

## Current pipeline

```text
POST /api/documents
  -> validate/store local source
  -> inspect native PDF text or mark OCR pages

POST /api/documents/{job_id}/ocr
  -> OCR only OCR_REQUIRED pages
  -> persist OCR blocks/provenance

POST /api/documents/{job_id}/structure
  -> consume native + OCR evidence
  -> build canonical contract
  -> persist contract.json

POST /api/documents/{job_id}/audit-rules
  -> consume contract.json only
  -> execute deterministic rule registry
  -> persist audit-rules.json
```

No external LLM API is required through Stage 5.

## Runtime files

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/jobs/<job-id>/contract.json
runtime/jobs/<job-id>/audit-rules.json
runtime/rendered/<job-id>/page-0001.png
```

All runtime artifacts are local/ignored and must not be committed.

## Stage 2 — Document ingestion

PDF pages are inspected with `pypdf`. A page becomes `NATIVE_TEXT_USABLE` only when the deterministic routing heuristic considers native text substantial enough and not suspicious; otherwise it is `OCR_REQUIRED`.

Current routing thresholds are explicit/testable routing heuristics, not accuracy guarantees:

- at least 32 non-whitespace characters;
- suspicious/replacement characters no more than 2%;
- at least 45% meaningful/alphanumeric characters.

## Stage 3 — OCR evidence

`POST /api/documents/{job_id}/ocr` preserves native pages and OCRs only required pages.

- provider boundary: `OcrProvider`;
- first concrete provider: local PaddleOCR;
- PDF rasterizer: pypdfium2/PDFium;
- default OCR models: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`.

Each OCR block retains stable Evidence ID, page, text, confidence, bbox/polygon and provider/model/version. The current `0.85` threshold is a review-routing threshold, not a calibrated text-correctness probability.

Optional Windows OCR runtime:

```text
setup-ocr-cpu.bat
```

Pinned path:

- PaddlePaddle CPU 3.3.0;
- PaddleOCR 3.7.0.

## Stage 4 — Canonical contract structure

Dedicated modules:

```text
app/contract_models.py
app/contract_structure.py
```

Canonical schema version: `1.0.0`.

Native PDF text and OCR blocks are transformed into one ordered EvidenceUnit stream. Reusable SourceSpan objects preserve page/Evidence IDs plus native character offsets or OCR bbox/polygon/confidence.

The deterministic parser currently reconstructs title candidates, clause hierarchy/cross-page continuation, party mentions, explicit dates, money, percentages, identifiers, references, conservative table candidates and unresolved/warning states.

If a required OCR page is missing, failed or no-text, complete structure generation is refused rather than silently omitting a page.

## Stage 5 — Deterministic audit rules

Dedicated modules:

```text
app/audit_rule_models.py
app/audit_rules.py
```

Report schema: `1.0.0`.
Engine version: `stage5-1.0.0`.
Default explicit profile: `basic-bilateral-v1`.

API:

```text
POST /api/documents/{job_id}/audit-rules?profile=basic-bilateral-v1
GET  /api/documents/{job_id}/audit-rules
```

### Result semantics

Every RuleResult includes stable rule ID/version, family/title, final state, deterministic state, reason code, explanation, canonical object IDs, SourceSpans, Evidence IDs, observed values and review reasons.

Visible states:

- `PASS` — configured deterministic condition holds;
- `FAIL` — configured deterministic condition fails; this is not a legal conclusion;
- `REVIEW` — ambiguity/source uncertainty/parser limitation/intent requires verification;
- `NOT_APPLICABLE` — explicit context is insufficient for a safe check.

### Initial rule registry

- `REQ-BASIC-PROFILE` — profile-driven minimum title/party presence;
- `PARTY-ROLE-CONSISTENCY` — repeated same-role party names, with no fuzzy entity merge;
- `IDENTIFIER-LABEL-CONSISTENCY` — repeated values under the same explicit identifier label;
- `DATE-FIELD-CONSISTENCY` — repeated explicit date-field values;
- `DATE-SIGNING-EFFECTIVE-ORDER` — chronology review; retroactive effective dates route to REVIEW rather than a legal-invalidity claim;
- `PAYMENT-PERCENTAGE-TOTAL` — conservative same-line explicitly labelled payment groups only;
- `AMOUNT-LABEL-CONSISTENCY` — supported repeated explicit contract-total amount labels;
- `UPPERCASE-RMB-REVIEW` — detects uppercase RMB text and documents the current parser limitation rather than shipping weak numeric conversion.

### OCR uncertainty propagation

If a material SourceSpan comes from OCR with missing confidence or confidence below `0.85`, an otherwise machine-determined PASS/FAIL can become final `REVIEW`. The original `deterministic_state` is retained so the calculation remains inspectable.

### Rule isolation

Rules are registered explicitly and run in deterministic order. A rule exception is captured in `engine_errors` and emitted as a REVIEW result; unrelated rules continue running.

### Persistence / determinism

Reports are persisted to:

```text
runtime/jobs/<job-id>/audit-rules.json
```

The report records canonical source/content fingerprints. Re-running against unchanged `contract.json` produces idempotent output.

## Stage 6 boundary

Stage 6 is the next active task. It will add a local, version-aware legal-authority/article store with official source/version metadata, deterministic legal Evidence IDs, hashes, SQLite persistence, historical-version relationships and `as_of` resolution.

Stage 6 does not add embeddings, BM25/vector retrieval, LLM legal reasoning or Agent behavior.

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
