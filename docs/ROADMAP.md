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
- OpenAI-compatible HTTP integration with JSON Output, thinking enabled, high reasoning effort and bounded retry/timeout;
- deterministic fake/static providers for normal CI with no external-model credits;
- deterministic bounded legal-topic/context builder over canonical clauses, non-PASS rules and Stage 7 retrieval;
- raw PDF is not independently reread by the model and the whole contract is not dumped by default;
- contract/legal text is marked untrusted data and prompt-injection-like clauses are regression-tested;
- strict JSON/Pydantic output validation;
- invented issue IDs, canonical object IDs, contract Evidence IDs and Legal Evidence IDs are rejected;
- a Legal Evidence ID must belong to the cited issue package;
- `SUPPORTED_FINDING` must cite both contract and legal evidence;
- legal-version applicability is rechecked after model output against `as_of`;
- an intentionally injected stale historical legal version is rejected by regression test;
- corpus/version/OCR uncertainty propagates into evidence-sufficiency/review state;
- `NO_FINDING` cannot become a confident negative conclusion when evidence coverage is incomplete;
- atomic local `runtime/jobs/<job-id>/ai-audit.json` persistence only after validation;
- provider/model failures and invalid responses cannot overwrite a previous valid report;
- DeepSeek `reasoning_content` is not persisted;
- provider configuration health plus POST/GET AI-audit APIs;
- minimal primary-audit UI with explicit external-transmission warning;
- mocked DeepSeek HTTP request-contract regression test;
- opt-in paid/network DeepSeek smoke using synthetic empty context only, skipped by default;
- normal backend CI requires no model key and frontend `build` includes TypeScript `tsc --noEmit`;
- all Stage 1–7 regressions and frontend production build green.

Key boundary: prompt wording is not the trust mechanism. Deterministic post-model evidence/version validation is authoritative. Stage 8 uses one primary model only.

## Stage 9 — Constrained Agent and secondary review

Status: active.

Goal: add bounded adaptive actions and one secondary-review provider without surrendering control of the mandatory audit pipeline.

Planned scope includes:

- explicit secondary-review provider boundary (Kimi/Qwen/local provider may be evaluated; no implicit provider choice);
- selective review triggers for high-risk, low-evidence, source uncertainty, retrieval ambiguity or primary/reviewer disagreement;
- bounded tool allowlist for extra retrieval, referenced clause/attachment lookup, source-evidence inspection and explicit OCR retry requests;
- application-controlled state machine; the Agent may choose among allowed follow-up actions but may not skip mandatory extraction/rule/retrieval/validation stages;
- primary/reviewer disagreement representation and human escalation;
- strict evidence/citation validation applied independently to reviewer output;
- cost/privacy controls so second-model calls are conditional rather than universal;
- deterministic fake-agent/provider tests and opt-in real-provider smoke paths;
- no final professional workstation redesign yet.

## Stage 10 — Professional audit workstation UI

Goal: document/page viewer, exact evidence highlighting, risk filters, legal-authority panel, source/version display, provenance, uncertainty, human confirm/reject/review states, and processing history. Chat remains secondary to the audit workstation.

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
- mandatory pipeline stages remain application-controlled.
