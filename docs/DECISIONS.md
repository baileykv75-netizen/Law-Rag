# Architecture Decisions

This file records decisions that future work should not silently reverse. If a decision changes, add a new dated entry explaining why.

## D-001 — Local-first product

**Status:** accepted

Law-Rag is primarily a local Windows-oriented application, not a public SaaS product.

The browser UI communicates with a local backend. Real contracts should remain local by default except for intentionally configured external model API requests.

## D-002 — Browser UI + Python backend

**Status:** accepted

Initial target stack:

- frontend: React + Vite + TypeScript;
- backend: Python + FastAPI.

Rationale:

- browser UI gives a professional workstation interface without committing to a native desktop framework early;
- Python is the practical integration layer for OCR, RAG, data processing, evaluation, and AI tooling;
- the local HTTP boundary keeps frontend and backend concerns clean and supports later packaging.

## D-003 — Evidence-first canonical model

**Status:** accepted

Every important derived contract object must remain traceable to source evidence.

Page number, source location/bounding box when available, extraction method, and confidence should be preserved rather than discarded during text normalization.

## D-004 — Native PDF text before OCR

**Status:** accepted

The system must not blindly OCR every PDF.

A reliable native text layer should be parsed directly. OCR should be used for scanned/image pages or when the native text layer fails a reliability check.

Rationale: unnecessary OCR can introduce avoidable recognition errors.

## D-005 — Deterministic rules before LLM reasoning

**Status:** accepted

Arithmetic, percentage, date, exact/normalized entity consistency, and other deterministic checks should be implemented as ordinary code whenever practical.

LLMs are reserved for semantic/ambiguous reasoning that benefits from language understanding.

## D-006 — Version-aware legal knowledge

**Status:** accepted

Legal RAG must preserve article identity, source, effective dates, status/version, and jurisdiction/scope where available.

Anonymous text chunks without legal identity are insufficient as the sole knowledge representation.

## D-007 — Hybrid retrieval

**Status:** accepted

Legal retrieval will not be vector-only.

Target retrieval combines:

- exact article/citation lookup;
- lexical/BM25 search;
- semantic/vector search;
- fusion/reranking.

## D-008 — Provider-neutral LLM interface

**Status:** accepted

DeepSeek is the planned first primary model integration, but application/domain code must use a provider abstraction.

Kimi, Qwen, local endpoints, or future providers should be swappable without rewriting audit-domain logic.

## D-009 — Constrained Agent

**Status:** accepted

The Agent does not own the mandatory audit pipeline.

Application code controls required stages such as extraction, evidence construction, rule checks, retrieval, validation, and finalization.

The Agent may make bounded choices only through an explicit tool allowlist.

## D-010 — Explicit human-review state

**Status:** accepted

The system must support uncertainty and disagreement.

Results may be marked for human review rather than forcing a binary conclusion when evidence is insufficient or models disagree.

## D-011 — Public repository contains no private contract data

**Status:** accepted

Only fictional test fixtures may be committed by default.

Private benchmark data, reviewer labels, uploads, outputs, logs containing contract text, local indexes, and secrets remain outside Git tracking.

## D-012 — No open-source license yet

**Status:** accepted

No MIT, Apache-2.0, GPL, or other license will be selected until the project owner explicitly decides reuse and redistribution terms.

Repository visibility and open-source licensing are separate decisions.

## D-013 — Packaging comes after runtime stability

**Status:** accepted

Do not begin with a monolithic Windows `.exe`.

Progression:

1. reliable developer setup;
2. stable local startup scripts;
3. dependency/model-cache handling;
4. downloadable Windows-oriented bundle;
5. installer only when runtime behavior is proven.
