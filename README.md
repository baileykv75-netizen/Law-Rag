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
  -> build/retrieve versioned legal authorities
  -> perform evidence-grounded LLM reasoning
  -> invoke bounded secondary review when needed
  -> show findings + contract evidence + legal evidence + review state
```

The browser is only the interface. Processing runs in the local FastAPI backend unless a later stage explicitly calls an external model API.

## Current status

**Stage 5 complete. Stage 6 active: Versioned Legal Knowledge Base.**

Completed foundations now include:

- React/Vite + FastAPI local application shell;
- validated PDF/JPG/PNG ingestion;
- page-aware PDF native-text extraction;
- native/OCR/mixed routing;
- PDFium rendering only for OCR-required PDF pages;
- provider-neutral local OCR layer;
- PaddleOCR adapter with PP-OCRv6 medium default;
- OCR text, page, bbox/polygon, confidence and provider provenance;
- explicit OCR low-confidence/no-text/failure states;
- unified evidence abstraction over native PDF lines and OCR blocks;
- versioned canonical contract schema (`1.0.0`);
- deterministic clause/party/date/money/percentage/identifier reconstruction;
- source-grounded `contract.json`;
- versioned deterministic rule engine;
- explicit audit profile `basic-bilateral-v1`;
- `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE` rule states;
- OCR uncertainty propagation into rule-review state;
- local `audit-rules.json` persistence;
- deterministic audit API and local UI inspection;
- automated backend regression tests and frontend production-build CI.

The next implementation scope is strictly defined in [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 6 builds a version-aware legal-authority store before any RAG retrieval or LLM legal reasoning.

## Quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

No DeepSeek/Kimi/Qwen API key is required through Stage 6 foundation work.

### Base setup

Download/clone the repository, then double-click:

```text
setup-dev.bat
```

This creates the local Python virtual environment and installs the base backend/frontend dependencies.

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
```

Stage 6 will add generated legal-store artifacts under `runtime/legal/` rather than committing live databases/download snapshots to Git.

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

If a material rule input comes from OCR with missing confidence or confidence below the current review threshold, an otherwise deterministic `PASS`/`FAIL` can be surfaced as `REVIEW` while the original `deterministic_state` remains visible.

The percentage rule intentionally does **not** sum every percentage in a contract. It only evaluates conservatively identified payment-percentage groups with explicit context.

One rule exception is isolated and surfaced as an engine error/review result; unrelated rules continue running.

## Stage 6 boundary

Stage 6 will create the canonical legal-evidence layer before RAG.

Target concepts include:

- authority/version/article identities;
- official source identity;
- issuing body and legal authority class;
- publication/effective/repeal/supersession metadata;
- historical versions rather than latest-text-only storage;
- exact article text and hashes;
- deterministic legal Evidence IDs;
- local SQLite persistence;
- deterministic `as_of` version resolution;
- import manifests and validation reports.

Stage 6 explicitly does **not** add embeddings, BM25 ranking, vector search, DeepSeek/Kimi/Qwen reasoning, or an Agent. Those remain later stages.

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
5. **No fabricated legal authority.** Future legal citations must originate from the versioned legal knowledge layer.
6. **Uncertainty is allowed.** Review/insufficient-evidence states are preferable to forced certainty.
7. **Local-first data handling.** Private contracts, outputs, logs, indexes, model caches and secrets remain outside Git.
8. **Constrained Agent.** Mandatory audit stages remain application-controlled.
9. **One verifiable stage per iteration.** Avoid many half-finished subsystems in one round.

## Repository safety

This repository is currently public. Treat every committed file as public information.

Never commit real contracts, re-identifiable pseudonymized contracts, private legal test sets, API keys, `.env` files, private outputs/logs, generated legal databases, local indexes, model weights/caches, or OCR outputs containing private contract content. Use only fully fictional public fixtures unless a public legal source has been intentionally verified and curated under the Stage 6 policy.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance and research tool. A deterministic rule `FAIL` is not a legal conclusion, and future model output may also be incomplete or wrong. High-impact findings must remain reviewable by a qualified professional.

## Development documents

- [`AGENTS.md`](AGENTS.md) — long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) — the only implementation scope for the current iteration.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) — public-repository and local-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decisions.

## License

No open-source repository license has been selected yet. Public visibility does not by itself grant reuse/redistribution permission; a license should be chosen only after the project owner explicitly decides those terms.
