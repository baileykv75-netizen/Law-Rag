# ARCHITECTURE.md

## 1. System objective

Law-Rag is a local-first contract audit assistant. The architecture optimizes for evidence traceability, reproducibility, replaceable model providers, controlled Agent behavior, explicit uncertainty, human review, and eventual Windows distribution.

The browser UI is a local application interface. It is not evidence that processing happens in the cloud.

## 2. Runtime topology

```text
Windows user
  |
  v
Local React/Vite UI
  |
  v
Local FastAPI backend
  |
  +-- document ingestion / native PDF inspection
  +-- PaddleOCR / PDFium rendering
  +-- canonical contract model
  +-- deterministic rule engine
  +-- versioned legal knowledge + hybrid retrieval
  +-- DeepSeek primary provider boundary
  +-- Kimi secondary provider boundary
  +-- deterministic comparison
  +-- constrained local Agent tools
  +-- professional review workspace
  +-- append-only human review
  +-- local persistence
  |
  +---- explicit outbound calls ----> configured DeepSeek / Kimi APIs
```

Real contract files remain local except for explicitly requested bounded model calls. Workstation navigation, source rendering, Evidence lookup, filtering, Legal Evidence display, and human review do not call external models.

## 3. Major components

### 3.1 Frontend

Current responsibilities:

- local file upload and processing controls;
- legal knowledge/retrieval inspection;
- explicit DeepSeek and Kimi execution controls;
- dedicated `/workspace?job=<job-id>` professional review route;
- page navigation and source zoom;
- Evidence-linked source highlighting;
- unified risk/comparison/omission queue;
- Legal Evidence/version/provenance display;
- Agent trace display;
- human confirm/reject/needs-more-review decisions and revision history.

The frontend contains presentation and interaction logic only. It does not generate legal findings or reinterpret the raw contract.

### 3.2 Backend API

FastAPI exposes bounded local HTTP endpoints. Major responsibilities:

- validate uploads and limits;
- create local jobs;
- expose deterministic pipeline stages;
- expose provider health and explicit model-run APIs;
- expose read-only workstation aggregation/source/Evidence endpoints;
- append human-review revisions;
- normalize errors into explicit HTTP failure states.

The workstation aggregation endpoint deliberately avoids helper functions that create directories when the job does not exist.

### 3.3 Document ingestion

Supported input:

- PDF;
- JPG/JPEG;
- PNG.

The ingestion layer:

- stores the source under the ignored local runtime tree;
- validates signatures/size/media type;
- preserves 1-based page identity;
- prefers reliable native PDF text;
- classifies pages as native-text usable or OCR-required;
- persists stable page Evidence IDs.

### 3.4 OCR / layout layer

Current implementation:

- provider-neutral OCR boundary;
- PaddleOCR 3.7.0 / PaddlePaddle CPU 3.3.0 optional local runtime;
- PP-OCRv6 medium detection/recognition default;
- pypdfium2/PDFium rendering for OCR-required PDF pages;
- OCR block text, confidence, bbox/polygon, page coordinate space and provider provenance;
- explicit low-confidence/no-text/failure states.

Reliable native text is not OCRed by default.

### 3.5 Canonical contract model

`contract.json` is the downstream contract source of truth.

Canonical entities include clauses, parties, dates, money, percentages, identifiers, references, structured blocks and reusable `SourceSpan` records. Derived objects retain Evidence IDs and page/span/bbox provenance.

Rules, retrieval, models, comparison and workstation views consume the canonical contract rather than independently rereading the raw PDF.

### 3.6 Deterministic rule engine

The rule engine owns machine-checkable checks such as arithmetic/percentage/date/entity consistency.

States:

```text
PASS
FAIL
REVIEW
NOT_APPLICABLE
```

`FAIL` means a configured machine condition failed; it is not itself a legal conclusion.

### 3.7 Versioned legal knowledge

Canonical legal identity is:

```text
authority
  -> authority version
       -> article / Legal Evidence ID
```

The local SQLite store preserves source hashes, official-source provenance, effective intervals, status and coverage semantics (`FULL_TEXT` / `CURATED_EXCERPT`).

Applicability is deterministic:

```text
effective_date <= as_of < end_date_exclusive
```

Private user contracts never enter the legal corpus.

### 3.8 Hybrid legal retrieval

```text
query + as_of
  |
  +-- exact article/citation lookup
  +-- SQLite FTS5 trigram + BM25
  +-- optional local BGE semantic channel
  |
  v
weighted reciprocal-rank fusion
  |
  v
applicable versioned Legal Evidence IDs
```

Retrieval ranking is not a legal-confidence percentage. Corpus/version insufficiency remains explicit even when similar candidates exist.

### 3.9 Model provider layer

Domain logic depends on provider-neutral interfaces.

Current adapters:

- DeepSeek primary audit provider;
- Kimi K3 secondary review provider.

Provider responsibilities include request formatting, timeout/retry behavior, structured output normalization and safe metadata capture. Hidden reasoning content is not persisted.

Provider responses are not trusted merely because they match JSON shape. Application code validates IDs, evidence membership and legal-version applicability before persistence.

### 3.10 Dual-model audit reasoning

Mandatory reasoning topology for a completed audited contract:

```text
validated canonical/rule/RAG context
    -> one DeepSeek primary call
    -> deterministic validation
    -> one Kimi contract-level secondary call
    -> independent deterministic validation
    -> structured comparison
```

The application compares risk state, ordinal severity distance, contract Evidence sets, Legal Evidence sets and validated possible omissions. It does not use a third model to judge model agreement.

### 3.11 Constrained Agent

The Agent is a bounded evidence-gathering layer after dual-model comparison.

Hard action budget:

```text
maximum follow-up actions = 2
```

Current allowlist:

```text
inspect_contract_evidence
get_clause_context
inspect_legal_evidence
retrieve_more_legal
resolve_contract_reference
request_ocr_retry
```

No arbitrary shell, unrestricted filesystem action, open-ended browsing, automatic corpus mutation or third-model vote is available.

The Agent may gather additional material, but unresolved material disagreement remains `HUMAN_REVIEW_REQUIRED`; finding new evidence is not automatic authority to declare one model the winner.

## 4. Mandatory audit pipeline

Current application-controlled sequence:

```text
ingest
  -> native/OCR evidence
  -> canonical contract
  -> deterministic checks
  -> versioned legal retrieval
  -> DeepSeek primary audit
  -> primary validation
  -> Kimi secondary review
  -> secondary validation
  -> deterministic comparison
  -> optional bounded local Agent evidence actions
  -> review-report.json
  -> professional workstation / human review
```

No Agent or UI component may silently skip required evidence/validation stages.

## 5. Evidence identity and source viewing

Evidence IDs are stable within a job and resolvable to source.

Stage 10 exposes bounded APIs:

```text
GET /api/documents/<job-id>/source/pages/<page-number>
GET /api/documents/<job-id>/evidence/<evidence-id>
```

PDF pages are rendered locally with the existing PDFium renderer into ignored viewer cache files. Image jobs expose their one bounded source page. Arbitrary user-supplied local paths are never accepted.

OCR Evidence can return bbox/polygon/confidence and the image coordinate space. Native-text Evidence returns exact quote/character offsets when visual coordinates are unavailable. The UI must never fabricate a bbox.

## 6. Professional review workspace

The dedicated job-centric route is:

```text
/workspace?job=<job-id>
```

Desktop-first layout:

```text
left                    center                     right
source/page viewer      audit/triage queue         evidence/review context
Evidence highlight      filters/comparison         DeepSeek + Kimi
processing history      possible omissions         law/version/provenance
                                                   Agent trace
                                                   human decision history
```

Read-only aggregation:

```text
GET /api/documents/<job-id>/workspace
```

The summary reports per-stage `READY`, `MISSING`, `NOT_REQUIRED` or `INVALID`. Missing/corrupt artifacts remain explicit. Tests assert both partial and complete job navigation are provider-free.

## 7. Human review boundary

Human review is a separate persistence layer:

```text
runtime/jobs/<job-id>/human-review.json
```

States:

```text
UNREVIEWED
CONFIRMED
REJECTED
NEEDS_MORE_REVIEW
```

APIs:

```text
GET  /api/documents/<job-id>/human-review
POST /api/documents/<job-id>/human-review/decisions
```

Each POST appends a revision containing the target, note, timestamp, server-derived contract/Legal Evidence snapshot and current `review-report.json` fingerprint.

Human review never overwrites source evidence, canonical contract, deterministic rules, DeepSeek/Kimi reports, review-report, legal store or retrieval index. A regression test protects those artifacts byte-for-byte.

If `review-report.json` changes, earlier revisions remain in history and are surfaced as stale rather than silently carried forward.

## 8. Local persistence

Current ignored runtime layout includes:

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
runtime/rendered/<job-id>/...
runtime/viewer/<job-id>/...
runtime/legal/legal.db
runtime/legal/retrieval.db
```

Remote persistence is not part of the current product architecture.

## 9. Trust boundaries

### Trusted application controls

- system/developer instructions owned by Law-Rag;
- explicit local configuration;
- validated schemas;
- deterministic validators;
- allowlisted Agent tools and action budget;
- versioned legal-source metadata.

### Untrusted data

- contract text;
- OCR output;
- embedded PDF text;
- tables/attachments;
- external document content;
- retrieved legal text with respect to any instructions embedded inside it;
- model-generated prose/IDs until validated.

Untrusted content cannot redefine system instructions, tool policy or evidence identity.

## 10. Failure states

Explicit states are preferred over silent fallback, including:

- `OCR_LOW_CONFIDENCE` / `OCR_FAILED`;
- `INSUFFICIENT_CORPUS` / version ambiguity;
- model unavailable / invalid output;
- unresolved Evidence ID;
- model disagreement;
- `HUMAN_REVIEW_REQUIRED`;
- workspace artifact `MISSING` / `INVALID`;
- stale human decision.

A failed/incomplete stage must not be rendered as an approved legal result.

## 11. Deployment path

Progression:

1. local developer launch — complete;
2. stable local processing/audit/workstation — complete through Stage 10;
3. benchmark + runtime hardening — Stage 11 active;
4. self-contained Windows-oriented release bundle;
5. optional installer only after bundle/runtime behavior is proven.

Do not optimize for public SaaS deployment during the current product phase.

## 12. Explicit non-goals

- public user registration/cloud multi-tenancy;
- payment systems;
- public legal-advice service;
- unrestricted autonomous browsing;
- automatic filing/submission of legal documents;
- training/fine-tuning on private user contracts;
- automatic final legal approval;
- third-model voting as a substitute for evidence/human review.
