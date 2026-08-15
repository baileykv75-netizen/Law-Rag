# Law-Rag

Law-Rag is a local-first contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application rather than a generic legal chatbot. Extraction, OCR, canonical structure, deterministic rules, legal evidence and retrieval run locally. External model calls are explicit and receive bounded evidence packages rather than unrestricted raw-file access.

## Product flow

```text
PDF / JPG / PNG
  -> native PDF text when reliable
  -> PaddleOCR only where needed
  -> evidence-grounded Canonical Contract
  -> deterministic audit rules
  -> versioned legal evidence store
  -> exact + BM25 + optional semantic legal retrieval
  -> DeepSeek primary audit
  -> Kimi K3 independent secondary review
  -> deterministic primary/secondary comparison
  -> at most two allowlisted local Agent evidence actions
  -> review-report.json / human review
  -> professional audit workstation
  -> benchmark / Windows hardening
```

## Current status

**Stage 10 complete. Stage 11 active: Benchmark, Hardening, and Windows Release.**

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
- exact citation + SQLite FTS5 trigram/BM25 + optional local BGE legal retrieval;
- coverage/version-aware retrieval and public retrieval benchmark;
- Stage 8 evidence-bounded DeepSeek primary audit with post-model citation/version validation;
- Stage 9 universal one-call-per-contract Kimi K3 independent review;
- deterministic comparison of risk state, severity, contract Evidence sets and Legal Evidence sets;
- validated possible-primary-omission handling;
- application-owned constrained Agent policy with a hard two-action budget;
- allowlisted local evidence tools and explicit forbidden-action boundary;
- local-only `review-report` generation with human-review escalation;
- dedicated `/workspace` professional review surface;
- bounded source-page rendering and Evidence-to-page/span/bbox navigation;
- unified DeepSeek/Kimi/comparison/Agent review queue without rewriting source artifacts;
- Legal Evidence detail with version, `as_of`, provenance and coverage display;
- append-only local `human-review.json` with revision history and stale-report detection;
- keyboard/focus/responsive workstation behavior and explicit missing/integrity states;
- full Stage 1–10 deterministic backend regressions and frontend TypeScript/production build green.

The only active implementation scope is [`CURRENT_TASK.md`](CURRENT_TASK.md).

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

### 3. Build Exact + BM25 retrieval

```text
build-retrieval-index.bat
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

### 6. Configure DeepSeek primary audit

```bat
set DEEPSEEK_API_KEY=<your-local-key>
set DEEPSEEK_BASE_URL=https://api.deepseek.com
set DEEPSEEK_MODEL=deepseek-v4-pro
```

### 7. Configure Kimi secondary review

```bat
set MOONSHOT_API_KEY=<your-local-key>
set MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
set MOONSHOT_MODEL=kimi-k3
```

Never commit real keys or a private `.env` file.

### 8. Start Law-Rag

```text
start-dev.bat
```

Local services:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

Provider health checks only inspect local configuration and do not make paid model requests.

### 9. Open the professional workstation

Open:

```text
http://127.0.0.1:5173/workspace?job=<job-id>
```

The workstation reads persisted local artifacts. Opening a job, navigating pages, filtering findings, resolving Evidence IDs, opening Legal Evidence, and loading human-review history do **not** run OCR/retrieval or call DeepSeek/Kimi.

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
runtime/jobs/<job-id>/secondary-review.json
runtime/jobs/<job-id>/review-report.json
runtime/jobs/<job-id>/human-review.json
runtime/rendered/<job-id>/page-0001.png
runtime/viewer/<job-id>/page-0001.png
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

Public regression gate:

```text
Recall@5 >= 0.90
MRR      >= 0.80
```

This tiny benchmark measures retrieval mechanics on the current 15-article public seed; it is not a production legal-recall claim.

See [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md).

## Stage 8 primary audit

Stage 8 does not send the raw PDF directly to DeepSeek. The application builds a bounded evidence package from canonical clauses, non-PASS rule context, explicit `as_of` and Stage 7 Legal Evidence.

Current DeepSeek default:

```text
model = deepseek-v4-pro
response_format = json_object
thinking = enabled
reasoning_effort = high
```

Before `ai-audit.json` is persisted, application code validates issue IDs, canonical object IDs, contract Evidence IDs, Legal Evidence IDs and legal-version applicability. Model memory cannot create authoritative law.

DeepSeek hidden reasoning content is not persisted.

APIs:

```text
GET  /api/ai/providers/health?provider=deepseek
POST /api/documents/<job-id>/ai-audit
GET  /api/documents/<job-id>/ai-audit
```

See [`docs/AI_AUDIT.md`](docs/AI_AUDIT.md).

## Stage 9 universal Kimi review + constrained Agent

Stage 9 deliberately uses two model calls for every completed audited contract:

```text
Call 1: DeepSeek primary audit
Call 2: Kimi K3 whole-contract secondary review
```

The Kimi call is contract-level, not one call per finding. It receives the same reproducible bounded Stage 8 evidence world and must review every primary finding exactly once.

Default Kimi configuration:

```text
model = kimi-k3
base_url = https://api.moonshot.cn/v1
response_format = json_object
reasoning_effort = max
```

Kimi output passes its own Evidence ID and legal-version validation before comparison.

### Deterministic comparison

Law-Rag does not use another model to decide whether DeepSeek and Kimi agree. It compares validated structured fields:

- primary/secondary risk-state truth table;
- ordinal severity distance;
- contract Evidence ID set intersection/difference;
- Legal Evidence ID set intersection/difference;
- validated possible omissions.

Reasoning prose is shown to humans but is not converted into a fake semantic-agreement percentage.

Representative comparison states:

```text
AGREEMENT
MINOR_DISAGREEMENT
AGREEMENT_WITH_REVIEW
REQUIRES_MORE_EVIDENCE
MATERIAL_DISAGREEMENT
```

### Constrained Agent

The application owns the state machine. The hard follow-up budget is:

```text
maximum actions = 2
```

Allowlisted tools:

```text
inspect_contract_evidence
get_clause_context
inspect_legal_evidence
retrieve_more_legal
resolve_contract_reference
request_ocr_retry
```

Current tools are local-only. There is no arbitrary shell/filesystem tool, unrestricted web legal research, automatic corpus mutation or open-ended Agent loop.

`request_ocr_retry` currently validates whether cited evidence is OCR-derived and returns explicit `UNAVAILABLE` until a bounded retry execution path is configured; it never silently OCRs the whole document again.

If a material disagreement/evidence dispute remains, local tools may gather extra evidence but do not automatically declare one model the winner. The final state remains `HUMAN_REVIEW_REQUIRED` unless the two validated model results were already in agreement/minor disagreement.

### Stage 9 APIs

```text
GET  /api/ai/secondary/health?provider=kimi
POST /api/documents/<job-id>/secondary-review
GET  /api/documents/<job-id>/secondary-review
POST /api/documents/<job-id>/review-report
GET  /api/documents/<job-id>/review-report
```

`POST secondary-review` is the one explicit Kimi external call. `POST review-report` performs only local deterministic comparison and bounded local tools.

See [`docs/SECONDARY_REVIEW.md`](docs/SECONDARY_REVIEW.md).

## Stage 10 professional audit workstation

Stage 10 turns the persisted Stage 2–9 artifacts into one job-centric review surface. It does not create a new reasoning layer.

```text
/workspace?job=<job-id>

left                          center                         right
source page / Evidence   ->  audit queue / filters    ->   DeepSeek + Kimi
OCR/native provenance        comparison / omission          law / Agent trace
page + bbox/span              severity / triage             human decision history
```

### Read-only workspace aggregation

```text
GET /api/documents/<job-id>/workspace
```

The endpoint validates available artifacts and reports `READY`, `MISSING`, `NOT_REQUIRED`, or `INVALID`. A complete-job regression explicitly fails if workspace loading tries to resolve either external model provider.

### Bounded source/Evidence navigation

```text
GET /api/documents/<job-id>/source/pages/<page-number>
GET /api/documents/<job-id>/evidence/<evidence-id>
```

PDF pages use the existing local PDFium renderer and are cached under ignored `runtime/viewer/`. Image jobs expose only their bounded source page. The browser never receives an arbitrary filesystem path.

OCR Evidence keeps bbox/polygon/confidence/coordinate-space metadata. Native PDF Evidence keeps exact quote/character offsets when no trustworthy visual bbox exists; the UI does not invent coordinates.

### Unified review queue

The presentation layer joins, without rewriting:

- DeepSeek primary finding;
- Kimi secondary assessment;
- deterministic comparison state and severity distance;
- contract/Legal Evidence sets;
- validated Kimi possible omissions as separate items;
- relevant bounded Agent action trace.

Filters include severity, comparison state, attention-only and text search. Findings are keyboard-selectable and preserve direct Evidence/Legal Evidence navigation.

### Legal authority context

Clicking a Legal Evidence ID displays the canonical authority/article/version record, effective interval, current `as_of`, coverage type and public source provenance. `CURATED_EXCERPT` is visibly marked; no retrieval score is shown as a legal-confidence percentage.

### Human review layer

```text
GET  /api/documents/<job-id>/human-review
POST /api/documents/<job-id>/human-review/decisions
```

Human states:

```text
UNREVIEWED
CONFIRMED
REJECTED
NEEDS_MORE_REVIEW
```

Each POST appends a new revision to `human-review.json`. The server snapshots the target contract/Legal Evidence references and a SHA-256 fingerprint of the current validated `review-report.json`.

If that report later changes, prior revisions remain in history and are returned with `is_stale=true`; approval is never silently carried forward to a changed audit context.

Human review writes are regression-tested so `review-report.json`, canonical contract, deterministic rules, DeepSeek report, Kimi report, `legal.db` and `retrieval.db` remain byte-for-byte unchanged. Human review never calls an external provider.

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

Optional real integrations remain explicit opt-in tests. Normal CI needs no external API keys and spends no DeepSeek/Kimi credits.

Example Kimi smoke:

```bat
cd backend
set PYTHONPATH=.
set MOONSHOT_API_KEY=<your-local-key>
set LAW_RAG_KIMI_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m kimi_smoke
```

## Core engineering principles

1. **Evidence first.** Material findings trace to exact source evidence.
2. **Native text before OCR.** Reliable PDF text is not degraded unnecessarily.
3. **Deterministic before probabilistic.** Machine-checkable conditions stay in code.
4. **One canonical contract model.** Downstream systems do not independently reinterpret raw PDFs.
5. **Versioned canonical legal evidence.** Legal identity/source/version/coverage survive retrieval.
6. **Hybrid retrieval, not vector-only.** Exact, lexical and semantic channels are complementary.
7. **No fabricated legal authority.** Model citations must originate from supplied canonical Legal Evidence.
8. **Post-model validation, not prompt trust.** Plausible but invalid IDs/versions fail closed.
9. **Two-model agreement is not proof.** Agreement/disagreement remains reviewable structured evidence.
10. **Uncertainty is first-class.** Insufficient corpus/version/source/OCR evidence remains visible.
11. **Constrained Agent.** Mandatory stages, tools and budgets remain application-controlled.
12. **Human decisions are append-only review data.** They never rewrite source, rules, models or legal evidence.
13. **Local-first private data.** External transmission is explicit; private artifacts stay outside Git.
14. **One verifiable stage per iteration.** No broad half-finished rewrites.

## Repository safety

This repository is public. Treat every committed file as public information.

Never commit real contracts, re-identifiable pseudonymized contracts, private expert benchmark labels, API keys, `.env`, private outputs/logs, generated SQLite/index files, model weights/caches, or OCR output containing private contract data.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance/research tool. Rule failures, retrieval scores, model findings, model agreement and human workstation states are not automatically final legal opinions. Material findings remain reviewable by a qualified professional.

## Development documents

- [`AGENTS.md`](AGENTS.md) — long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) — only active implementation scope.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) — public-repository/private-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decisions.
- [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md) — hybrid legal retrieval.
- [`docs/AI_AUDIT.md`](docs/AI_AUDIT.md) — Stage 8 primary audit.
- [`docs/SECONDARY_REVIEW.md`](docs/SECONDARY_REVIEW.md) — Stage 9 Kimi review/comparison/Agent.
- [`legal_data/README.md`](legal_data/README.md) — legal provenance/coverage policy.

## License

No open-source repository license has been selected yet. Public visibility does not by itself grant reuse/redistribution permission; a license should be chosen only after the project owner explicitly decides those terms.
