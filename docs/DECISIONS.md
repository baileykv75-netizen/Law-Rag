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

## D-014 — pypdf for Stage 2 native PDF inspection

**Date:** 2026-08-15  
**Status:** accepted

Stage 2 uses `pypdf` behind the document-ingestion layer for PDF page count and native text extraction.

Rationale:

- pure Python and practical on Windows;
- supports page-level PDF text extraction and metadata access;
- BSD-3-Clause licensing is compatible with the project's current goal of preserving future distribution options;
- OCR and page rendering remain separate concerns rather than being coupled to the PDF text library.

The dependency is constrained to major version 6 (`pypdf>=6.14,<7`) so a future breaking major release requires an intentional compatibility review.

## D-015 — pypdfium2/PDFium for OCR page rendering

**Date:** 2026-08-15  
**Status:** accepted

Stage 3 uses `pypdfium2==5.12.1` as the concrete implementation of the PDF page-rendering boundary.

Rationale:

- Windows wheels are available, including x86-64 builds;
- PDFium provides reliable page rasterization without requiring an external Poppler installation;
- `pypdfium2` itself is Apache-2.0/BSD-3-Clause and avoids a strong-copyleft renderer dependency;
- the renderer can target only pages already classified `OCR_REQUIRED`.

The Stage 3 default render scale is `2.0` (approximately 144 DPI for standard PDF points). It is an OCR input-quality setting, not a legal/evidence confidence score.

Distribution note: pypdfium2's upstream documentation states that PDFium and bundled dependency licenses must accompany applicable binary distributions. A future Windows release bundle must therefore preserve the license files shipped with the selected pypdfium2 wheel and must re-check them when the pinned version changes.

## D-016 — PaddleOCR local CPU provider is optional and lazy-loaded

**Date:** 2026-08-15  
**Status:** accepted, model choice superseded by D-017

The first real OCR provider is local PaddleOCR using:

- PaddlePaddle CPU `3.3.0` from the official Windows CPU package index;
- PaddleOCR `3.7.0`;
- initially proposed `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec` for a lightweight CPU path.

PaddlePaddle and PaddleOCR are both released under Apache-2.0. Current official PaddlePaddle Windows pip documentation supports 64-bit Python 3.9–3.13; Law-Rag's existing Python 3.11+ target is therefore retained.

OCR is installed separately with `setup-ocr-cpu.bat` rather than placed in the base requirements. The adapter imports PaddleOCR lazily so a native-text-only PDF workflow does not fail or download models when OCR is not required.

The provider disables automatic document rotation/unwarping/text-line-orientation in the first integration because Stage 3 prioritizes direct pixel-coordinate traceability. Rotation/unwarping may be added later only with explicit coordinate-remapping evidence so transformed OCR coordinates are not falsely presented as original-image coordinates.

PaddleOCR model downloads remain local runtime/cache data and must never be committed to Git.

## D-017 — Accuracy-first default: PP-OCRv6 medium

**Date:** 2026-08-15  
**Status:** accepted

The initial v5-mobile model choice in D-016 is superseded before Stage 3 completion. The default provider now uses:

- `PP-OCRv6_medium_det`;
- `PP-OCRv6_medium_rec`.

Rationale:

- PaddleOCR 3.7 makes PP-OCRv6 medium the default general-OCR model family;
- the medium tier is the accuracy-oriented tier in the current official model lineup;
- Law-Rag's first priority is reliable legal-document evidence rather than minimum CPU latency;
- provider construction accepts explicit detection/recognition model names, so later benchmark data may justify switching to v6 small/tiny or another model without changing OCR-domain code.

This is still a hypothesis to be validated against Law-Rag's private legal-document benchmark. Model selection must ultimately be driven by measured OCR accuracy on amounts, dates, percentages, party names, article numbers, tables, and difficult scans, not by vendor benchmark claims alone.
