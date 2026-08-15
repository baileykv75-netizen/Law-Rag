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

Validated: canonical schema `1.0.0`, unified native/OCR evidence stream, reusable source spans, clause hierarchy/cross-page continuation, party/date/money/percentage/identifier mentions, references, conservative unresolved/table-candidate states, `contract.json`, incomplete-OCR refusal, APIs/UI and deterministic regressions.

Key boundary: downstream rules, RAG, LLMs and Agents consume the canonical contract instead of independently reinterpreting raw PDFs.

## Stage 5 — Deterministic audit rules

Status: complete.

Validated: versioned rule results, explicit audit profile, `PASS`/`FAIL`/`REVIEW`/`NOT_APPLICABLE`, conservative arithmetic/grouping checks, repeated field consistency, chronology review, OCR uncertainty propagation, explicit parser limitations, local `audit-rules.json`, APIs/UI and regressions.

Key boundary: rule `FAIL` is a configured machine-condition failure, not a legal conclusion.

## Stage 6 — Versioned legal knowledge base

Status: complete.

Validated: dedicated legal schema, authority -> version -> article identity in SQLite, deterministic Legal Evidence IDs, hashes/provenance, deterministic Chinese article parsing, manifest import/rebuild, historical versions, explicit `as_of` resolution, legal APIs/UI and verified public `CURATED_EXCERPT` seed with 2 authorities / 2 versions / 15 articles.

Known hardening item: a failed multi-record normal-import report may contain an intermediate `IMPORTED` label for a row subsequently rolled back; authoritative SQLite rollback remains correct. Refine report wording before release packaging.

Key boundary: absence from a `CURATED_EXCERPT` corpus is never evidence that no law exists.

## Stage 7 — Hybrid legal RAG

Status: complete.

Validated:

- deterministic exact citation/article retrieval;
- SQLite FTS5 trigram + `bm25()` lexical retrieval;
- provider-neutral embeddings and optional local `BAAI/bge-small-zh-v1.5`;
- real Windows BGE semantic smoke;
- weighted reciprocal-rank fusion with exact-hit priority;
- legal-source fingerprint/stale index detection;
- `as_of` applicability filtering;
- explicit partial/insufficient/version-ambiguous/index-unavailable states;
- retrieval API/UI;
- public retrieval benchmark and CI gates `Recall@5 >= 0.90`, `MRR >= 0.80`;
- all prior regressions/builds green.

Key boundary: retrieval score is not a legal conclusion. No-hit in a partial corpus remains insufficient evidence.

## Stage 8 — Primary LLM audit reasoning

Status: complete.

Validated:

- dedicated AI-audit/context schemas `1.0.0` and engine `stage8-1.0.0`;
- provider-neutral `PrimaryAuditProvider` boundary;
- DeepSeek V4-Pro adapter re-verified against current official API documentation on 2026-08-15;
- JSON Output, thinking enabled, high reasoning effort and bounded retry/timeout;
- deterministic bounded legal-topic/context builder over canonical clauses, non-PASS rules and Stage 7 retrieval;
- raw PDF is not independently reread by the model;
- contract/legal text is untrusted data and prompt-injection-like clauses are regression-tested;
- strict structured output and evidence/version validation;
- atomic local `ai-audit.json` persistence;
- provider failure cannot overwrite a previous valid report;
- hidden reasoning is not persisted;
- API/UI plus mocked request-contract and opt-in real-provider smoke paths;
- all prior regressions/builds green.

Key boundary: prompt wording is not the trust mechanism. Deterministic post-model evidence/version validation is authoritative.

## Stage 9 — Universal secondary review + constrained Agent

Status: complete.

Validated:

- reliability-first universal dual-call policy: one DeepSeek primary call + one contract-level Kimi secondary call for every completed audited contract;
- no per-finding second-model call explosion;
- provider-neutral `SecondaryReviewProvider` boundary and real Kimi K3 adapter;
- current Moonshot/Kimi API configuration via `MOONSHOT_API_KEY`, `kimi-k3`, JSON mode and max reasoning effort;
- deterministic fake provider for ordinary CI and opt-in real Kimi smoke path;
- reproducible Stage 8 context fingerprint before secondary review;
- Kimi must review every primary finding exactly once;
- independent rejection of invented/stale contract or Legal Evidence IDs;
- validated possible-primary-omission representation;
- deterministic primary/secondary comparison over risk state, severity rank, contract Evidence sets and Legal Evidence sets;
- natural-language reasoning summaries are not used to fabricate an agreement probability;
- comparison states: agreement, minor disagreement, agreement-with-review, more-evidence-required and material disagreement;
- explicit `POSSIBLE_PRIMARY_OMISSION` follow-up path;
- application-owned Agent policy and hard maximum of two follow-up cycles;
- allowlist: contract evidence inspection, clause context, legal evidence inspection, local legal retrieval, canonical reference lookup and explicit OCR retry request;
- arbitrary shell/filesystem commands, unrestricted web research, corpus mutation and open-ended loops are unavailable;
- local contract/legal/retrieval tool execution with provenance and no hidden external transmission;
- OCR retry currently fails explicitly as unavailable after verifying OCR-derived evidence rather than silently reprocessing the document;
- material unresolved disagreement remains `HUMAN_REVIEW_REQUIRED`; local evidence gathering does not automatically make one model win;
- versioned `review-report.json` with primary/secondary metadata, comparison, omission list, action trace and final state;
- explicit API boundary separating the Kimi external call from local comparison/Agent execution;
- minimal Stage 9 UI showing Kimi review, structured comparison, action trace and final human-review state;
- all Stage 1–9 backend regressions and frontend TypeScript/production build green.

Key boundary: two-model agreement is not proof of legal correctness, and Agent evidence gathering is not an automatic third-model arbitration step.

See [`SECONDARY_REVIEW.md`](SECONDARY_REVIEW.md).

## Stage 10 — Professional audit workstation UI

Status: active.

Goal: turn the validated Stage 1–9 pipeline into a professional review workspace: document/page viewer, exact evidence highlighting, risk filters, linked legal-authority panel, source/version display, provenance/uncertainty, human confirm/reject/review actions, processing history and review ergonomics. Chat remains secondary to the audit workstation.

## Stage 11 — Benchmark, hardening, and Windows release

Goal: measure OCR, structure extraction, retrieval recall, audit precision/recall, high-risk recall, legal-citation accuracy, evidence-location accuracy, false-positive categories and model disagreement before producing a robust Windows-oriented release bundle/installer.

## Cross-stage quality gates

Every stage must preserve:

- local-first private-data handling;
- explicit disclosure before external model transmission;
- evidence traceability;
- explicit uncertainty/failure states;
- no secrets or private contracts in Git;
- fictional public fixtures only unless public legal data is explicitly verified/curated;
- replaceable providers;
- bounded stage scope;
- automated regression coverage for deterministic behavior;
- no legal conclusion without traceable legal authority once legal reasoning begins;
- post-model evidence/version validation before persistence;
- mandatory pipeline stages remain application-controlled;
- two-model agreement must not be presented as a correctness probability;
- unresolved material disagreement must remain visible to a human reviewer.
