# Law-Rag Backend

The backend is the local Python/FastAPI application for Law-Rag. OCR, embedding and future generative-model providers stay behind replaceable adapters rather than leaking provider-specific behavior into domain logic.

## Current pipeline

```text
POST /api/documents
  -> validate/store local source
  -> native PDF inspection / OCR routing

POST /api/documents/{job_id}/ocr
  -> OCR only OCR_REQUIRED pages
  -> persist page/block evidence

POST /api/documents/{job_id}/structure
  -> build canonical contract
  -> persist contract.json

POST /api/documents/{job_id}/audit-rules
  -> deterministic rule registry
  -> persist audit-rules.json

legal manifest + verified source snapshots
  -> versioned authority/version/article SQLite store
  -> Legal Evidence IDs + as_of resolution

GET /api/legal/retrieval/summary
POST /api/legal/retrieve
  -> exact citation lookup
  -> FTS5 trigram / BM25
  -> optional local semantic vectors
  -> deterministic fusion
  -> versioned Legal Evidence candidates
```

No external **generative** LLM API is required through completed Stage 7. Stage 8 is the first stage allowed to add a primary generative audit provider.

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
runtime/legal/retrieval.db
runtime/legal/import_reports/last-import-report.json
```

All generated runtime artifacts are local/ignored and must not be committed.

## Evidence/document foundations

### Stage 2 — Native PDF before OCR

PDF pages are inspected with `pypdf`. Reliable native text is retained; only scanned/suspicious pages route to OCR.

### Stage 3 — OCR evidence

`POST /api/documents/{job_id}/ocr` preserves native pages and OCRs only required pages.

- provider boundary: `OcrProvider`;
- local provider: PaddleOCR;
- PDF rasterizer: pypdfium2/PDFium;
- default OCR models: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`;
- evidence retains page, text, bbox/polygon, confidence and provider/model/version.

### Stage 4 — Canonical contract

```text
app/contract_models.py
app/contract_structure.py
```

Schema `1.0.0`. Native/OCR evidence becomes one ordered canonical representation with SourceSpans. Failed/missing OCR pages block complete structure generation rather than being silently omitted.

### Stage 5 — Deterministic audit rules

```text
app/audit_rule_models.py
app/audit_rules.py
```

Rule states:

- `PASS`;
- `FAIL` — machine condition failed, not a legal conclusion;
- `REVIEW`;
- `NOT_APPLICABLE`.

The engine consumes `contract.json`, preserves Evidence IDs/observed values, and propagates material OCR uncertainty.

## Stage 6 — Versioned legal evidence

Dedicated package:

```text
app/legal/models.py
app/legal/parser.py
app/legal/store.py
app/legal/importer.py
app/legal/cli.py
```

Canonical identity:

```text
authority -> authority version -> article / Legal Evidence ID
```

Example:

```text
legal:prc-civil-code:effective-2021-01-01:article-585
```

Applicability:

```text
effective_date <= as_of < end_date_exclusive
```

Resolver states include `RESOLVED`, `NO_APPLICABLE_VERSION`, and `AMBIGUOUS`.

Build the verified public seed from repository root:

```text
rebuild-legal-seed.bat
```

The current public seed is deliberately `CURATED_EXCERPT` coverage: 2 authorities / 2 versions / 15 articles. A missing article is not proof the law has no such rule.

## Stage 7 — Hybrid legal retrieval

Dedicated modules:

```text
app/legal/retrieval_models.py
app/legal/retrieval.py
app/legal/embeddings.py
app/legal/retrieval_cli.py
```

Retrieval schema: `1.0.0`.
Engine: `stage7-1.0.0`.

### Exact channel

Exact authority/article/Legal-Evidence hints are resolved deterministically against the version applicable on `as_of`. Exact applicable hits remain ahead of probabilistic candidates.

Exact lookup does not require a derivative retrieval index.

### Lexical channel

The local derivative index uses SQLite FTS5:

```text
tokenize='trigram'
+ bm25()
```

This gives a deterministic Chinese substring-oriented lexical baseline without relying on whitespace tokenization.

Build it from repository root:

```text
build-retrieval-index.bat
```

The index records a fingerprint of canonical Stage 6 legal evidence. When `legal.db` changes, index health becomes stale until rebuilt.

### Optional semantic channel

Provider boundary:

```text
EmbeddingProvider
  -> BgeSmallZhProvider
  -> deterministic fake provider for tests
```

Initial real local model:

```text
BAAI/bge-small-zh-v1.5
```

Install/build on Windows:

```text
setup-rag-semantic-cpu.bat
build-retrieval-index-semantic.bat
```

Exact + BM25 remain available without semantic dependencies.

The real Windows semantic path has been verified in an opt-in GitHub Actions integration job: install semantic runtime -> load/download BGE -> embed the verified seed -> execute Chinese liquidated-damages retrieval -> assert expected Civil Code evidence is returned.

### Fusion and uncertainty

Candidates from exact/BM25/semantic channels are merged through deterministic weighted reciprocal-rank fusion. Each candidate retains channel rank/raw score/contribution plus fused score.

Ranking never overrides evidence-state constraints:

- non-applicable historical versions are excluded;
- ambiguous/no-applicable versions remain explicit;
- exact requested evidence missing from a partial corpus yields `INSUFFICIENT_CORPUS` even if similar articles rank highly;
- fused score is not a calibrated probability of legal correctness.

### Retrieval API

```text
GET  /api/legal/retrieval/summary
POST /api/legal/retrieve
```

The response exposes Legal Evidence IDs, authority/version/article data, `as_of`, coverage, channels executed, per-channel scores/ranks, fused score and warnings.

### Retrieval benchmark

Public fixture:

```text
legal_data/fixtures/retrieval_benchmark.json
```

Normal CI rebuilds the public seed/index and requires:

```text
Recall@5 >= 0.90
MRR      >= 0.80
```

This small benchmark verifies retrieval mechanics on the checked-in 15-article seed only; it is not a production legal-recall claim.

## Stage 8 boundary

Stage 8 is active. It may add **one** primary generative audit provider, with DeepSeek planned first after current official API verification.

The provider must reason only over a deterministic package derived from:

```text
contract.json
+ audit-rules.json
+ Stage 7 versioned Legal Evidence
+ explicit as_of / coverage / uncertainty
```

Model output must be strict structured data and must pass deterministic validation. Invented contract Evidence IDs or Legal Evidence IDs are rejected. Second-model review and Agent orchestration remain Stage 9.

## Local run

```text
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Normal backend tests:

```text
pytest -q
```

Optional real OCR smoke:

```bat
set PYTHONPATH=.
set LAW_RAG_OCR_SMOKE_IMAGE=C:\path\to\fictional-test-image.png
..\.venv\Scripts\python.exe -m pytest -q -m ocr_smoke
```

Optional real semantic smoke:

```bat
set PYTHONPATH=.
set LAW_RAG_RAG_SEMANTIC_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m rag_semantic_smoke
```

See [`../docs/RETRIEVAL.md`](../docs/RETRIEVAL.md) for Stage 7 details.
