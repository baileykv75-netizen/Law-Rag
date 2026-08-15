# Law-Rag

Law-Rag is a local-first intelligent contract audit assistant designed for personal research, testing, and professional review workflows.

The project goal is not to build a generic legal chatbot. The target product is a Windows-friendly local application that can ingest contracts, preserve source evidence, retrieve relevant legal rules, run deterministic checks, use large language models for semantic risk analysis, and keep every important conclusion traceable to its supporting evidence.

## Product goal

```text
Start Law-Rag locally
  -> open local web UI
  -> upload PDF / JPG / PNG contract
  -> preserve reliable native PDF text
  -> OCR only pages that actually require OCR
  -> reconstruct clauses / tables / parties / dates / amounts
  -> run deterministic audit rules
  -> retrieve current legal authorities
  -> perform evidence-grounded LLM-assisted risk analysis
  -> invoke secondary review only when needed
  -> show risk + contract evidence + legal evidence + review state
```

The intended final form is a downloadable local application. The browser is only the user interface; contract processing runs locally unless a later, explicitly configured external model API is called.

## Current status

**Stage 3 complete. Stage 4 active: Canonical Contract Structure.**

Completed foundations now include:

- local React/Vite + FastAPI application shell;
- validated local file ingestion;
- page-aware PDF native-text extraction;
- native/OCR/mixed routing;
- local PDF page rendering for OCR-required pages;
- provider-neutral OCR interface;
- local PaddleOCR adapter;
- OCR block text, coordinates, confidence and provider provenance;
- explicit low-confidence/no-text/failure states;
- mixed native/OCR evidence preservation;
- Windows-oriented setup/start paths;
- deterministic backend regression tests and frontend production-build CI.

The next implementation scope is strictly defined in [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 4 will reconstruct source evidence into a canonical contract model without adding legal RAG, LLM reasoning, audit rules, or Agent behavior.

## Quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

No DeepSeek/Kimi/Qwen API key is required yet.

### Base setup

Download/clone the repository, then double-click:

```text
setup-dev.bat
```

This creates the local Python virtual environment and installs the base backend/frontend dependencies.

### Optional local OCR setup

If you want to process scanned PDFs or JPG/PNG contract images, then also run:

```text
setup-ocr-cpu.bat
```

This installs the pinned local CPU OCR runtime:

- PaddlePaddle CPU 3.3.0;
- PaddleOCR 3.7.0.

The default OCR model pair is accuracy-oriented:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

OCR dependencies are deliberately separate from the base install. A native-text-only PDF workflow does not need to import PaddleOCR or download OCR models.

PaddleOCR models are downloaded locally on first OCR use. If the default model source is inaccessible, you may set:

```text
PADDLE_PDX_MODEL_SOURCE=BOS
```

before starting Law-Rag.

### Start Law-Rag

After setup, double-click:

```text
start-dev.bat
```

It starts:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

The frontend opens in the browser. Closing the backend/frontend terminal windows stops the local application.

## Verified document and OCR behavior

The UI accepts one `.pdf`, `.jpg`, `.jpeg`, or `.png` file up to 50 MiB.

### Local source and evidence storage

Uploaded and generated artifacts remain under ignored local runtime paths:

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/rendered/<job-id>/page-0001.png   # only PDF pages routed to OCR
```

These runtime paths are excluded from Git.

### PDF routing

Each PDF is inspected page by page with `pypdf`.

A page with usable native text remains native evidence. A page with absent/sparse/suspicious native text becomes `OCR_REQUIRED`.

Document routing can therefore be:

- `NATIVE_TEXT`;
- `OCR_REQUIRED`;
- `MIXED`.

Law-Rag does **not** convert every PDF page to images and OCR everything.

### OCR routing

```text
NATIVE_TEXT_USABLE page
  -> preserve original native evidence
  -> do not OCR by default

OCR_REQUIRED PDF page
  -> render only that page with pypdfium2/PDFium
  -> OCR locally

JPG/JPEG/PNG
  -> OCR original image
```

The PDF renderer uses `pypdfium2==5.12.1` and currently renders at scale `2.0` (roughly 144 DPI for standard PDF points).

### OCR evidence

Each recognized OCR block retains:

- stable OCR evidence ID;
- 1-based page number;
- recognized text;
- recognition confidence when available;
- bounding box and polygon when available;
- OCR provider/model/version provenance;
- pixel source locator;
- explicit low-confidence flag/reason.

The current low-confidence review threshold is `0.85`. This is a routing threshold for human review, not a calibrated probability that the OCR text is correct.

Pages can end in explicit states such as:

- `OCR_COMPLETE`;
- `OCR_LOW_CONFIDENCE`;
- `OCR_NO_TEXT`;
- `OCR_FAILED`;
- `NATIVE_RETAINED`.

### UI

After document inspection, the local interface shows page counts and route decisions. If OCR is required and the local OCR runtime is installed, the UI can run OCR and display:

- pages attempted;
- pages with recognized text;
- low-confidence page count;
- failed page count;
- no-text page count;
- per-page source method/state;
- OCR provider/model/version.

This is still an evidence-processing tool at this stage. **Legal audit has not started yet.**

## Validation status

Stage 3 deterministic CI covers synthetic/fictional cases including:

- native PDF routing;
- blank/scanned-style PDF routing;
- mixed native/OCR PDF routing;
- real PDFium page rendering;
- image OCR orchestration through a fake deterministic provider;
- stable OCR evidence IDs;
- coordinate/confidence persistence;
- low-confidence results;
- no-text results;
- provider failures;
- PaddleOCR result-field normalization;
- all earlier Stage 1/2 regressions.

A GitHub Actions Windows smoke run has also verified that Python 3.11 can install PaddlePaddle CPU 3.3.0 and PaddleOCR 3.7.0 and pass the Paddle runtime/import check.

Normal CI deliberately does **not** download the OCR model weights. A local opt-in real-model smoke test exists under `backend/tests/test_ocr_smoke.py`; it should be run with a fictional/local image after OCR setup when validating a specific machine and downloaded model set.

## Developer validation

Backend deterministic tests:

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

GitHub Actions runs deterministic backend tests and the frontend production build on pushes and pull requests to `main`.

## Core engineering principles

1. **Evidence first.** Every material audit finding must be traceable to exact contract evidence and, when it is a legal conclusion, to retrieved legal evidence.
2. **Deterministic before probabilistic.** Arithmetic, date consistency, party-name consistency, percentage totals, duplicate values, and other rule-based checks should not be delegated to an LLM when ordinary code can verify them.
3. **No fabricated legal authority.** A model may not invent a statute, article number, judicial interpretation, or legal source. Legal citations must originate from the legal knowledge layer.
4. **Uncertainty is allowed.** `NEEDS_HUMAN_REVIEW` is preferable to a confident but unsupported answer.
5. **Local-first data handling.** Real contracts, private benchmarks, uploads, OCR outputs, logs containing contract content, vector stores, model caches, and API keys must never be committed to this repository.
6. **Constrained Agent.** Mandatory audit stages are fixed by the system. The Agent may decide when to retry, retrieve more evidence, invoke a visual reviewer, or request a second-model review, but it may not skip required evidence checks.
7. **One verifiable stage per iteration.** Do not implement many half-finished subsystems in a single round.

## Planned architecture

```text
Local UI
  |
  v
FastAPI backend
  |
  +-- document ingestion
  +-- PDF text extraction
  +-- OCR / source evidence
  +-- canonical contract document model
  +-- deterministic rule engine
  +-- legal knowledge base + hybrid retrieval
  +-- LLM provider abstraction
  +-- constrained audit Agent
  +-- local audit result store
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the detailed system boundaries.

## Repository safety

This repository is currently public. Treat every committed file as public information.

Never commit real contracts, re-identifiable pseudonymized contracts, private legal test sets, API keys, `.env` files, private outputs/logs, local indexes, model weights/caches, or OCR outputs containing private contract content. Use only fully fictional public fixtures.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance and research tool. Future model output may be incomplete or wrong and must not be treated as a substitute for professional legal judgment. High-impact findings should remain reviewable by a qualified human.

## Development documents

- [`AGENTS.md`](AGENTS.md) - long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) - the only implementation scope for the current iteration.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) - staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) - public-repository and local-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) - architecture decisions.

## Configuration

Secrets will be supplied through a local `.env` file in later stages. Only `.env.example` belongs in Git.

Model providers and OCR engines must remain replaceable behind explicit interfaces so that changing DeepSeek, Kimi, Qwen, PaddleOCR, or another provider does not require rewriting the audit domain logic.

## License

No open-source license has been selected yet. The repository being public does not by itself grant an open-source license. A license should be chosen only after the project owner explicitly decides how reuse, modification, and redistribution should be permitted.
