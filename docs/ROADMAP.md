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

Status: complete.

Validated deliverables:

- PDF/JPG/PNG document ingestion;
- stable local job IDs;
- page-level native PDF text extraction using pypdf;
- explicit deterministic native-text reliability heuristic;
- `NATIVE_TEXT`, `OCR_REQUIRED`, and `MIXED` document routing;
- image documents routed to future OCR without pretending text was extracted;
- stable page Evidence IDs and page-number linkage;
- local `document.json` and `evidence.json` persistence;
- explicit corrupt-PDF failure;
- PDF page-rendering interface boundary;
- UI page/route summary;
- regression coverage for native, blank, mixed, image, invalid, and corrupt inputs;
- GitHub Actions validation for backend tests and frontend production build.

Key risk addressed: unnecessary OCR can reduce accuracy and destroy already reliable text.

## Stage 3 — OCR and layout evidence layer

Status: complete.

Validated deliverables:

- provider-neutral OCR interface;
- PaddleOCR 3.7.0 local adapter with lazy loading;
- accuracy-first `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec` default;
- optional PaddlePaddle 3.3.0 CPU installation path for Windows;
- pypdfium2/PDFium page renderer with packaging/licensing decision recorded;
- rendering only for PDF pages already classified `OCR_REQUIRED`;
- original image OCR path for JPG/JPEG/PNG;
- stable OCR block evidence IDs;
- page number, text, bbox/polygon, recognition confidence, provider/model/version provenance;
- explicit `OCR_COMPLETE`, `OCR_LOW_CONFIDENCE`, `OCR_NO_TEXT`, and `OCR_FAILED` states;
- mixed native/OCR evidence in correct page order;
- local `ocr.json` and rendered-page persistence under ignored runtime paths;
- UI OCR status and uncertainty summary;
- deterministic regression coverage using synthetic/fake-provider inputs;
- real PDFium rendering exercised by tests;
- opt-in local real-PaddleOCR smoke test;
- GitHub Actions Windows smoke verification of Python 3.11 + PaddlePaddle CPU 3.3.0 + PaddleOCR 3.7.0 installation/runtime imports;
- normal CI green for backend tests and frontend production build.

Known limitations intentionally carried forward:

- normal CI does not download OCR model weights or claim real-model accuracy;
- automatic rotation/unwarping/text-line orientation is disabled until coordinate remapping is designed;
- OCR accuracy thresholds/model choice still require later benchmark validation on legal-document samples;
- table/semantic structure is not reconstructed in Stage 3.

Key risk addressed: scanned/image text is now traceable and uncertain OCR is explicit rather than silently treated as truth.

## Stage 4 — Canonical contract structure

Status: active.

Goal: reconstruct contract concepts without losing evidence links.

Deliverables:

- typed canonical schemas;
- unified source evidence stream from native and OCR pages;
- section/clause hierarchy;
- cross-page clause stitching;
- party mentions/roles;
- dates and amounts as extracted values with evidence links;
- table representation when recoverable from source evidence;
- attachment and cross-reference relationships;
- extraction confidence/uncertainty and explicit unresolved states;
- source evidence IDs on every derived object;
- schema validation and regression tests.

Key risk addressed: downstream rule/RAG/LLM components must consume one evidence-grounded contract representation instead of inventing incompatible interpretations.

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
