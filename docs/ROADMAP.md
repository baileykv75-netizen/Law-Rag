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

Status: complete.

Validated:

- dedicated legal-domain schema `1.0.0`, separate from contract/rule schemas;
- explicit authority classes, version statuses and coverage types;
- authority → version → article identity in local SQLite;
- unique authority/version/article constraints and foreign-key integrity;
- exact article text, source SHA-256 and article SHA-256 persistence;
- deterministic Legal Evidence IDs such as `legal:<authority>:<version>:<article>`;
- line-start Chinese article segmentation without falsely splitting inline article references;
- structural chapter/section context retained for articles;
- manifest-driven deterministic import rather than live scraping at application startup;
- official-source host policy for real seed data, with explicit testing override for fictional fixtures;
- source hash/article-count validation and same-version source-change rejection;
- atomic rebuild through a temporary SQLite database and replacement only after successful validation;
- normal import transaction rollback on critical conflicts;
- historical versions retained and queryable;
- half-open effective interval resolution `effective_date <= as_of < end_date_exclusive`;
- explicit `RESOLVED`, `NO_APPLICABLE_VERSION`, and `AMBIGUOUS` version-resolution states;
- machine-readable import reports and local `runtime/legal/legal.db` storage;
- Windows `rebuild-legal-seed.bat` command;
- legal summary/authority/evidence/version-resolution APIs;
- minimal legal-knowledge health UI;
- small verified contract-relevant seed with coverage explicitly marked `CURATED_EXCERPT`;
- seed contains 8 selected Civil Code contract articles and 7 selected SPC contract-general interpretation articles;
- regression coverage for parsing, inline references, stable IDs, rebuild idempotence, hash changes, duplicate identities, missing metadata, history, overlap ambiguity, rollback, malformed snapshots, curated seed import and APIs;
- all earlier regressions and frontend production build green in GitHub Actions.

Known limitation intentionally recorded before release hardening:

- on a failed multi-record non-rebuild transaction, SQLite rollback is correct, but an intermediate failure report may retain an `IMPORTED` state for a record that was subsequently rolled back. This report-state wording must be refined before release packaging; it does not alter the authoritative database state.

Key boundary: absence from a `CURATED_EXCERPT` seed is never evidence that the law contains no such rule. Coverage metadata must propagate into retrieval.

## Stage 7 — Hybrid legal RAG

Status: active.

Goal: retrieve the right versioned Legal Evidence IDs for a contract issue while preserving `as_of`, source identity, version status and corpus coverage.

Planned retrieval channels:

- exact authority/article/citation lookup;
- lexical/BM25 retrieval;
- semantic/vector retrieval behind a replaceable embedding boundary;
- deterministic candidate fusion/reranking;
- version filtering/resolution before evidence can be returned;
- coverage-aware `INSUFFICIENT_CORPUS` / ambiguity states rather than false negatives.

Retrieval quality must be measured on labeled fictional/curated questions (for example Recall@K) before later LLM audit quality is attributed to the model.

Stage 7 does not add DeepSeek/Kimi/Qwen audit reasoning.

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
- fictional public fixtures only unless public legal data is explicitly verified/curated;
- replaceable providers;
- bounded stage scope;
- automated regression coverage for deterministic behavior;
- no legal conclusion without traceable legal authority once legal reasoning begins.
