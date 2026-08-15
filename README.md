# Law-Rag

Law-Rag is a local-first intelligent contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application rather than a generic legal chatbot. Contract ingestion, OCR, canonical structure, deterministic rules and legal retrieval run locally. Stage 8 can intentionally send a bounded evidence package to a configured external DeepSeek API for primary reasoning.

## Product flow

```text
PDF / JPG / PNG
  -> native PDF text when reliable
  -> PaddleOCR only where needed
  -> evidence-grounded Canonical Contract
  -> deterministic audit rules
  -> versioned legal evidence store
  -> exact + BM25 + optional semantic legal retrieval
  -> evidence-grounded primary LLM audit
  -> bounded secondary review / Agent
  -> professional human-review workstation
```

## Current status

**Stage 8 complete. Stage 9 active: Constrained Agent and Secondary Review.**

Completed foundations include:

- React/Vite + FastAPI local application shell;
- validated PDF/JPG/PNG ingestion;
- native PDF text / OCR-required / mixed page routing;
- PaddleOCR local CPU path with PP-OCRv6 medium default;
- page/Evidence IDs, OCR coordinates/confidence and provenance;
- canonical contract schema `1.0.0` with clauses, parties, dates, money, percentages, identifiers and source spans;
- deterministic audit rules with `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE` states;
- local `contract.json` and `audit-rules.json` job artifacts;
- canonical versioned legal schema `1.0.0` in local SQLite;
- authority -> version -> article / Legal Evidence ID identity;
- source/article SHA-256 hashes and official-source provenance;
- historical legal-version retention and explicit `as_of` resolution;
- `CURATED_EXCERPT` coverage semantics;
- verified public contract-relevant legal seed: 2 authorities / 2 versions / 15 articles;
- deterministic exact article/citation retrieval;
- SQLite FTS5 trigram + `bm25()` lexical retrieval for Chinese legal text;
- provider-neutral embedding interface and optional local `BAAI/bge-small-zh-v1.5` semantic retrieval;
- deterministic weighted reciprocal-rank fusion with exact-hit priority;
- stale retrieval-index detection through canonical legal-source fingerprint;
- coverage-aware retrieval states such as `INSUFFICIENT_CORPUS`, `NO_APPLICABLE_VERSION`, and `VERSION_AMBIGUOUS`;
- public retrieval benchmark enforced in backend CI;
- real Windows BGE semantic smoke verified through opt-in GitHub Actions;
- versioned Stage 8 AI-audit schema and deterministic audit-context builder;
- provider-neutral `PrimaryAuditProvider` boundary;
- current DeepSeek V4-Pro HTTP adapter with JSON Output + thinking mode;
- explicit prompt-injection boundary treating contract/legal text as untrusted data;
- deterministic post-model validation of issue IDs, contract Evidence IDs, Legal Evidence IDs and legal-version applicability;
- explicit evidence sufficiency states and corpus/OCR/version uncertainty propagation;
- atomic local `ai-audit.json` persistence only after validation succeeds;
- provider failures/invalid model output cannot overwrite a previous valid report;
- primary-provider health + POST/GET AI-audit APIs;
- minimal Stage 8 primary-audit inspection UI;
- deterministic fake-provider CI, DeepSeek request-contract tests, stale-version guard and optional real DeepSeek smoke;
- all Stage 1–8 deterministic backend regressions and frontend TypeScript/production build green.

The only active implementation scope is [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 9 may add bounded secondary review and Agent actions; the mandatory pipeline remains application-controlled.

## Quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

### 1. Base setup

```text
setup-dev.bat
```

### 2. Build the verified legal seed database

```text
rebuild-legal-seed.bat
```

Generated local artifacts:

```text
runtime/legal/legal.db
runtime/legal/import_reports/last-import-report.json
```

### 3. Build the exact + BM25 retrieval index

```text
build-retrieval-index.bat
```

Generated artifact:

```text
runtime/legal/retrieval.db
```

### 4. Optional local semantic retrieval

```text
setup-rag-semantic-cpu.bat
build-retrieval-index-semantic.bat
```

Initial local embedding provider:

```text
BAAI/bge-small-zh-v1.5
```

Exact + BM25 remain usable without this optional semantic stack.

### 5. Optional OCR runtime

For scanned PDFs/images:

```text
setup-ocr-cpu.bat
```

Pinned OCR path:

- PaddlePaddle CPU 3.3.0;
- PaddleOCR 3.7.0;
- `PP-OCRv6_medium_det`;
- `PP-OCRv6_medium_rec`.

### 6. Configure DeepSeek for Stage 8 primary audit

Keep the key only in your local environment/private secret workflow:

```bat
set DEEPSEEK_API_KEY=<your-local-key>
set DEEPSEEK_BASE_URL=https://api.deepseek.com
set DEEPSEEK_MODEL=deepseek-v4-pro
```

Never commit the real key or `.env` file.

### 7. Start Law-Rag

```text
start-dev.bat
```

Local services:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

The Stage 8 panel reports provider configuration without making a paid/network request. Only clicking the primary-audit action sends the selected evidence package to the configured external provider.

## Local runtime artifacts

Private/generated artifacts stay under ignored runtime paths:

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

## Deterministic rule semantics

```text
PASS
  configured machine condition holds

FAIL
  configured machine condition does not hold
  != illegal / invalid / unenforceable

REVIEW
  ambiguity, parser/source/OCR uncertainty, or intent requires verification

NOT_APPLICABLE
  explicit context is insufficient to run the rule safely
```

Machine-checkable issues remain ordinary code rather than being delegated to an LLM.

## Versioned legal evidence

Canonical legal evidence uses:

```text
authority
  -> authority version
       -> exact article / Legal Evidence ID
```

Example:

```text
legal:prc-civil-code:effective-2021-01-01:article-585
```

Applicability uses:

```text
effective_date <= as_of < end_date_exclusive
```

The checked-in public seed is deliberately `CURATED_EXCERPT`:

- Civil Code: selected articles 469, 496, 497, 502, 509, 577, 585, 586;
- SPC contract-general interpretation: selected articles 1, 3, 9, 10, 16, 65, 69.

**Absence from this seed is never evidence that no legal rule exists.**

## Stage 7 hybrid legal retrieval

```text
query + as_of
      ↓
legal version resolution
      ↓
EXACT
+ FTS5 trigram / BM25
+ optional local BGE vectors
      ↓
weighted reciprocal-rank fusion
      ↓
versioned Legal Evidence IDs
+ provenance
+ corpus/version warnings
```

Retrieval APIs:

```text
GET  /api/legal/retrieval/summary
POST /api/legal/retrieve
```

Public benchmark gate:

```text
Recall@5 >= 0.90
MRR      >= 0.80
```

This tiny benchmark measures mechanics on the current 15-article public seed; it is not a production legal-recall claim.

See [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md).

## Stage 8 evidence-grounded primary audit

Stage 8 does **not** send the raw PDF directly to a model. The deterministic context builder starts from:

```text
contract.json
+ audit-rules.json
+ explicit as_of
        ↓
bounded legal-topic map
        ↓
Stage 7 retrieval
        ↓
AuditContextPackage
        ↓
DeepSeek primary reasoning
        ↓
strict JSON + deterministic validation
        ↓
ai-audit.json
```

Current bounded topics:

- 格式条款;
- 违约金;
- 定金;
- 合同生效;
- 合同履行;
- 违约责任;
- 合同形式;
- 合同成立.

### DeepSeek adapter

The implementation re-verified the current official API contract on 2026-08-15 and defaults to:

```text
model = deepseek-v4-pro
response_format = {"type":"json_object"}
thinking = {"type":"enabled"}
reasoning_effort = high
```

The old `deepseek-chat` / `deepseek-reasoner` aliases are not used.

### Post-model firewall

Before any new report is persisted, Law-Rag rejects:

- malformed/non-schema JSON;
- duplicate model finding IDs;
- invented issue IDs;
- invented canonical object IDs;
- invented contract Evidence IDs;
- invented Legal Evidence IDs;
- Legal Evidence IDs outside the cited retrieval issue;
- legal versions not applicable on `as_of`;
- supported findings without both contract and legal evidence.

Incomplete legal corpus, ambiguous versions and uncertain OCR remain visible as evidence-sufficiency/review states. A model cannot erase those warnings.

DeepSeek `reasoning_content` is not persisted. Only validated final structured `content`, safe request metadata and response hashes are retained.

AI-audit APIs:

```text
GET  /api/ai/providers/health?provider=deepseek
POST /api/documents/<job-id>/ai-audit
GET  /api/documents/<job-id>/ai-audit
```

See [`docs/AI_AUDIT.md`](docs/AI_AUDIT.md).

## Developer validation

Backend deterministic suite:

```bat
cd backend
set PYTHONPATH=.
..\.venv\Scripts\python.exe -m pytest -q
```

Frontend typecheck + production build:

```bat
cd frontend
npm run build
```

`npm run build` executes `tsc --noEmit` before Vite production build.

Optional real OCR smoke:

```bat
cd backend
set PYTHONPATH=.
set LAW_RAG_OCR_SMOKE_IMAGE=C:\path\to\fictional-test-image.png
..\.venv\Scripts\python.exe -m pytest -q -m ocr_smoke
```

Optional real semantic smoke:

```bat
cd backend
set PYTHONPATH=.
set LAW_RAG_RAG_SEMANTIC_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m rag_semantic_smoke
```

Optional **paid/network** DeepSeek smoke using synthetic empty context only:

```bat
cd backend
set PYTHONPATH=.
set DEEPSEEK_API_KEY=<your-local-key>
set LAW_RAG_DEEPSEEK_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m deepseek_smoke
```

Normal CI does not require API keys and does not spend external-model credits.

## Core engineering principles

1. **Evidence first.** Material findings must trace to exact source evidence.
2. **Native text before OCR.** Do not degrade reliable PDF text unnecessarily.
3. **Deterministic before probabilistic.** Machine-checkable conditions stay in code.
4. **One canonical contract model.** Downstream systems do not independently reinterpret raw PDFs.
5. **Versioned canonical legal evidence.** Legal identity/source/version/coverage survive retrieval.
6. **Hybrid retrieval, not vector-only.** Exact, lexical and semantic channels are complementary.
7. **No fabricated legal authority.** Model citations must originate from supplied canonical Legal Evidence.
8. **Post-model validation, not prompt trust.** A valid-looking answer is rejected if its IDs/version/evidence do not validate.
9. **Uncertainty is first-class.** Insufficient corpus/version ambiguity/source uncertainty stay visible.
10. **Local-first private data.** Contracts, outputs, indexes, model caches and secrets remain outside Git; external transmission is explicit.
11. **Constrained Agent.** Mandatory stages remain application-controlled.
12. **One verifiable stage per iteration.** No broad half-finished rewrites.

## Repository safety

This repository is public. Treat every committed file as public information.

Never commit real contracts, re-identifiable pseudonymized contracts, private expert benchmark labels, API keys, `.env`, private outputs/logs, generated SQLite/index files, model weights/caches, or OCR output containing private contract data.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance/research tool. Rule failures, retrieval scores and AI findings are not automatically final legal opinions. High-impact findings must remain reviewable by a qualified professional.

## Development documents

- [`AGENTS.md`](AGENTS.md) — long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) — only active implementation scope.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) — public-repository/private-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decisions.
- [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md) — Stage 7 retrieval design and validation.
- [`docs/AI_AUDIT.md`](docs/AI_AUDIT.md) — Stage 8 primary audit design and validation.
- [`legal_data/README.md`](legal_data/README.md) — legal provenance/coverage policy.

## License

No open-source repository license has been selected yet. Public visibility does not by itself grant reuse/redistribution permission; a license should be chosen only after the project owner explicitly decides those terms.
