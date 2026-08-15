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

DeepSeek is the planned first primary model integration, but domain code must use a provider abstraction so Kimi, Qwen, local endpoints or future providers can be swapped without rewriting audit logic.

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

Stage 2 uses `pypdf` behind the ingestion layer for PDF page count and native text extraction. It is practical on Windows, pure Python, BSD-3-Clause, and keeps text extraction separate from OCR/rendering. Dependency remains constrained to major version 6 (`pypdf>=6.14,<7`).

## D-015 — pypdfium2/PDFium for OCR page rendering

**Date:** 2026-08-15  
**Status:** accepted

Stage 3 uses `pypdfium2==5.12.1` for PDF rasterization, rendering only pages already classified `OCR_REQUIRED`, with default scale `2.0` (roughly 144 DPI). Future binary distribution must preserve the applicable PDFium/dependency license files and re-check them when the pinned version changes.

## D-016 — PaddleOCR local CPU provider is optional and lazy-loaded

**Date:** 2026-08-15  
**Status:** accepted, model choice superseded by D-017

The real OCR provider is local PaddleOCR using PaddlePaddle CPU `3.3.0` and PaddleOCR `3.7.0`. OCR is installed separately via `setup-ocr-cpu.bat` and imported lazily so native-text-only workflows do not require model dependencies. Automatic document rotation/unwarping/text-line-orientation remain disabled until transformed coordinates can be mapped back safely. Model caches remain local and outside Git.

## D-017 — Accuracy-first default: PP-OCRv6 medium

**Date:** 2026-08-15  
**Status:** accepted

The initial lightweight model proposal was superseded before Stage 3 completion. Default provider uses `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`. This remains a hypothesis to validate against the private legal-document benchmark; final model selection must be driven by measured accuracy on amounts, dates, percentages, names, article numbers, tables and difficult scans.

## D-018 — Canonical contract structure is deterministic and evidence-grounded

**Date:** 2026-08-15  
**Status:** accepted

Stage 4 introduces a dedicated versioned canonical contract boundary before audit rules, legal RAG, LLM reasoning or Agent behavior. Schema `1.0.0` is persisted as `runtime/jobs/<job-id>/contract.json`.

Key rules:

- native PDF lines and OCR blocks are consumed through one ordered evidence abstraction;
- every derived object retains reusable SourceSpans and Evidence IDs;
- native character offsets and OCR bbox/polygon/confidence are retained when available;
- canonical structure never silently replaces source evidence;
- missing/failed/no-text OCR pages block complete structure generation;
- ambiguous facts/references remain explicit;
- extraction is deterministic and unchanged evidence produces idempotent output/source fingerprint.

Downstream deterministic rules, legal retrieval and future models consume this canonical representation instead of independently reinterpreting raw PDFs.

## D-019 — Deterministic rule failure is not a legal conclusion

**Date:** 2026-08-15  
**Status:** accepted

Stage 5 introduces a versioned deterministic rule engine with an explicit registry and four visible states: `PASS`, `FAIL`, `REVIEW`, `NOT_APPLICABLE`.

Interpretation is intentionally narrow:

- `FAIL` means a configured machine-checkable condition did not hold; it does **not** mean the contract is illegal, invalid or unenforceable;
- `REVIEW` is used when grouping/inputs are ambiguous, legal intent may justify the observed chronology, a parser limitation exists, or source OCR is uncertain;
- `NOT_APPLICABLE` is preferred over forcing a check when the required explicit context is absent;
- rules only consume `contract.json` and canonical SourceSpans rather than independently rereading raw PDFs;
- rules retain stable rule IDs/versions, observed values, canonical object IDs and source Evidence IDs;
- low/unknown OCR confidence can downgrade an otherwise deterministic PASS/FAIL to `REVIEW` while preserving `deterministic_state`;
- one rule exception is isolated and surfaced; it must not erase unrelated rule results;
- required-field assumptions are attached to an explicit audit profile (`basic-bilateral-v1`) rather than claimed to be universal contract requirements;
- percentage arithmetic groups only conservatively identified payment percentages instead of summing all percentages in the document.

The report is persisted as `runtime/jobs/<job-id>/audit-rules.json`. Nuanced legal conclusions remain out of scope until versioned legal evidence and later grounded reasoning layers exist.

## D-020 — Canonical legal evidence is authority/version/article identity, not anonymous chunks

**Date:** 2026-08-15  
**Status:** accepted

Stage 6 introduces legal schema `1.0.0` with three durable identity layers:

```text
authority -> authority version -> article / Legal Evidence ID
```

Legal Evidence IDs are deterministic (`legal:<authority>:<version>:<article>`). Source snapshot and exact article text receive SHA-256 hashes. Source URLs, issuing body/type, effective metadata, coverage type, schema/importer version and verification notes remain attached to the legal version.

Later retrieval/indexes/embeddings are derivative indexes only. They may not replace the canonical legal evidence record or invent a citation absent from it.

## D-021 — SQLite legal store and half-open effective intervals

**Date:** 2026-08-15  
**Status:** accepted

Stage 6 uses local SQLite at `runtime/legal/legal.db`; no database server is required. Historical versions are retained. Applicability uses the deterministic half-open interval:

```text
effective_date <= as_of < end_date_exclusive
```

When no interval matches, resolver returns `NO_APPLICABLE_VERSION`. When multiple intervals overlap, it returns `AMBIGUOUS` rather than selecting the latest/promulgated record by guess.

Rebuilds are constructed in a temporary SQLite file and replace the valid store only after full validation succeeds. Normal imports are transactional and roll back on critical identity errors.

## D-022 — Legal corpus coverage is first-class evidence

**Date:** 2026-08-15  
**Status:** accepted

A stored authority version declares `FULL_TEXT` or `CURATED_EXCERPT`. Stage 6 seed is intentionally partial: 8 selected Civil Code contract articles and 7 selected SPC contract-general interpretation articles.

Absence from a `CURATED_EXCERPT` corpus can never support a conclusion that a legal rule does not exist. Stage 7 retrieval and later LLM prompts must propagate this coverage state and use an insufficient-corpus/review result when completeness matters.

## D-023 — Real legal seed requires authoritative public source provenance

**Date:** 2026-08-15  
**Status:** accepted

Real checked-in seed records require curated authoritative public sources, expected source hashes, expected article counts, effective/version metadata and an explicit verification date/note. Stage 6 seed uses official National Laws and Regulations Database / official government publication sources for the Civil Code and official Supreme People's Court sources for the contract-general judicial interpretation.

Commercial legal databases, blogs, search snippets, copied law sites and model memory are not sources of record. Tests may use fictional source hosts only through an explicit test override.
