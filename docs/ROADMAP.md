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
- explicit audit profile `basic-bilateral-v1`;
- conservative payment-percentage grouping;
- repeated labelled amount/party/identifier/date consistency checks;
- signing/effective chronology review without claiming retroactive effect is legally invalid;
- OCR uncertainty propagation into final `REVIEW` state;
- Chinese uppercase RMB detection routed to review rather than weak conversion;
- rule exception isolation;
- canonical object IDs, SourceSpans, Evidence IDs and observed values retained;
- `runtime/jobs/<job-id>/audit-rules.json` persistence;
- POST/GET deterministic-audit APIs and minimal UI;
- regressions/CI green.

Key boundary: rule `FAIL` is a configured machine-condition failure, not a legal conclusion.

## Stage 6 — Versioned legal knowledge base

Status: complete.

Validated:

- dedicated legal-domain schema `1.0.0`;
- authority -> version -> article identity in local SQLite;
- authority/version/article constraints and foreign-key integrity;
- exact article text, source SHA-256 and article SHA-256 persistence;
- deterministic Legal Evidence IDs;
- Chinese article segmentation without false inline-reference splitting;
- manifest-driven import and official-source provenance policy;
- source hash/article-count validation and same-version change rejection;
- atomic rebuild and transactional imports;
- historical versions retained/queryable;
- half-open `effective_date <= as_of < end_date_exclusive` resolution;
- explicit `RESOLVED`, `NO_APPLICABLE_VERSION`, `AMBIGUOUS` states;
- Windows legal-seed rebuild command;
- legal inspection APIs and health UI;
- verified public `CURATED_EXCERPT` seed: 2 authorities / 2 versions / 15 articles;
- regressions/CI green.

Known hardening item: a failed multi-record normal-import report may contain an intermediate `IMPORTED` label for a row subsequently rolled back; authoritative SQLite rollback remains correct. Refine report wording before release packaging.

Key boundary: absence from a `CURATED_EXCERPT` corpus is never evidence that no law exists.

## Stage 7 — Hybrid legal RAG

Status: complete.

Validated:

- retrieval schema/engine `1.0.0` / `stage7-1.0.0`;
- explicit `query`, `as_of`, top-K, authority/article/Legal-Evidence hints and channel provenance;
- deterministic exact authority/article lookup before probabilistic ranking;
- normalized Chinese article-reference handling and exact-hit priority;
- exact lookup still works when derivative retrieval index is absent;
- SQLite FTS5 trigram lexical index with `bm25()` ranking;
- lexical index rebuilt only from canonical Stage 6 Legal Evidence;
- canonical legal-source fingerprint and stale-index detection;
- provider-neutral embedding interface;
- deterministic fake embedding provider for CI;
- optional local `BAAI/bge-small-zh-v1.5` semantic provider;
- vector metadata records provider/model/dimension and Legal Evidence identity;
- real Windows semantic stack/model/index/query smoke verified through opt-in GitHub Actions;
- weighted reciprocal-rank fusion with duplicate merge and exact-hit pinning;
- final evidence filtered by Stage 6 `as_of` version applicability;
- explicit `PARTIAL_COVERAGE`, `INSUFFICIENT_CORPUS`, `NO_APPLICABLE_VERSION`, `VERSION_AMBIGUOUS`, and `INDEX_NOT_READY` semantics;
- explicit requested article missing from partial corpus cannot be hidden by nearby BM25/vector candidates;
- retrieval candidates retain per-channel rank/raw score/contribution, fused score, version and coverage metadata;
- `GET /api/legal/retrieval/summary` and `POST /api/legal/retrieve`;
- local Stage 7 retrieval inspection UI;
- Windows `build-retrieval-index.bat`, `setup-rag-semantic-cpu.bat`, and `build-retrieval-index-semantic.bat` flows;
- public 10-case retrieval benchmark over the checked-in seed;
- CI gate `Recall@5 >= 0.90` and `MRR >= 0.80`;
- all Stage 1–6 regressions and frontend production build green.

Key boundary: a retrieval score is not a legal conclusion or calibrated correctness probability. No-hit in a partial corpus remains insufficient evidence, not proof of legal absence.

## Stage 8 — Primary LLM audit reasoning

Status: active.

Goal: add one provider-neutral primary generative audit layer, with DeepSeek planned first after current official API verification.

The model may reason only over a deterministic package containing canonical contract evidence, deterministic rule results, version-aware Stage 7 Legal Evidence, explicit `as_of`, and source/corpus uncertainty.

Stage 8 must add:

- versioned AI-audit schema;
- provider-neutral primary-audit interface;
- real DeepSeek adapter plus deterministic fake provider for normal CI;
- strict structured model output;
- deterministic validation that rejects invented contract/Legal Evidence IDs;
- explicit insufficient-evidence/review states;
- prompt-injection regression cases where contract text remains untrusted data;
- local `ai-audit.json` provenance/persistence;
- minimal primary-audit API/UI;
- optional real-provider smoke using only fictional/public data.

Stage 8 does not add a second reviewer model or Agent orchestration.

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
