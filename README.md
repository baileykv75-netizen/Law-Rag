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

**Stage 0 complete: project foundation.**

No OCR, RAG, LLM, or Agent implementation should be considered complete yet.

The next implementation task is defined in [`CURRENT_TASK.md`](CURRENT_TASK.md).

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

Secrets will be supplied through a local `.env` file. Only `.env.example` belongs in Git.

Model providers and OCR engines must be replaceable behind explicit interfaces so that changing DeepSeek, Kimi, Qwen, PaddleOCR, or another provider does not require rewriting the audit domain logic.

## License

No open-source license has been selected yet. The repository being public does not by itself grant an open-source license. A license should be chosen only after the project owner explicitly decides how reuse, modification, and redistribution should be permitted.
