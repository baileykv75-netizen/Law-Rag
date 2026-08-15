# Law-Rag Development Roadmap

This roadmap is intentionally staged. Each stage should be independently testable before the next one begins.

## Stage 0 — Project foundation

Status: complete.

Deliverables:

- project definition;
- long-term agent/contributor rules;
- architecture boundaries;
- data-safety rules;
- current-task mechanism;
- configuration and ignore policy.

## Stage 1 — Local application shell

Status: complete.

Validated deliverables:

- React/Vite local UI;
- FastAPI backend;
- supported file selection/upload;
- local ignored runtime storage;
- health endpoint;
- backend regression tests;
- Windows-oriented `setup-dev.bat` and `start-dev.bat`;
- developer startup documentation;
- GitHub Actions validation for backend tests and frontend production build.

## Stage 2 — Document ingestion and native PDF path

Status: complete.

Validated deliverables:

- PDF/JPG/PNG document ingestion;
- stable local job IDs;
- page-level native PDF text extraction using pypdf;
- explicit deterministic native-text reliability heuristic;
- `NATIVE_TEXT`, `OCR_REQUIRED`, and `MIXED` routing;
- stable page Evidence IDs and page-number linkage;
- local `document.json` and `evidence.json` persistence;
- explicit corrupt-PDF failure;
- UI page/route summary;
- regression coverage and CI.

## Stage 3 — OCR and layout evidence layer

Status: complete.

Validated deliverables:

- provider-neutral OCR interface;
- PaddleOCR 3.7.0 local adapter with lazy loading;
- accuracy-first PP-OCRv6 medium default;
- optional PaddlePaddle 3.3.0 CPU installation path for Windows;
- pypdfium2/PDFium page renderer;
- OCR only for `OCR_REQUIRED` PDF pages;
- original-image OCR for JPG/JPEG/PNG;
- stable OCR block IDs, page, bbox/polygon, confidence and provider provenance;
- explicit complete/low-confidence/no-text/failure states;
- mixed native/OCR evidence preservation;
- Windows dependency smoke verification;
- deterministic regression coverage and CI.

## Stage 4 — Canonical contract structure

Status: complete.

Validated deliverables:

- dedicated versioned canonical contract schema (`1.0.0`);
- one ordered evidence abstraction over native PDF lines and OCR blocks;
- native character offsets plus OCR coordinate/confidence provenance retained in reusable source spans;
- conservative Chinese/Arabic clause parsing for `第X条`, `一、`, `（一）`, `1.`, `1.1`, `1.1.1`, `（1）` and related forms;
- deterministic parent/child clause relationships and cross-page clause continuation;
- party-role/name mentions without entity-equivalence judgment;
- explicit Chinese/ISO-style dates with safe normalization and invalid-date states;
- explicit money and percentage mentions with deterministic normalization when possible;
- labelled contract/project/agreement identifiers;
- attachment and clause-reference mentions with resolved/unresolved/ambiguous states;
- conservative table-candidate representation only when source delimiters support it;
- extraction provenance and warnings rather than invented certainty;
- `runtime/jobs/<job-id>/contract.json` persistence with source fingerprint;
- idempotent structure generation for unchanged evidence;
- explicit refusal to structure incomplete OCR pages;
- local POST/GET structure APIs;
- minimal UI title/count/party/fact/clause-outline inspection;
- regression coverage for hierarchy, cross-page continuation, mixed native/OCR evidence, facts, references, malformed inputs and idempotence;
- backend tests and frontend production build green in GitHub Actions.

Known limitations intentionally carried forward:

- Stage 4 is deterministic and conservative; it does not use an LLM to recover ambiguous structure;
- entity-name equivalence is not decided yet;
- Chinese uppercase monetary text is not yet used for arithmetic comparison;
- table reconstruction remains candidate-only unless evidence is sufficiently explicit;
- structure correctness still requires later expert benchmark validation.

Key risk addressed: downstream rule/RAG/LLM components now have one evidence-grounded representation instead of inventing incompatible contract interpretations.

## Stage 5 — Deterministic audit rules

Status: active.

Goal: detect explainable hard inconsistencies before LLM analysis.

Initial rule families:

- payment-percentage totals;
- amount arithmetic and explicit numeric conflicts;
- uppercase/lowercase amount consistency where reliably parseable;
- party-name consistency without silently merging entities;
- contract/document identifier consistency;
- date-order anomalies;
- required-field presence by explicitly selected audit profile;
- duplicate/conflicting values.

Each rule result must include rule ID/version, severity, explanation, canonical evidence/source spans, and explicit pass/fail/not-applicable/review state.

## Stage 6 — Versioned legal knowledge base

Goal: ingest public legal sources with version metadata.

Required metadata:

- authority ID;
- title;
- authority type/level;
- article number;
- article text;
- issuing body;
- publication/effective dates;
- expiry/repeal status where applicable;
- jurisdiction/scope;
- source/version information.

Do not build a vector-only corpus with anonymous chunks.

## Stage 7 — Hybrid legal RAG

Goal: retrieve the right legal authority for a contract issue.

Retrieval channels:

- exact article/citation lookup;
- lexical/BM25 retrieval;
- semantic/vector retrieval;
- candidate fusion/reranking.

Evaluation must include retrieval recall on labeled questions before LLM audit quality is attributed to the model.

## Stage 8 — Primary LLM audit reasoning

Goal: add model-assisted semantic risk analysis grounded in evidence.

Deliverables:

- provider-neutral LLM interface;
- DeepSeek adapter first unless owner changes priority;
- strict structured output schema;
- contract evidence IDs;
- legal evidence IDs;
- explicit insufficient-evidence state;
- timeout/retry/error handling;
- model/version provenance.

The model may not create legal evidence IDs or legal citations not supplied by the knowledge layer.

## Stage 9 — Constrained Agent and secondary review

Goal: allow bounded adaptive orchestration without sacrificing determinism.

Potential Agent actions:

- retry OCR;
- request visual verification;
- retrieve referenced clauses/attachments;
- reformulate retrieval query;
- invoke secondary reviewer for high-risk/low-confidence findings;
- detect reviewer disagreement;
- escalate to human review.

Mandatory pipeline stages remain application-controlled.

## Stage 10 — Professional audit workstation UI

Goal: make findings practical for a legal reviewer.

Target UI:

- document/page viewer;
- risk summary and filters;
- exact contract evidence highlighting;
- legal authority panel;
- source/version display;
- model/rule provenance;
- confidence and uncertainty;
- confirm/reject/needs-review actions;
- processing history and visible failures.

Chat can be added as a secondary interface, not the core product.

## Stage 11 — Benchmark, hardening, and Windows release

Goal: make the system measurable and realistically downloadable.

Benchmark dimensions:

- OCR accuracy, with extra attention to amounts/dates/percentages;
- structure extraction quality;
- legal retrieval recall;
- audit precision;
- audit recall;
- high-risk recall;
- legal-citation accuracy;
- evidence-location accuracy;
- false-positive categories;
- model disagreement rate.

Release progression:

1. reliable documented developer setup;
2. `setup.bat` / `start.bat`;
3. dependency/model-cache handling;
4. downloadable Windows-oriented release bundle;
5. installer only after runtime stability is proven.

## Cross-stage quality gates

Every stage must preserve:

- local-first private-data handling;
- evidence traceability;
- explicit failure states;
- no secrets in Git;
- fictional public fixtures only;
- replaceable providers;
- bounded scope;
- automated regression coverage for newly introduced deterministic behavior.
