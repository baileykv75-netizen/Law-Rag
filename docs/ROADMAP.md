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

No OCR or LLM work was added in this stage.

## Stage 2 — Document ingestion and native PDF path

Status: active.

Goal: distinguish files that can be parsed directly from files that require OCR.

Deliverables:

- PDF/JPG/PNG ingestion abstraction;
- stable local document/job IDs;
- native PDF text extraction path;
- PDF page count and metadata;
- reliability heuristic for native text layer;
- page rendering path for scan/image workflows;
- evidence blocks that preserve page/source location.

Key risk addressed: unnecessary OCR can reduce accuracy.

## Stage 3 — OCR and layout evidence layer

Goal: convert scanned/image contracts into traceable evidence.

Deliverables:

- OCR provider interface;
- PaddleOCR adapter;
- text recognition with page/bounding-box metadata;
- confidence preservation;
- layout/table-region support where practical;
- low-confidence flags;
- OCR regression fixtures;
- optional visual-review hook defined but not necessarily connected to a second model yet.

Key risks addressed:

- numeric OCR errors;
- page skew/rotation;
- multi-column/layout order;
- tables;
- seals/signatures as document elements;
- cross-page source traceability.

## Stage 4 — Canonical contract structure

Goal: reconstruct contract concepts without losing evidence links.

Deliverables:

- typed canonical schemas;
- clause/section hierarchy;
- cross-page clause stitching;
- parties;
- dates;
- amounts;
- tables;
- attachment references;
- source evidence IDs on every derived object;
- schema validation tests.

Key risk addressed: downstream components must not each invent a different representation.

## Stage 5 — Deterministic audit rules

Goal: detect explainable hard inconsistencies before LLM analysis.

Initial rule families:

- payment-percentage totals;
- amount arithmetic;
- uppercase/lowercase amount consistency where applicable;
- party-name consistency;
- contract identifier consistency;
- date-order anomalies;
- required-field presence;
- duplicate/conflicting values.

Each rule result must include rule ID, severity, explanation, and evidence IDs.

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
