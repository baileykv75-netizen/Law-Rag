# Law-Rag

Law-Rag is a local-first intelligent contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application, not a generic legal chatbot. Contracts are ingested locally, source evidence is preserved, deterministic checks run before probabilistic reasoning, and later legal/LLM conclusions must remain traceable to supporting evidence.

## Product flow

```text
local browser UI
  -> upload PDF / JPG / PNG
  -> preserve reliable native PDF text
  -> OCR only pages that actually require OCR
  -> reconstruct evidence-grounded contract structure
  -> run deterministic audit rules
  -> build/retrieve versioned legal authorities
  -> perform evidence-grounded LLM reasoning
  -> invoke bounded secondary review when needed
  -> show findings + contract evidence + legal evidence + review state
```

The browser is only the interface. Processing runs in the local FastAPI backend unless a later stage explicitly calls an external model API.

## Current status

**Stage 4 complete. Stage 5 active: Deterministic Audit Rules.**

Completed foundations now include:

- React/Vite + FastAPI local application shell;
- validated PDF/JPG/PNG ingestion;
- page-aware PDF native-text extraction;
- native/OCR/mixed routing;
- PDFium rendering only for OCR-required PDF pages;
- provider-neutral local OCR layer;
- PaddleOCR adapter with an accuracy-oriented PP-OCRv6 medium default;
- OCR text, page, bbox/polygon, confidence and provider provenance;
- explicit OCR low-confidence/no-text/failure states;
- one unified evidence abstraction over native PDF lines and OCR blocks;
- versioned canonical contract schema (`1.0.0`);
- deterministic clause hierarchy and cross-page continuation;
- evidence-linked party/date/money/percentage/identifier/reference mentions;
- explicit unresolved/ambiguous states instead of guessed facts;
- local `contract.json` persistence and Stage 4 structure APIs;
- deterministic regression tests and frontend production-build CI.

The active implementation scope is defined in [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 5 adds explainable hard checks only; legal RAG, DeepSeek/Kimi/Qwen reasoning and Agent behavior remain later stages.

## Quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

No DeepSeek/Kimi/Qwen API key is required through the current Stage 5 work.

### Base setup

Download/clone the repository, then run:

```text
setup-dev.bat
```

This creates the local Python environment and installs base backend/frontend dependencies.

### Optional local OCR setup

To process scanned PDFs or JPG/PNG contract images, also run:

```text
setup-ocr-cpu.bat
```

The pinned local CPU OCR path uses:

```text
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

OCR is deliberately separate from the base installation. Native-text-only PDFs do not need to import PaddleOCR or download OCR models.

PaddleOCR model files are downloaded locally on first OCR use. If the default model source is inaccessible, the environment variable below can be used before startup:

```text
PADDLE_PDX_MODEL_SOURCE=BOS
```

### Start Law-Rag

Run:

```text
start-dev.bat
```

It starts:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

Closing the backend/frontend terminal windows stops the application.

## Local runtime data

Uploaded and generated artifacts remain under ignored local paths:

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/jobs/<job-id>/contract.json
runtime/rendered/<job-id>/page-0001.png
```

These paths are excluded from Git and must not be committed.

## Verified document and OCR behavior

### Native text before OCR

Each PDF is inspected page by page. Pages with sufficiently usable native text remain native evidence. Pages with missing/sparse/suspicious text become `OCR_REQUIRED`.

Document routes are:

- `NATIVE_TEXT`;
- `OCR_REQUIRED`;
- `MIXED`.

Law-Rag does **not** rasterize and OCR every PDF page by default.

### OCR evidence

For OCR-required pages, Stage 3 preserves:

- stable OCR block Evidence IDs;
- 1-based page number;
- recognized text;
- recognition confidence when available;
- bounding box and polygon when available;
- provider/model/version provenance;
- explicit low-confidence state/reason.

Page states include:

- `NATIVE_RETAINED`;
- `OCR_COMPLETE`;
- `OCR_LOW_CONFIDENCE`;
- `OCR_NO_TEXT`;
- `OCR_FAILED`.

The current `0.85` OCR threshold is only a review-routing threshold, not a calibrated probability that the text is correct.

A GitHub Actions Windows smoke run has verified Python 3.11 + PaddlePaddle CPU 3.3.0 + PaddleOCR 3.7.0 installation/runtime imports. Normal CI deliberately does not download OCR model weights or claim real-model legal-document accuracy.

## Verified Stage 4 canonical structure

Stage 4 converts prior evidence into one typed canonical contract representation without calling an LLM.

### Unified evidence stream

Native PDF and OCR evidence are consumed through one ordered abstraction while preserving provenance:

```text
native PDF line
  -> page Evidence ID + native character offsets

OCR block
  -> OCR Evidence ID + bbox/polygon + recognition confidence
```

A native-text page is never silently replaced by OCR text.

### Canonical contract schema

The persisted `contract.json` uses schema version `1.0.0` and contains evidence-linked objects for:

- title candidates;
- numbered clauses/sections;
- unnumbered blocks;
- party-role/name mentions;
- date mentions;
- monetary amount mentions;
- percentage mentions;
- contract/project/agreement identifiers;
- attachment and clause references;
- conservative structured/table candidates;
- extraction warnings and unresolved states.

Every derived object retains source spans that ultimately point to native/OCR Evidence IDs.

### Clause structure

The deterministic parser currently supports common forms including:

```text
第一条 / 第二条
一、 / 二、
（一） / （二）
1. / 1、
1.1 / 1.1.1
(1) / （1）
```

The original heading token is preserved. Parent/child levels are represented conservatively, and a clause can continue across later pages until a new heading is encountered.

### Factual mentions

Stage 4 conservatively extracts explicit facts such as:

```text
甲方：甲测试有限公司
签订日期：2026年8月15日
人民币 100,000 元
10万元
30%
百分之七十
合同编号：HT-2026-001
见附件1
按照第一条执行
```

Safe deterministic normalization is stored separately from raw source text. Impossible dates, unresolved references and ambiguous targets remain explicit instead of being guessed.

Stage 4 does **not** fuzzy-merge party names or decide legal entity equivalence. Chinese uppercase RMB comparison is intentionally deferred to the deterministic-rule stage unless a well-tested parser is available.

### Incomplete OCR protection

If any page that requires OCR remains `OCR_FAILED`, `OCR_NO_TEXT`, missing, or otherwise incomplete, canonical structure generation is refused rather than silently omitting that page.

### Structure API

```text
POST /api/documents/{job_id}/structure
GET  /api/documents/{job_id}/structure
```

POST generates/persists the canonical structure. GET returns the full persisted `contract.json` representation.

For unchanged evidence, structure output is deterministic/idempotent and carries a source fingerprint.

### Stage 4 UI

The local interface can now show:

- detected title candidate;
- clause count and outline;
- clause page ranges/hierarchy;
- party mentions;
- date/money/percentage/identifier counts and values;
- unresolved reference count;
- extraction warning count.

This remains factual document structure. **No semantic legal-risk conclusion or statute judgment is produced yet.**

## Validation status

Stage 4 regression coverage includes fictional/synthetic cases for:

- Chinese `第X条` parsing;
- Chinese `一、` / `（一）` hierarchy;
- Arabic `1.` / `1.1` / `1.1.1` hierarchy;
- cross-page clause continuation;
- mixed native/OCR evidence provenance;
- native offsets and OCR coordinates/evidence IDs;
- parties, dates, money, percentages and identifiers;
- resolved/unresolved/ambiguous references;
- invalid dates;
- deterministic/idempotent output;
- explicit missing-OCR refusal;
- malformed evidence failure handling;
- all previous Stage 1–3 regressions.

The Stage 4 backend test suite and frontend production build have passed GitHub Actions after parser fixes for title-vs-clause classification and preservation of original Arabic heading tokens.

## Developer validation

Backend:

```bat
cd backend
set PYTHONPATH=.
..\.venv\Scripts\python.exe -m pytest -q
```

Optional real PaddleOCR smoke test:

```bat
cd backend
set PYTHONPATH=.
set LAW_RAG_OCR_SMOKE_IMAGE=C:\path\to\fictional-test-image.png
..\.venv\Scripts\python.exe -m pytest -q -m ocr_smoke
```

Frontend:

```bat
cd frontend
npm run typecheck
npm run build
```

## Core engineering principles

1. **Evidence first.** Material findings must be traceable to exact contract evidence and, later, retrieved legal evidence.
2. **Deterministic before probabilistic.** Arithmetic, date consistency, identifiers and other hard checks belong in ordinary code whenever practical.
3. **No fabricated legal authority.** Later models may only cite legal authorities supplied by the knowledge layer.
4. **Uncertainty is allowed.** Explicit review/unresolved states are preferable to unsupported certainty.
5. **Local-first data handling.** Real contracts, private benchmark data, outputs/logs, local indexes, model caches and secrets remain outside Git.
6. **Constrained Agent.** Mandatory audit stages stay application-controlled; future Agent choices are bounded by an allowlist.
7. **One verifiable stage per iteration.** A stage is closed only after tests/builds verify its behavior.

## Repository safety

This repository is public. Treat every committed file as public information.

Never commit:

- real contracts;
- re-identifiable pseudonymized contracts;
- private legal benchmark/test sets;
- API keys or `.env`;
- private OCR/structure/audit outputs;
- vector/index/model caches.

Use fully fictional fixtures in the public repository. See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance and research tool. Future model/rule output may still be incomplete or wrong and must not replace professional legal judgment. High-impact findings should remain reviewable by a qualified human.

## Development documents

- [`AGENTS.md`](AGENTS.md) — long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) — active implementation scope.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) — local/private-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decisions.

## License

No open-source license has been selected yet. A public repository is not automatically an open-source license grant. Reuse/redistribution terms should be chosen only when the project owner explicitly decides them.
