# Law-Rag

Law-Rag is a local-first intelligent contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application rather than a generic legal chatbot. Private contract processing remains local by default; external model APIs are introduced only in explicit later stages.

## Product flow

```text
PDF / JPG / PNG
  -> native PDF text when reliable
  -> PaddleOCR only where needed
  -> evidence-grounded Canonical Contract
  -> deterministic audit rules
  -> versioned legal evidence store
  -> exact + BM25 + optional semantic legal retrieval
  -> primary evidence-grounded LLM audit
  -> bounded secondary review / Agent
  -> professional human-review workstation
```

## Current status

**Stage 7 complete. Stage 8 active: Primary LLM Audit Reasoning.**

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
- Stage 6 verified public contract-relevant seed: 2 authorities / 2 versions / 15 articles;
- deterministic exact article/citation retrieval;
- SQLite FTS5 trigram + `bm25()` lexical retrieval for Chinese legal text;
- provider-neutral embedding interface;
- optional local `BAAI/bge-small-zh-v1.5` semantic retrieval;
- deterministic weighted reciprocal-rank fusion with exact-hit priority;
- stale retrieval-index detection through canonical legal-source fingerprint;
- coverage-aware states such as `INSUFFICIENT_CORPUS`, `NO_APPLICABLE_VERSION`, and `VERSION_AMBIGUOUS`;
- legal knowledge and hybrid retrieval inspection panels in the local UI;
- public retrieval benchmark enforced in backend CI;
- real Windows BGE semantic smoke verified through opt-in GitHub Actions;
- all prior backend regressions and frontend production build green.

The only active implementation scope is [`CURRENT_TASK.md`](CURRENT_TASK.md). Stage 8 introduces one primary LLM provider and strict post-model evidence/citation validation; it does **not** introduce a second reviewer model or free-form Agent.

## Quick start on Windows

### Prerequisites

Install:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

### 1. Base setup

```text
setup-dev.bat
```

This creates the local Python environment and installs the base backend/frontend dependencies.

### 2. Build the verified legal seed database

```text
rebuild-legal-seed.bat
```

Generated local artifacts:

```text
runtime/legal/legal.db
runtime/legal/import_reports/last-import-report.json
```

A failed rebuild does not replace a previously valid legal database.

### 3. Build the exact + BM25 retrieval index

```text
build-retrieval-index.bat
```

This creates:

```text
runtime/legal/retrieval.db
```

Exact lookup itself does not require this derivative index, but BM25 retrieval does.

### 4. Optional local semantic retrieval

Install the optional semantic runtime:

```text
setup-rag-semantic-cpu.bat
```

Then rebuild the retrieval index with local BGE vectors:

```text
build-retrieval-index-semantic.bat
```

The initial real provider is:

```text
BAAI/bge-small-zh-v1.5
```

Exact + BM25 remain usable without installing this optional semantic stack.

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

### 6. Start Law-Rag

```text
start-dev.bat
```

Local services:

```text
Backend:  http://127.0.0.1:8000
Frontend: http://127.0.0.1:5173
```

## Local runtime artifacts

Private/generated artifacts stay under ignored runtime paths:

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

Stage 8 will add a validated local primary-model audit artifact only after the provider/citation-validation boundary is implemented.

## Stage 5 deterministic audit semantics

Rule states are intentionally narrow:

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

Machine-checkable issues remain deterministic code rather than being delegated to an LLM.

## Stage 6 versioned legal evidence

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

Applicability uses explicit half-open version intervals:

```text
effective_date <= as_of < end_date_exclusive
```

Resolution states include:

- `RESOLVED`;
- `NO_APPLICABLE_VERSION`;
- `AMBIGUOUS`.

The checked-in public seed is deliberately small and explicitly marked `CURATED_EXCERPT`:

- Civil Code: selected articles 469, 496, 497, 502, 509, 577, 585, 586;
- SPC Civil Code contract-general interpretation: selected articles 1, 3, 9, 10, 16, 65, 69.

**Absence from this seed is never evidence that no legal rule exists.**

## Stage 7 hybrid legal retrieval

### Retrieval channels

```text
query + as_of
      ↓
legal version resolution
      ↓
EXACT
+ FTS5 trigram / BM25
+ optional local BGE semantic vectors
      ↓
weighted reciprocal-rank fusion
      ↓
versioned Legal Evidence IDs
+ per-channel provenance
+ corpus/version warnings
```

Hard rules:

- exact authority/article citations are deterministic and remain ahead of probabilistic candidates;
- final candidates must be applicable on the requested `as_of` date;
- historical/not-yet-effective versions are not silently mixed into current results;
- duplicate Evidence IDs from several channels are fused rather than duplicated;
- every candidate keeps per-channel rank/raw score/contribution and final fused score;
- an explicitly requested article missing from `CURATED_EXCERPT` returns `INSUFFICIENT_CORPUS`, even if BM25 finds similar neighboring articles;
- retrieval score is not a legal correctness probability or legal conclusion.

### Retrieval APIs

```text
GET  /api/legal/retrieval/summary
POST /api/legal/retrieve
```

Example request:

```json
{
  "query": "民法典第五百八十五条违约金",
  "as_of": "2026-08-15",
  "top_k": 8,
  "use_semantic": false
}
```

See [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md) for implementation/validation details.

### Retrieval benchmark

Checked-in public fixture:

```text
legal_data/fixtures/retrieval_benchmark.json
```

Normal backend CI rebuilds the legal store/index and enforces the current baseline gate:

```text
Recall@5 >= 0.90
MRR      >= 0.80
```

This tiny benchmark measures retrieval mechanics on the 15-article public seed. It does not represent production legal-corpus recall. Broader expert-labeled testing remains a later requirement.

### Real semantic smoke

The optional Windows integration path has been verified with real `BAAI/bge-small-zh-v1.5` embeddings: the job installs the semantic stack, downloads/loads the model, embeds the verified seed and performs a Chinese liquidated-damages retrieval assertion.

Normal CI does not repeatedly download the model. The opt-in job is triggered only when intentionally requested.

## Stage 8 boundary

Stage 8 will add one primary generative audit provider, DeepSeek planned first after current official API verification.

The model will receive only a deterministic package built from:

```text
contract.json
+ audit-rules.json
+ Stage 7 retrieval results / Legal Evidence
+ explicit as_of and uncertainty metadata
```

It may not invent contract Evidence IDs, Legal Evidence IDs, law versions or source text. Model output must pass strict schema and citation validation before being persisted as a finding.

Second-model review and Agent behavior remain Stage 9.

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

## Core engineering principles

1. **Evidence first.** Material findings must trace to exact source evidence.
2. **Native text before OCR.** Do not degrade reliable PDF text unnecessarily.
3. **Deterministic before probabilistic.** Machine-checkable conditions stay in code.
4. **One canonical contract model.** Downstream systems do not independently reinterpret raw PDFs.
5. **Versioned canonical legal evidence.** Legal identity/source/version/coverage survive retrieval.
6. **Hybrid retrieval, not vector-only.** Exact, lexical and semantic channels are complementary.
7. **No fabricated legal authority.** Future citations must originate from canonical Legal Evidence.
8. **Uncertainty is first-class.** Insufficient corpus/version ambiguity/source uncertainty stay visible.
9. **Local-first private data.** Contracts, outputs, indexes, model caches and secrets remain outside Git.
10. **Constrained Agent.** Mandatory stages remain application-controlled.
11. **One verifiable stage per iteration.** No broad half-finished rewrites.

## Repository safety

This repository is public. Treat every committed file as public information.

Never commit:

- real contracts;
- re-identifiable pseudonymized contracts;
- private expert benchmark labels;
- API keys or `.env` files;
- private outputs/logs;
- generated SQLite/index files;
- model weights/caches;
- OCR output containing private contract data.

Use only fictional public fixtures unless a public legal source has been intentionally verified and curated.

See [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).

## Legal-use boundary

Law-Rag is an audit-assistance/research tool. Rule failures, retrieval scores and future model findings are not automatically final legal opinions. High-impact findings must remain reviewable by a qualified professional.

## Development documents

- [`AGENTS.md`](AGENTS.md) — long-term development rules.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries and target architecture.
- [`CURRENT_TASK.md`](CURRENT_TASK.md) — only active implementation scope.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — staged delivery plan.
- [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md) — public-repository/private-data rules.
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decisions.
- [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md) — Stage 7 retrieval design and validation.
- [`legal_data/README.md`](legal_data/README.md) — legal provenance/coverage policy.

## License

No open-source repository license has been selected yet. Public visibility does not by itself grant reuse/redistribution permission; a license should be chosen only after the project owner explicitly decides those terms.
