# Law-Rag

Law-Rag is a local-first intelligent contract audit assistant designed for personal research, testing, and professional review workflows.

The project goal is not to build a generic legal chatbot. The target product is a Windows-friendly local application that can ingest contracts, preserve source evidence, retrieve relevant legal rules, run deterministic checks, use large language models for semantic risk analysis, and keep every important conclusion traceable to its supporting evidence.

## Product goal

Target user flow:

```text
Start Law-Rag locally
  -> open local web UI
  -> upload PDF / JPG / PNG contract
  -> parse native PDF text when reliable
  -> use OCR only when needed
  -> reconstruct clauses / tables / parties / dates / amounts
  -> run deterministic audit rules
  -> retrieve current legal authorities
  -> perform LLM-assisted risk analysis
  -> invoke secondary review only when needed
  -> show risk + contract evidence + legal evidence + review state
```

The intended final form is a downloadable local application. The browser is only the user interface; the contract processing backend runs locally unless a configured external model API is explicitly called.

## Current status

**Stage 1 complete. Stage 2 active: document ingestion and native PDF text path.**

Stage 1 established the runnable local shell: React/Vite UI, FastAPI backend, validated local-only file ingestion, Windows development setup/start scripts, regression tests, and GitHub Actions CI. Backend tests and the frontend production build have passed in GitHub Actions.

The next implementation scope is strictly defined in [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 2 will decide when PDF native text is reliable enough to preserve directly and when a page/document must later be routed to OCR. PaddleOCR itself is still out of scope until Stage 3.

## Stage 1 quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended. Vite 8 requires Node.js 20.19+ or 22.12+.

No DeepSeek/Kimi/Qwen API key is required for Stage 1.

### First setup

Download/clone the repository, then double-click:

```text
setup-dev.bat
```

This creates a local Python virtual environment, installs FastAPI dependencies, and installs frontend npm dependencies.

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

The frontend should open automatically in the browser. Two terminal windows remain open while Law-Rag is running; closing them stops the local application.

### Current Stage 1 behavior

You can select or drag one:

- `.pdf`
- `.jpg`
- `.jpeg`
- `.png`

up to 50 MiB. The backend validates the basic type/signature, generates a UUID job ID, and stores the file only under:

```text
runtime/uploads/<job-id>/source.<ext>
```

`runtime/` is ignored by Git.

At the Stage 1 boundary the application returns file metadata only. Stage 2 will add document inspection; legal conclusions remain much later in the roadmap.

## Developer validation

Backend:

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

GitHub Actions runs backend tests and the frontend production build on pushes and pull requests to `main`.

## Core engineering principles

1. **Evidence first.** Every material audit finding must be traceable to exact contract evidence and, when it is a legal conclusion, to retrieved legal evidence.
2. **Deterministic before probabilistic.** Arithmetic, date consistency, party-name consistency, percentage totals, duplicate values, and other rule-based checks should not be delegated to an LLM when ordinary code can verify them.
3. **No fabricated legal authority.** A model may not invent a statute, article number, judicial interpretation, or legal source. Legal citations must originate from the legal knowledge layer.
4. **Uncertainty is allowed.** `NEEDS_HUMAN_REVIEW` is preferable to a confident but unsupported answer.
5. **Local-first data handling.** Real contracts, private benchmarks, uploads, OCR outputs, logs containing contract content, vector stores, model caches, and API keys must never be committed to this repository.
6. **Constrained Agent.** Mandatory audit stages are fixed by the system. The Agent may decide when to retry, retrieve more evidence, invoke a visual reviewer, or request a second model review, but it may not skip required evidence checks.
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
  +-- OCR / document layout parsing
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

Never commit:

- real contracts;
- merely pseudonymized contracts that remain re-identifiable;
- private legal test sets;
- API keys, tokens, passwords, cookies, or credentials;
- `.env` files;
- uploads or generated audit reports containing private content;
- local vector databases or logs containing contract text.

Use only fully fictional test fixtures in the public repository.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance and research tool. Model output may be incomplete or wrong and must not be treated as a substitute for professional legal judgment. High-impact findings should remain reviewable by a qualified human.

## Development documents

- [`AGENTS.md`](AGENTS.md) - long-term development rules for AI coding agents and contributors.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) - the only implementation scope for the current iteration.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) - staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) - public-repository and local-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) - architectural decisions that should not be silently reversed.

## Configuration

Secrets will be supplied through a local `.env` file in later stages. Only `.env.example` belongs in Git.

Model providers and OCR engines must be replaceable behind explicit interfaces so that changing DeepSeek, Kimi, Qwen, PaddleOCR, or another provider does not require rewriting the audit domain logic.

## License

No open-source license has been selected yet. The repository being public does not by itself grant an open-source license. A license should be chosen only after the project owner explicitly decides how reuse, modification, and redistribution should be permitted.
