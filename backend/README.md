# Law-Rag Backend

The backend is the local Python/FastAPI application for Law-Rag. OCR, embedding and generative-model providers stay behind replaceable adapters rather than leaking provider-specific objects into domain logic.

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

legal manifest + verified snapshots
  -> versioned authority/version/article SQLite store
  -> Legal Evidence IDs + as_of resolution

GET /api/legal/retrieval/summary
POST /api/legal/retrieve
  -> exact + FTS5/BM25 + optional BGE
  -> deterministic fusion
  -> versioned Legal Evidence candidates

POST /api/documents/{job_id}/ai-audit
  -> deterministic Stage 8 issue/context builder
  -> Stage 7 retrieval
  -> one PrimaryAuditProvider
  -> strict JSON / evidence / legal-version validation
  -> persist ai-audit.json only after validation
```

## Runtime files

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/jobs/<job-id>/contract.json
runtime/jobs/<job-id>/audit-rules.json
runtime/jobs/<job-id>/ai-audit.json
runtime/rendered/<job-id>/page-0001.png
runtime/legal/legal.db
runtime/legal/retrieval.db
runtime/legal/import_reports/last-import-report.json
```

All generated artifacts are local/ignored and must not be committed.

## Stages 2–5 evidence foundations

- Stage 2: `pypdf` native text before OCR.
- Stage 3: local PaddleOCR only on `OCR_REQUIRED` pages; coordinates/confidence/provenance retained.
- Stage 4: canonical contract schema `1.0.0`, one evidence-grounded representation consumed by downstream systems.
- Stage 5: deterministic rule states `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE`; rule `FAIL` is not a legal conclusion.

## Stage 6 — Versioned legal evidence

Canonical identity:

```text
authority -> authority version -> article / Legal Evidence ID
```

Applicability:

```text
effective_date <= as_of < end_date_exclusive
```

The verified public seed is deliberately `CURATED_EXCERPT`: 2 authorities / 2 versions / 15 articles. Missing evidence from this seed is not proof a legal rule does not exist.

Build:

```text
rebuild-legal-seed.bat
```

## Stage 7 — Hybrid legal retrieval

Modules:

```text
app/legal/retrieval_models.py
app/legal/retrieval.py
app/legal/embeddings.py
app/legal/retrieval_cli.py
```

Channels:

- deterministic exact authority/article lookup;
- SQLite FTS5 `trigram` + `bm25()`;
- optional local `BAAI/bge-small-zh-v1.5` semantic embeddings;
- deterministic weighted reciprocal-rank fusion.

Final candidates are rechecked for `as_of` applicability and keep coverage/version/channel provenance.

Build exact + BM25 index:

```text
build-retrieval-index.bat
```

Optional semantic stack/index:

```text
setup-rag-semantic-cpu.bat
build-retrieval-index-semantic.bat
```

Public CI gate on the current small seed:

```text
Recall@5 >= 0.90
MRR      >= 0.80
```

## Stage 8 — Primary LLM audit reasoning

Modules:

```text
app/ai_audit_models.py
app/ai_audit_context.py
app/ai_audit_providers.py
app/ai_audit.py
app/ai_audit_api.py
```

Schemas/engine:

```text
AI audit schema: 1.0.0
context schema:  1.0.0
engine:          stage8-1.0.0
context builder: stage8-context-1.0.0
```

### Context builder

The model does not independently reread the raw PDF and does not receive a blind entire-contract dump.

Application code identifies a bounded first set of legal topics from canonical clauses:

- 格式条款;
- 违约金;
- 定金;
- 合同生效;
- 合同履行;
- 违约责任;
- 合同形式;
- 合同成立.

For each matched topic, Stage 7 retrieval runs with the explicit `as_of`. Non-PASS deterministic rule context is also included. The resulting `AuditContextPackage` receives a deterministic fingerprint.

### Provider boundary

```text
PrimaryAuditProvider
  -> DeepSeekProvider
  -> FakeAuditProvider   # tests only
```

Current DeepSeek default, re-verified against official API docs on 2026-08-15:

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
response_format={"type":"json_object"}
thinking={"type":"enabled"}
reasoning_effort=high
```

The adapter uses the existing `httpx` dependency. There is no hidden fallback to another provider.

Local configuration:

```bat
set DEEPSEEK_API_KEY=<your-local-key>
set DEEPSEEK_BASE_URL=https://api.deepseek.com
set DEEPSEEK_MODEL=deepseek-v4-flash
```

Provider health does not make a model call:

```text
GET /api/ai/providers/health?provider=deepseek
```

### Prompt-injection boundary

Contract clauses, legal text, filenames and rule explanations are explicitly serialized as untrusted data. Embedded instructions are not system instructions.

This is defense-in-depth only. Deterministic post-model validation is the trust boundary.

### Post-model validation

Before persistence, Stage 8 rejects:

- invalid/non-schema JSON;
- duplicate model finding IDs;
- unsupplied issue IDs;
- unsupplied canonical object IDs;
- unsupplied contract Evidence IDs;
- unsupplied Legal Evidence IDs;
- Legal Evidence outside the cited issue package;
- Legal Evidence whose stored version does not apply on `as_of`;
- `SUPPORTED_FINDING` without both contract and legal evidence.

Evidence sufficiency remains explicit:

```text
SUFFICIENT
PARTIAL_CORPUS
INSUFFICIENT_CORPUS
VERSION_UNCERTAIN
SOURCE_UNCERTAIN
```

A `NO_FINDING` cannot become a confident negative conclusion when coverage is incomplete. Material OCR/version/corpus uncertainty can force review.

### Persistence/API

Only validated output is written atomically:

```text
runtime/jobs/<job-id>/ai-audit.json
```

A provider error or invalid new response leaves any previously valid report unchanged.

API:

```text
POST /api/documents/<job-id>/ai-audit
GET  /api/documents/<job-id>/ai-audit
```

DeepSeek `reasoning_content` is not persisted. Provider result stores final structured content plus safe request/usage metadata and response hashes.

## Validation

Normal deterministic suite:

```text
pytest -q
```

Normal CI uses fake/static providers only and requires no DeepSeek key.

Stage 8 regressions include:

- valid grounded finding/persistence;
- malformed JSON rejection;
- invented contract/Legal Evidence rejection;
- wrong historical legal version rejection on `as_of`;
- prompt-injection separation;
- provider error preserving previous valid report;
- API configuration/persistence;
- mocked DeepSeek V4 HTTP request-shape contract.

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

Optional real **paid/network** DeepSeek smoke using synthetic empty context only:

```bat
set PYTHONPATH=.
set DEEPSEEK_API_KEY=<your-local-key>
set LAW_RAG_DEEPSEEK_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m deepseek_smoke
```

See:

- [`../docs/RETRIEVAL.md`](../docs/RETRIEVAL.md)
- [`../docs/AI_AUDIT.md`](../docs/AI_AUDIT.md)

## Stage 9 boundary

Stage 9 may add conditional secondary review and bounded Agent actions. It may not hand ownership of the mandatory audit pipeline to a model. The second reviewer must receive bounded evidence and pass independent evidence/version validation just like the primary model.
