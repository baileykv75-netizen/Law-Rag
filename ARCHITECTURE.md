# ARCHITECTURE.md

## 1. System objective

Law-Rag is a local-first contract audit assistant. Its architecture must optimize for evidence traceability, reproducibility, replaceable model providers, controlled Agent behavior, and eventual Windows distribution.

The browser UI is a local application interface. It is not evidence that processing happens in the cloud.

## 2. Target runtime topology

```text
Windows user
  |
  v
Local browser UI
  |
  v
Local FastAPI backend
  |
  +-- document ingestion
  +-- native PDF text parser
  +-- OCR / layout parser
  +-- canonical contract model
  +-- deterministic rule engine
  +-- legal knowledge / retrieval
  +-- LLM provider layer
  +-- constrained Agent
  +-- local persistence
  |
  +---- optional outbound calls ----> configured model APIs
```

Real contract files should remain local by default. External APIs should receive only the minimum necessary content required for the configured analysis path.

## 3. Major components

### 3.1 Frontend

Responsibilities:

- file selection/upload to the local backend;
- processing progress;
- document/page viewer;
- risk list and filters;
- evidence highlighting;
- legal-authority display;
- human review actions;
- settings for model/API configuration without exposing secrets in logs.

The UI must not contain legal reasoning logic.

### 3.2 Backend API

Responsibilities:

- expose a stable local HTTP interface;
- validate input files and limits;
- create audit jobs;
- coordinate application services;
- stream or poll job status;
- serve local result data;
- expose health information for startup diagnostics.

Initial technology target: Python + FastAPI.

### 3.3 Document ingestion

Responsibilities:

- accept PDF/JPG/JPEG/PNG initially;
- compute stable local document IDs;
- detect whether a PDF contains a reliable native text layer;
- avoid OCR when reliable native text already exists;
- render pages for OCR/viewing when necessary;
- preserve page order and source metadata.

### 3.4 OCR / layout layer

Responsibilities:

- detect and recognize text;
- preserve page number and bounding boxes;
- expose confidence when available;
- identify tables and other layout regions when supported;
- support retry/secondary visual review for ambiguous regions later.

PaddleOCR is the planned first OCR family, but domain code must depend on an OCR interface rather than Paddle-specific return objects.

### 3.5 Canonical contract document model

All downstream components should consume one canonical typed representation rather than raw provider outputs.

Planned entities include:

- `SourceDocument`
- `Page`
- `EvidenceBlock`
- `Clause`
- `Table`
- `Party`
- `Amount`
- `DateValue`
- `AttachmentRef`

Every derived object should retain links to one or more evidence blocks.

### 3.6 Deterministic rule engine

Responsibilities:

- arithmetic validation;
- percentage checks;
- date-order checks;
- normalized entity consistency;
- amount consistency;
- required-field checks;
- other explainable deterministic rules.

Rule results must contain evidence IDs and machine-readable rule IDs.

### 3.7 Legal knowledge layer

Legal sources must be version-aware and source-aware.

Planned metadata:

- authority ID;
- law/regulation name;
- authority level/type;
- article number;
- text;
- issuing body;
- publication date;
- effective date;
- repeal/expiry date when applicable;
- status;
- jurisdiction/scope;
- source URL or source manifest;
- version identifier.

Private user contracts do not belong in the legal corpus.

### 3.8 Retrieval layer

Target design is hybrid retrieval:

```text
contract clause/query
  |
  +-- exact citation/article lookup
  +-- lexical/BM25 retrieval
  +-- semantic/vector retrieval
  |
  v
candidate fusion / reranking
  |
  v
legal evidence set
```

Exact legal references should not be forced through semantic search when deterministic lookup is possible.

### 3.9 LLM provider layer

Domain logic should call a provider-neutral interface.

Planned adapters may include:

- DeepSeek;
- Kimi;
- Qwen;
- local OpenAI-compatible endpoints or other approved providers later.

Provider responsibilities:

- request formatting;
- structured-output validation;
- retries/backoff;
- timeout handling;
- token/usage reporting when available;
- provider-specific error normalization.

The provider is not allowed to invent evidence IDs.

### 3.10 Audit reasoning layer

Inputs should include:

- contract clause and necessary context;
- deterministic rule results;
- retrieved legal evidence;
- explicit audit instructions;
- allowed output schema.

Planned `AuditFinding` fields include:

- finding ID;
- risk present/absent/uncertain;
- risk category;
- severity;
- contract evidence IDs;
- legal evidence IDs;
- concise rationale;
- recommendation;
- confidence;
- reviewer status;
- provenance (rule/model/version).

### 3.11 Constrained Agent

The Agent is a bounded orchestration layer, not an unconstrained autonomous actor.

Mandatory pipeline stages remain application-controlled.

Later Agent choices may include:

- retry OCR;
- request visual verification;
- fetch referenced clauses;
- reformulate retrieval queries;
- request secondary model review;
- escalate to human review.

Every callable Agent tool must be allowlisted and auditable.

## 4. Mandatory audit pipeline

Target mandatory sequence:

```text
ingest
  -> extract/recognize evidence
  -> build canonical document
  -> deterministic checks
  -> retrieve relevant legal evidence
  -> semantic audit reasoning
  -> evidence validation
  -> optional secondary review
  -> final human-reviewable findings
```

The Agent may enrich this sequence but may not silently bypass required evidence or validation stages.

## 5. Evidence identity

Evidence IDs must be stable within an audit job and resolvable back to their source.

A future evidence object should support fields similar to:

```json
{
  "evidence_id": "EV-P001-0007",
  "document_id": "DOC-...",
  "page": 1,
  "kind": "text",
  "text": "...",
  "bbox": [0, 0, 100, 20],
  "confidence": 0.98,
  "extractor": "native_pdf|paddleocr|other"
}
```

Exact schema names may evolve, but traceability must not be removed.

## 6. Persistence model

Initial persistence should remain simple and local.

Likely stages:

1. filesystem-based job workspace for early development;
2. SQLite for structured local metadata/results;
3. local vector index only when RAG is implemented.

Do not introduce a remote database before there is a demonstrated need.

## 7. Trust boundaries

### Trusted application instructions

- system/developer prompts owned by Law-Rag;
- explicit configuration;
- allowlisted tool definitions;
- validated schemas.

### Untrusted data

- contract text;
- OCR output;
- embedded PDF text;
- tables;
- attachments;
- external document content;
- retrieved legal text with respect to instructions embedded in the text.

Untrusted data must never be allowed to redefine the tool policy or system instructions.

## 8. Failure states

Prefer explicit states such as:

- `PARSING_FAILED`
- `OCR_LOW_CONFIDENCE`
- `LEGAL_EVIDENCE_INSUFFICIENT`
- `MODEL_UNAVAILABLE`
- `MODEL_OUTPUT_INVALID`
- `EVIDENCE_LINK_BROKEN`
- `MODEL_DISAGREEMENT`
- `NEEDS_HUMAN_REVIEW`

A failed stage must not be rendered as a successful audit.

## 9. Deployment path

Planned progression:

1. local developer launch;
2. stable `setup.bat` / `start.bat` workflow;
3. self-contained Windows-oriented release packaging;
4. optional installer only after local runtime is stable.

Do not optimize for public SaaS deployment during the current product phase.

## 10. Explicit non-goals for early stages

- public user registration;
- cloud multi-tenancy;
- payment systems;
- public legal-advice service;
- unrestricted autonomous browsing;
- automatic submission/filing of legal documents;
- training/fine-tuning on private user contracts.
