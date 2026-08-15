# Law-Rag

Law-Rag is a local-first intelligent contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application rather than a generic legal chatbot. Contracts are ingested locally, source evidence is preserved, deterministic checks run before probabilistic reasoning, and future legal/LLM conclusions must remain traceable to supporting contract and legal evidence.

## Product flow

```text
local browser UI
  -> upload PDF / JPG / PNG
  -> preserve reliable native PDF text
  -> OCR only pages that actually require OCR
  -> reconstruct evidence-grounded canonical contract
  -> run deterministic audit rules
  -> resolve/retrieve versioned legal authorities
  -> perform evidence-grounded LLM reasoning
  -> invoke bounded secondary review when needed
  -> show findings + contract evidence + legal evidence + review state
```

The browser is only the interface. Processing runs in the local FastAPI backend unless a later stage explicitly calls an external model API.

## Current status

**Stage 6 complete. Stage 7 active: Hybrid Legal RAG.**

Completed foundations now include:

- React/Vite + FastAPI local application shell;
- validated PDF/JPG/PNG ingestion;
- page-aware PDF native-text extraction;
- native/OCR/mixed routing;
- PDFium rendering only for OCR-required PDF pages;
- provider-neutral local OCR layer and PaddleOCR PP-OCRv6 medium default;
- OCR text, page, bbox/polygon, confidence and provider provenance;
- explicit OCR low-confidence/no-text/failure states;
- unified evidence abstraction over native PDF lines and OCR blocks;
- versioned canonical contract schema (`1.0.0`);
- deterministic clause/party/date/money/percentage/identifier reconstruction;
- source-grounded `contract.json`;
- versioned deterministic rule engine and explicit `basic-bilateral-v1` profile;
- `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE` rule states with OCR uncertainty propagation;
- local `audit-rules.json` persistence and rule inspection UI;
- dedicated versioned legal-evidence schema (`1.0.0`);
- local SQLite legal store with authority → version → article identity;
- deterministic legal Evidence IDs and per-source/per-article SHA-256 hashes;
- deterministic Chinese article segmentation with inline-reference protection;
- historical version retention and explicit `as_of` resolution;
- explicit `RESOLVED`, `NO_APPLICABLE_VERSION`, and `AMBIGUOUS` version states;
- atomic manifest rebuild/import and machine-readable validation reports;
- small verified contract-relevant legal seed with explicit `CURATED_EXCERPT` coverage;
- legal summary/authority/evidence/version-resolution APIs and local health UI;
- automated backend regression tests and frontend production-build CI.

The next implementation scope is strictly defined in [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 7 adds retrieval over this canonical legal evidence without yet adding DeepSeek/Kimi/Qwen audit reasoning.

## Quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

No DeepSeek/Kimi/Qwen API key is required through Stage 7 retrieval foundation work.

### Base setup

Download/clone the repository, then double-click:

```text
setup-dev.bat
```

This creates the local Python virtual environment and installs the base backend/frontend dependencies.

### Build the local legal seed database

Run:

```text
rebuild-legal-seed.bat
```

This validates the curated manifest/snapshots and atomically builds:

```text
runtime/legal/legal.db
runtime/legal/import_reports/last-import-report.json
```

A failed rebuild does not replace a previously valid database.

### Optional OCR setup

For scanned PDFs or JPG/PNG contracts, also run:

```text
setup-ocr-cpu.bat
```

The pinned local CPU OCR path uses:

- PaddlePaddle CPU 3.3.0;
- PaddleOCR 3.7.0;
- `PP-OCRv6_medium_det`;
- `PP-OCRv6_medium_rec`.

OCR model files are downloaded locally on first use and remain outside Git.

### Start Law-Rag

Double-click:

```text
start-dev.bat
```

Local services:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

The UI includes a Stage 6 legal-knowledge health panel. If the legal database has not been built, the panel tells you to run `rebuild-legal-seed.bat`.

## Local runtime artifacts

Generated/private processing artifacts remain under ignored runtime paths:

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

Generated legal databases, live snapshots/indexes, contract data, logs and other private runtime artifacts are not committed to Git.

## Stage 5 deterministic audit rules

After `contract.json` exists, the local UI/API can run the Stage 5 deterministic rule engine.

API:

```text
POST /api/documents/{job_id}/audit-rules?profile=basic-bilateral-v1
GET  /api/documents/{job_id}/audit-rules
```

The first rule families include:

- required-field checks driven by an explicit audit profile;
- repeated party-name consistency grouped by the same explicit role;
- repeated identifier consistency grouped by the same explicit label;
- repeated explicit date-field consistency;
- signing/effective date chronology review;
- conservative same-context payment-percentage totals;
- repeated supported labelled contract-amount consistency;
- Chinese uppercase RMB detection routed to manual review instead of using a weak conversion parser.

### Rule-state semantics

```text
PASS
  configured deterministic condition holds

FAIL
  configured deterministic condition does not hold
  != illegal / invalid / unenforceable

REVIEW
  source, grouping, parser, chronology intent, or OCR uncertainty needs verification

NOT_APPLICABLE
  explicit inputs/context are insufficient to run the rule safely
```

Every result retains stable rule ID/version, reason code, observed values, canonical object IDs, source spans and Evidence IDs.

## Stage 6 versioned legal evidence

Stage 6 creates a canonical legal-evidence layer before RAG or LLM reasoning.

SQLite stores three explicit identities:

```text
authority
  -> authority version
       -> exact article / Legal Evidence ID
```

Legal article Evidence IDs are deterministic, for example:

```text
legal:prc-civil-code:effective-2021-01-01:article-585
```

Each version retains official source references, issuing body/type, publication/effective interval metadata, coverage type, source SHA-256, schema/importer version, and verification notes. Each article retains its original token/text, article SHA-256 and structural heading context.

### Version resolution

The resolver uses explicit half-open effective intervals:

```text
effective_date <= as_of < end_date_exclusive
```

It returns an explicit state rather than guessing:

- `RESOLVED`;
- `NO_APPLICABLE_VERSION`;
- `AMBIGUOUS` when stored version intervals overlap.

The requested `as_of` date remains visible in the result. The database does not bake the current wall-clock date into legal evidence.

### Local legal APIs

```text
GET /api/legal/summary
GET /api/legal/authorities
GET /api/legal/authorities/{authority_id}
GET /api/legal/evidence/{legal_evidence_id}
GET /api/legal/resolve/{authority_id}?as_of=YYYY-MM-DD&article_token=第...条
```

These are identity/version inspection endpoints only. They are not RAG ranking or semantic search.

### Curated Stage 6 seed

The checked-in seed intentionally contains **two CURATED_EXCERPT versions, not complete authorities**:

- `中华人民共和国民法典`: 8 contract-core articles — 469, 496, 497, 502, 509, 577, 585, 586;
- `最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释`: 7 selected articles — 1, 3, 9, 10, 16, 65, 69.

The seed is deliberately small so Stage 6 validates provenance/version architecture before corpus expansion. **Absence from this seed is never evidence that a legal rule does not exist.** Coverage metadata must remain visible in Stage 7 retrieval to avoid false-negative legal conclusions.

See [`legal_data/README.md`](legal_data/README.md) and [`legal_data/seed/manifest.json`](legal_data/seed/manifest.json).

### Known Stage 6 limitation

If a multi-record non-rebuild import transaction later rolls back after an identity conflict, the SQLite transaction is correctly rolled back, but an intermediate validation entry may still describe a record as `IMPORTED` in the failure report. The database remains authoritative and unmodified; report-state refinement is recorded as a hardening item and should be fixed before release packaging.

## Stage 7 boundary

Stage 7 adds hybrid retrieval over canonical legal evidence:

- exact authority/article citation lookup;
- lexical/BM25 retrieval;
- semantic/vector retrieval behind a replaceable embedding boundary;
- fusion/reranking;
- `as_of` version filtering before legal evidence can be returned;
- coverage-aware retrieval states;
- labeled retrieval evaluation such as Recall@K.

Stage 7 still does **not** add DeepSeek/Kimi/Qwen audit reasoning. Model-assisted legal reasoning remains Stage 8.

## Developer validation

Backend deterministic tests:

```bat
cd backend
set PYTHONPATH=.
..\.venv\Scripts\python.exe -m pytest -q
```

Frontend:

```bat
cd frontend
npm run typecheck
npm run build
```

Optional real PaddleOCR smoke test:

```bat
cd backend
set PYTHONPATH=.
set LAW_RAG_OCR_SMOKE_IMAGE=C:\path\to\fictional-test-image.png
..\.venv\Scripts\python.exe -m pytest -q -m ocr_smoke
```

GitHub Actions runs deterministic backend tests and the frontend production build on pushes and pull requests to `main`.

## Core engineering principles

1. **Evidence first.** Material findings must be traceable to exact source evidence.
2. **Native text before OCR.** Do not degrade reliable PDF text through unnecessary OCR.
3. **Deterministic before probabilistic.** Machine-checkable inconsistencies are ordinary code before LLM reasoning.
4. **One canonical contract model.** Downstream rules/RAG/LLMs do not independently reinterpret raw PDFs.
5. **Versioned canonical legal evidence.** Legal retrieval must preserve authority/version/article/source identity and coverage.
6. **No fabricated legal authority.** Future legal citations must originate from the legal knowledge layer.
7. **Uncertainty is allowed.** Review/insufficient-evidence/ambiguity states are preferable to forced certainty.
8. **Local-first data handling.** Private contracts, outputs, logs, indexes, model caches and secrets remain outside Git.
9. **Constrained Agent.** Mandatory audit stages remain application-controlled.
10. **One verifiable stage per iteration.** Avoid many half-finished subsystems in one round.

## Repository safety

This repository is currently public. Treat every committed file as public information.

Never commit real contracts, re-identifiable pseudonymized contracts, private legal test sets, API keys, `.env` files, private outputs/logs, generated legal databases, local indexes, model weights/caches, or OCR outputs containing private contract content. Use only fully fictional public fixtures unless a public legal source has been intentionally verified and curated under the legal-data policy.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance and research tool. A deterministic rule `FAIL` is not a legal conclusion, absence from a partial legal seed is not evidence that no law exists, and future model output may also be incomplete or wrong. High-impact findings must remain reviewable by a qualified professional.

## Development documents

- [`AGENTS.md`](AGENTS.md) — long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) — the only implementation scope for the current iteration.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) — public-repository and local-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decisions.
- [`legal_data/README.md`](legal_data/README.md) — legal provenance/coverage policy.

## License

No open-source repository license has been selected yet. Public visibility does not by itself grant reuse/redistribution permission; a license should be chosen only after the project owner explicitly decides those terms.
