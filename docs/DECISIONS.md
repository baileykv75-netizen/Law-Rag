# Architecture Decisions

This file records decisions that future work should not silently reverse. If a decision changes, add a new dated entry explaining why.

## D-001 — Local-first product

**Status:** accepted

Law-Rag is primarily a local Windows-oriented application, not a public SaaS product. The browser UI communicates with a local backend. Real contracts should remain local by default except for intentionally configured external model API requests.

## D-002 — Browser UI + Python backend

**Status:** accepted

Initial target stack:

- frontend: React + Vite + TypeScript;
- backend: Python + FastAPI.

Rationale: browser UI gives a professional workstation without committing to a native desktop framework early; Python is the practical OCR/RAG/data/AI integration layer; a local HTTP boundary supports later packaging.

## D-003 — Evidence-first canonical model

**Status:** accepted

Every important derived contract object must remain traceable to source evidence. Preserve page number, source location/bounding box when available, extraction method, and confidence instead of discarding them during normalization.

## D-004 — Native PDF text before OCR

**Status:** accepted

Do not blindly OCR every PDF. Reliable native text is parsed directly; OCR is reserved for scanned/image pages or pages that fail the native-text reliability check.

## D-005 — Deterministic rules before LLM reasoning

**Status:** accepted

Arithmetic, percentage, date, exact/normalized entity consistency, and other machine-checkable checks should be ordinary code whenever practical. LLMs are reserved for semantic/ambiguous reasoning.

## D-006 — Version-aware legal knowledge

**Status:** accepted

Legal knowledge must preserve article identity, source, effective dates, status/version, jurisdiction/scope and historical-version relationships. Anonymous chunks are insufficient as the sole representation.

## D-007 — Hybrid retrieval

**Status:** accepted

Legal retrieval will not be vector-only. Target retrieval combines exact citation lookup, lexical/BM25 search, semantic/vector search and fusion/reranking.

## D-008 — Provider-neutral LLM interface

**Status:** accepted

DeepSeek is the first primary model integration, but domain code uses a provider abstraction so Kimi, Qwen, local endpoints or future providers can be swapped without rewriting audit logic.

## D-009 — Constrained Agent

**Status:** accepted

The Agent does not own the mandatory audit pipeline. Application code controls required extraction, evidence, rule, retrieval, validation and finalization stages. The Agent may make bounded choices only through an explicit tool allowlist.

## D-010 — Explicit human-review state

**Status:** accepted

Uncertainty and disagreement must remain visible. `REVIEW`/human-review states are preferable to confident unsupported conclusions.

## D-011 — Public repository contains no private contract data

**Status:** accepted

Only fictional public fixtures may be committed by default. Private benchmarks, reviewer labels, uploads, outputs/logs containing contract text, local indexes and secrets remain outside Git.

## D-012 — No open-source license yet

**Status:** accepted

No MIT, Apache-2.0, GPL or other repository license will be selected until the project owner explicitly decides reuse and redistribution terms. Public visibility and open-source licensing are separate decisions.

## D-013 — Packaging comes after runtime stability

**Status:** accepted

Do not begin with a monolithic Windows `.exe`. Progression: reliable developer setup -> stable startup scripts -> dependency/model-cache handling -> downloadable Windows bundle -> installer only after runtime behavior is proven.

## D-014 — pypdf for Stage 2 native PDF inspection

**Date:** 2026-08-15  
**Status:** accepted

Stage 2 uses `pypdf` behind the ingestion layer for PDF page count and native text extraction. Dependency remains constrained to major version 6 (`pypdf>=6.14,<7`).

## D-015 — pypdfium2/PDFium for OCR page rendering

**Date:** 2026-08-15  
**Status:** accepted

Stage 3 uses `pypdfium2==5.12.1` for PDF rasterization, rendering only pages already classified `OCR_REQUIRED`, with default scale `2.0`. Future binary distribution must preserve applicable dependency license files.

## D-016 — PaddleOCR local CPU provider is optional and lazy-loaded

**Date:** 2026-08-15  
**Status:** accepted, model choice superseded by D-017

The real OCR provider is local PaddleOCR using PaddlePaddle CPU `3.3.0` and PaddleOCR `3.7.0`. OCR is installed separately and imported lazily. Model caches remain local and outside Git.

## D-017 — Accuracy-first default: PP-OCRv6 medium

**Date:** 2026-08-15  
**Status:** accepted

Default provider uses `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`. Final model selection remains benchmark-driven on legal-document OCR accuracy.

## D-018 — Canonical contract structure is deterministic and evidence-grounded

**Date:** 2026-08-15  
**Status:** accepted

Stage 4 introduces a versioned canonical contract boundary persisted as `runtime/jobs/<job-id>/contract.json`. Every derived object retains source spans/Evidence IDs; missing OCR pages block complete structure; downstream systems consume the canonical representation rather than independently rereading raw PDFs.

## D-019 — Deterministic rule failure is not a legal conclusion

**Date:** 2026-08-15  
**Status:** accepted

Stage 5 rule states are `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE`. `FAIL` means a configured machine condition failed; it does not mean illegal/invalid/unenforceable. OCR uncertainty may downgrade a machine decision to review while preserving deterministic state.

## D-020 — Canonical legal evidence is authority/version/article identity, not anonymous chunks

**Date:** 2026-08-15  
**Status:** accepted

Stage 6 uses durable identity:

```text
authority -> authority version -> article / Legal Evidence ID
```

Legal Evidence IDs, source/article hashes, source URLs, effective metadata and coverage remain canonical. Retrieval indexes/embeddings are derivative only.

## D-021 — SQLite legal store and half-open effective intervals

**Date:** 2026-08-15  
**Status:** accepted

Stage 6 uses local SQLite. Applicability is:

```text
effective_date <= as_of < end_date_exclusive
```

No match returns `NO_APPLICABLE_VERSION`; overlapping matches return `AMBIGUOUS` rather than choosing by guess.

## D-022 — Legal corpus coverage is first-class evidence

**Date:** 2026-08-15  
**Status:** accepted

Authority versions declare `FULL_TEXT` or `CURATED_EXCERPT`. Absence from a partial corpus can never support a conclusion that a rule does not exist. Retrieval and LLM layers must propagate coverage state.

## D-023 — Real legal seed requires authoritative public source provenance

**Date:** 2026-08-15  
**Status:** accepted

Real checked-in seed records require curated authoritative public sources, expected source hashes/article counts, effective/version metadata and verification notes. Commercial databases/blogs/search snippets/model memory are not sources of record.

## D-024 — Stage 7 Chinese lexical retrieval uses SQLite FTS5 trigram + BM25

**Date:** 2026-08-15  
**Status:** accepted

The lexical channel uses SQLite FTS5 `trigram` tokenization and `bm25()` over canonical Legal Evidence. Exact citation lookup remains a separate deterministic channel.

## D-025 — Semantic retrieval is optional, local and provider-neutral

**Date:** 2026-08-15  
**Status:** accepted

Stage 7 defines a replaceable `EmbeddingProvider`. Initial real local provider is `BAAI/bge-small-zh-v1.5`; exact + BM25 work without it. Provider/model/dimension are recorded and mismatches are rejected.

## D-026 — Retrieval fusion cannot hide explicit evidence absence or version uncertainty

**Date:** 2026-08-15  
**Status:** accepted

Weighted reciprocal-rank fusion is subordinate to evidence-state semantics. Final candidates must be applicable on `as_of`; ambiguity/no-applicable states cannot be hidden; an explicitly requested missing article in `CURATED_EXCERPT` remains `INSUFFICIENT_CORPUS` even if similar candidates exist. Fused score is ranking, not legal correctness probability.

## D-027 — Stage 8 primary model receives a deterministic evidence package, not the raw contract

**Date:** 2026-08-15  
**Status:** accepted

The Stage 8 primary model does not independently reread the raw PDF and does not receive an unconditional whole-contract dump. Application code builds `AuditContextPackage` from canonical clauses, non-PASS deterministic rule context, explicit `as_of`, and Stage 7 Legal Evidence.

The initial issue discovery is deliberately bounded to deterministic topic rules that overlap the verified public legal seed. A generative model may reason about supplied issues; it may not invent a new authoritative legal corpus or silently reinterpret omitted raw pages.

## D-028 — Prompt instructions are defense-in-depth; post-model validation is authoritative

**Date:** 2026-08-15  
**Status:** accepted

Contract/legal text is serialized as untrusted data and the system prompt explicitly forbids following embedded instructions. This does not make prompt wording a trust boundary.

Before persistence, application code independently validates schema, issue IDs, canonical object IDs, contract Evidence IDs, Legal Evidence IDs, issue-to-law membership and legal-version applicability on `as_of`. Unsupported IDs/versions fail closed. `SUPPORTED_FINDING` requires both contract and legal evidence.

A provider response that looks plausible but fails validation must not replace a previously valid `ai-audit.json`.

## D-029 — DeepSeek V4-Pro is the first primary provider; hidden reasoning is not persisted

**Date:** 2026-08-15  
**Status:** accepted

The DeepSeek API contract was re-verified against official documentation on 2026-08-15. Stage 8 defaults to `deepseek-v4-pro` via the provider's OpenAI-compatible HTTP endpoint, with JSON Output, thinking enabled and high reasoning effort. Legacy `deepseek-chat` / `deepseek-reasoner` aliases are not used.

Domain code depends on `PrimaryAuditProvider`, not DeepSeek SDK objects. API keys live only in local environment/private secret management. `reasoning_content` is not persisted or exposed by the Stage 8 provider result; only final structured content, safe usage/request metadata and a raw-response hash are retained.

No automatic fallback to another provider is allowed.

## D-030 — Secondary review is conditional Stage 9 work, not a universal second call

**Date:** 2026-08-15  
**Status:** superseded by D-031

Stage 8 uses exactly one primary generative provider. The initial Stage 9 plan proposed conditional Kimi/Qwen/local secondary review triggered by high risk, insufficient evidence, source uncertainty, version/retrieval ambiguity or disagreement.

This selective-call policy is no longer the active Stage 9 design.

## D-031 — Stage 9 uses one universal secondary-model call per contract

**Date:** 2026-08-15  
**Status:** accepted

Stage 9 prioritizes audit reliability and implementation clarity over token minimization. Every contract that has a valid Stage 8 primary report receives exactly one secondary-model review by default.

The topology is deliberately fixed:

```text
contract
  -> one Stage 8 primary-model call
  -> one Stage 9 secondary-model call
  -> deterministic comparison/validation
```

The secondary call is **contract-level**, not one external call per finding. It receives the bounded validated Stage 8 audit/evidence package and reviews all primary findings together. This avoids a per-finding N-call explosion while guaranteeing two-model coverage for every audited contract.

The second model remains independent: it must validate/cite only supplied canonical contract and Legal Evidence IDs, may disagree with the primary model, and cannot rewrite deterministic Stage 5 results. Two-model agreement is not treated as proof or converted into a fake correctness probability.

Only the later Agent/tool follow-up remains conditional. Bounded tools are invoked after the two fixed model calls when disagreement, missing context, OCR uncertainty or evidence insufficiency requires additional evidence. No automatic third-model voting is introduced.

Both external transmissions must remain explicit to the user, and provider-specific privacy/data-handling terms must be considered before real sensitive contracts are sent.

## D-032 — Kimi K3 is the default Stage 9 secondary provider

**Date:** 2026-08-15  
**Status:** accepted

The secondary provider is Moonshot AI Kimi. The official Kimi model/API documentation was re-verified during Stage 9B. The default model is `kimi-k3`, with the domestic API base `https://api.moonshot.cn/v1` and local secret `MOONSHOT_API_KEY`.

Kimi K3 is used as an independent contract-level reviewer after a validated Stage 8 DeepSeek report. The provider receives only the bounded secondary-review context reconstructed from the same Stage 8 evidence package; it does not reread the raw PDF or receive unrestricted file access.

The initial provider request uses JSON Mode (`response_format={"type":"json_object"}`), `reasoning_effort="max"`, non-streaming output and `max_completion_tokens`. Law-Rag deliberately keeps deterministic Pydantic/evidence/version validation as the authoritative output boundary rather than relying on provider-side formatting alone. Kimi `reasoning_content` is not persisted or exposed in the normalized review result.

The provider remains behind `SecondaryReviewProvider`; no Kimi-specific SDK objects are allowed in domain logic, and there is no hidden fallback to another reviewer. Normal CI uses fake providers plus an intercepted HTTP contract test, while real Kimi calls remain explicit opt-in network/paid tests using synthetic/public data only.

## D-033 — Stage 10 workstation navigation is provider-free and bounded to persisted artifacts

**Date:** 2026-08-15  
**Status:** accepted

The professional workstation is a presentation/review layer over persisted Stage 2–9 artifacts. Opening a job, filtering findings, rendering a page, resolving a Contract Evidence ID, opening Legal Evidence, or reading human-review history must never implicitly execute OCR, legal retrieval, DeepSeek, Kimi or the constrained Agent.

The read-only workspace API validates artifact presence/state without creating phantom job directories. Source viewing accepts only a job ID plus validated 1-based page number; PDF pages use the already-approved local PDFium renderer and ignored viewer cache. Contract Evidence lookup accepts an Evidence ID and resolves it through the job's validated local evidence artifacts. Arbitrary browser-supplied local filesystem paths are not accepted.

Complete-job and partial-job regression tests deliberately fail if workspace loading attempts to resolve either external model provider.

## D-034 — Human review is append-only, fingerprint-bound, and cannot mutate audit evidence/results

**Date:** 2026-08-15  
**Status:** accepted

Stage 10 stores human decisions separately in:

```text
runtime/jobs/<job-id>/human-review.json
```

A human decision is an additional review record, not an edit to the audit result. Each POST appends a revision with target finding/omission ID, state, note, timestamp, server-derived Contract/Legal Evidence snapshot and the SHA-256 fingerprint of the current validated `review-report.json`.

If `review-report.json` later changes, earlier human revisions remain in history and are returned as stale. They are never silently promoted to approval of the changed context.

Human review writes are restricted to `human-review.json`. Regression coverage asserts that `review-report.json`, `contract.json`, `audit-rules.json`, `ai-audit.json`, `secondary-review.json`, `legal.db` and `retrieval.db` remain byte-for-byte unchanged after a human decision. No external provider call is allowed from human-review GET/POST actions.
