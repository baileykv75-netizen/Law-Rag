# Law-Rag Development Roadmap

This roadmap is intentionally staged. Each stage must be independently testable before the next one begins.

## Stage 0 — Project foundation

Status: complete.

Validated: product definition, architecture boundaries, contributor/Agent rules, public-repository data policy, configuration/ignore policy, and current-task mechanism.

## Stage 1 — Local application shell

Status: complete.

Validated: React/Vite UI, FastAPI backend, local upload/runtime storage, health endpoint, Windows setup/start scripts, backend tests, frontend build, and CI.

## Stage 2 — Document ingestion and native PDF path

Status: complete.

Validated: PDF/JPG/PNG ingestion, native PDF text extraction, `NATIVE_TEXT` / `OCR_REQUIRED` / `MIXED` routing, stable page Evidence IDs, document/evidence persistence, corrupt-PDF failure, and page-route UI.

## Stage 3 — OCR and layout evidence layer

Status: complete.

Validated: provider-neutral OCR boundary, PaddleOCR 3.7.0 local CPU adapter, PP-OCRv6 medium default, pypdfium2/PDFium rendering only for OCR-required pages, OCR block coordinates/confidence/provenance, explicit low-confidence/no-text/failure states, Windows dependency smoke verification, and regression coverage.

## Stage 4 — Canonical contract structure

Status: complete.

Validated:

- canonical schema `1.0.0`;
- unified native/OCR evidence stream;
- reusable source spans with native offsets or OCR coordinates/confidence;
- Chinese/Arabic clause hierarchy and cross-page continuation;
- party/date/money/percentage/identifier mentions;
- attachment/clause references;
- conservative unresolved/table-candidate states;
- `contract.json` persistence and source fingerprint;
- incomplete OCR refusal;
- POST/GET structure APIs;
- minimal structure UI;
- deterministic/idempotent tests and CI.

Key boundary: downstream rules, RAG, LLMs and Agents consume the canonical contract instead of independently reinterpreting raw PDFs.

## Stage 5 — Deterministic audit rules

Status: complete.

Validated:

- versioned rule-result schema and explicit rule registry;
- `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE`, plus preserved `deterministic_state`;
- explicit audit profile `basic-bilateral-v1` rather than universal required-field assumptions;
- conservative payment-percentage grouping that does not sum unrelated percentages;
- repeated explicit labelled amount consistency;
- party-name consistency grouped by the same explicit role without fuzzy merging;
- identifier consistency grouped by the same explicit label;
- repeated labelled date consistency;
- signing/effective chronology review that does not declare retroactive effect legally invalid;
- OCR uncertainty propagation: low/unknown OCR confidence can downgrade a machine PASS/FAIL to `REVIEW`;
- Chinese uppercase RMB detection with an explicit manual-review limitation instead of a weak parser;
- rule exceptions isolated as visible engine errors while unrelated rules continue;
- canonical object IDs, SourceSpans, Evidence IDs and observed values retained in each result;
- `runtime/jobs/<job-id>/audit-rules.json` persistence;
- POST/GET deterministic-audit APIs;
- minimal rule-result UI with state counts and evidence/review warnings;
- deterministic/idempotent persistence tests, API tests, all Stage 1–4 regressions, and frontend production build green in GitHub Actions.

Known limitations intentionally carried forward:

- rule `FAIL` means a configured machine condition failed; it is not a legal conclusion;
- percentage grouping is deliberately conservative and may return not-applicable/review rather than guessing across lines or clauses;
- Chinese uppercase RMB numeric comparison remains deferred until a thoroughly tested parser exists;
- nuanced contractual/legal risk belongs to later legal-retrieval and LLM stages.

## Stage 6 — Versioned legal knowledge base

Status: active.

Goal: build a source-grounded legal-authority layer before any retrieval or LLM legal reasoning.

Target authority classes initially include nationally applicable contract-relevant laws, administrative regulations and judicial interpretations from authoritative public sources.

Required metadata includes:

- stable internal authority/version/article IDs;
- title and authority type/level;
- issuing body;
- promulgation/publication date;
- effective date;
- amendment/repeal/validity status when available;
- jurisdiction/scope;
- article number and exact article text;
- source URL/source identity and retrieval/import provenance;
- relationships between historical versions.

Stage 6 must not build embeddings or RAG yet. The first goal is a trustworthy, version-aware legal corpus with deterministic import/validation.

## Stage 7 — Hybrid legal RAG

Goal: retrieve the right legal authority for a contract issue using exact citation lookup, lexical/BM25 retrieval, semantic/vector retrieval, and fusion/reranking. Retrieval recall must be measured before model audit quality is attributed to the LLM.

## Stage 8 — Primary LLM audit reasoning

Goal: add evidence-grounded semantic risk analysis through a provider-neutral interface, with DeepSeek planned first. Models receive canonical contract evidence and retrieved legal evidence; they may not invent legal Evidence IDs or unsupported authorities.

## Stage 9 — Constrained Agent and secondary review

Goal: permit bounded adaptive actions such as OCR retry, extra retrieval, referenced-clause/attachment lookup, secondary review, disagreement detection and human escalation. Mandatory audit stages remain application-controlled.

## Stage 10 — Professional audit workstation UI

Goal: document/page viewer, exact evidence highlighting, risk filters, legal-authority panel, source/version display, provenance, uncertainty, human confirm/reject/review states, and processing history. Chat remains secondary to the audit workstation.

## Stage 11 — Benchmark, hardening, and Windows release

Goal: measure OCR, structure extraction, retrieval recall, audit precision/recall, high-risk recall, legal-citation accuracy, evidence-location accuracy, false-positive categories and model disagreement before producing a robust Windows-oriented release bundle/installer.

## Cross-stage quality gates

Every stage must preserve:

- local-first private-data handling;
- evidence traceability;
- explicit uncertainty/failure states;
- no secrets or private contracts in Git;
- fictional public fixtures only;
- replaceable providers;
- bounded stage scope;
- automated regression coverage for deterministic behavior;
- no legal conclusion without traceable legal authority once legal reasoning begins.
