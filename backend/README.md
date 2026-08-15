# Law-Rag Backend

The backend is the local Python/FastAPI application for Law-Rag. Provider-specific OCR/embedding/LLM details remain behind adapters instead of leaking into API or domain code.

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

legal manifest + curated snapshots
  -> deterministic validation/import
  -> authority/version/article SQLite store
  -> exact Legal Evidence IDs + as_of resolution
```

No external generative LLM API is required through Stage 7 retrieval foundation work.

## Runtime files

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/jobs/<job-id>/contract.json
runtime/jobs/<job-id>/audit-rules.json
runtime/rendered/<job-id>/page-0001.png
runtime/legal/legal.db
runtime/legal/import_reports/last-import-report.json
```

All generated runtime artifacts are local/ignored and must not be committed.

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

The deterministic parser reconstructs title candidates, clause hierarchy/cross-page continuation, party mentions, explicit dates, money, percentages, identifiers, references, conservative table candidates and unresolved/warning states.

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

Every RuleResult retains rule ID/version, final/deterministic state, reason code, explanation, canonical object IDs, SourceSpans, Evidence IDs, observed values and review reasons.

Visible states:

- `PASS` — configured deterministic condition holds;
- `FAIL` — configured deterministic condition fails; this is not a legal conclusion;
- `REVIEW` — ambiguity/source uncertainty/parser limitation/intent requires verification;
- `NOT_APPLICABLE` — explicit context is insufficient for a safe check.

Low/unknown OCR confidence can downgrade an otherwise machine-determined PASS/FAIL to `REVIEW` while preserving the original `deterministic_state`.

## Stage 6 — Versioned legal evidence

Dedicated package:

```text
app/legal/models.py
app/legal/parser.py
app/legal/store.py
app/legal/importer.py
app/legal/cli.py
```

Legal schema version: `1.0.0`.
Importer version: `stage6-1.0.0`.

### Canonical identities

SQLite stores:

```text
authorities
  -> authority_versions
       -> legal_articles
```

Every article has a deterministic Legal Evidence ID, for example:

```text
legal:prc-civil-code:effective-2021-01-01:article-585
```

Legal versions preserve status, issuing/source metadata, publication/effective interval, coverage type, source snapshot hash, importer/schema version and verification notes. Articles retain exact source text/token, SHA-256 and heading context.

### Deterministic parser

The Stage 6 Chinese article parser starts a new article only when a `第X条` heading begins a physical line. Article references appearing inside ordinary prose do not become fake articles. Structural chapter/section headings remain article context.

### Import/rebuild

From repository root on Windows:

```text
rebuild-legal-seed.bat
```

Developer equivalent from `backend/`:

```text
python -m app.legal.cli rebuild --manifest ../legal_data/seed/manifest.json
```

The importer validates official source hosts for real seed data, expected source SHA-256, expected article count, identity conflicts and metadata. Rebuild writes a temporary database and atomically replaces `runtime/legal/legal.db` only after successful validation.

### Version resolver

Applicability uses:

```text
effective_date <= as_of < end_date_exclusive
```

Resolution states are explicit:

- `RESOLVED`;
- `NO_APPLICABLE_VERSION`;
- `AMBIGUOUS` for overlapping stored intervals.

The resolver never silently chooses “the latest” record when metadata is ambiguous.

### Legal API

```text
GET /api/legal/summary
GET /api/legal/authorities
GET /api/legal/authorities/{authority_id}
GET /api/legal/evidence/{legal_evidence_id}
GET /api/legal/resolve/{authority_id}?as_of=YYYY-MM-DD&article_token=第...条
```

These endpoints inspect canonical identity/version/evidence only; they do not perform RAG ranking.

### Seed coverage

The Stage 6 checked-in seed has two `CURATED_EXCERPT` versions totaling 15 articles. It is intentionally partial. A missing hit can therefore mean “corpus incomplete”; it cannot support a claim that the law contains no such rule.

## Stage 7 boundary

Stage 7 is active. It will add version-aware exact, lexical/BM25 and semantic retrieval over canonical Legal Evidence IDs, followed by deterministic fusion/reranking and retrieval evaluation.

Derivative indexes must remain rebuildable/local, must detect stale legal-db state, and must preserve `as_of`, source/version provenance and `CURATED_EXCERPT` coverage warnings.

Stage 7 does not add generative LLM legal reasoning or Agent behavior.

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
