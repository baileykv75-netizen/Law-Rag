# CURRENT_TASK.md

# Stage 2 — Document Ingestion and Native PDF Path

## Goal

Build the document-ingestion layer that decides whether a document already contains a usable native text layer or should be routed toward the later OCR path.

At the end of this stage, Law-Rag should be able to ingest a supported document, inspect PDF structure when applicable, extract page-level native text when reliable, preserve page-level source evidence, and clearly classify documents/pages that require OCR later.

This stage still does **not** implement PaddleOCR, legal RAG, LLM calls, audit reasoning, or Agent behavior.

## Why this stage comes before OCR

Electronic PDFs often already contain accurate text. Converting every PDF to images and OCRing it would add avoidable recognition errors, especially for contract amounts, dates, percentages, names, and article numbers.

The system therefore needs a reliable routing decision:

```text
PDF with usable native text -> preserve native text evidence
PDF/page without usable native text -> mark OCR_REQUIRED
JPG/JPEG/PNG -> mark OCR_REQUIRED
```

## Dependency rule

Before adding a PDF library, check both technical suitability and license compatibility with the repository's future distribution goals. Do not introduce a copyleft dependency with material redistribution implications without recording the decision in `docs/DECISIONS.md`.

Prefer a small, well-maintained library stack with permissive licensing and Windows support.

## In scope

### 1. Document domain model

Create typed backend schemas/models for at least:

- document/job identifier;
- original filename;
- media type;
- source file path reference (internal only; do not expose arbitrary local paths to the UI);
- document kind (`pdf` / `image`);
- page count when known;
- processing route/status;
- per-page evidence records.

A first page evidence record should preserve at least:

- stable evidence ID;
- page number;
- source method (`native_pdf_text` or later-compatible equivalent);
- extracted text;
- character count;
- reliability/route state;
- source location sufficient to return to that page later.

Do not design clause/legal schemas yet; this is source evidence only.

### 2. PDF native text extraction

For PDFs:

- read page count;
- extract text separately for each page;
- preserve page boundaries;
- normalize only harmless whitespace required for downstream use;
- never silently join pages into one anonymous text blob;
- store extracted evidence under the ignored runtime job directory.

### 3. Native-text reliability heuristic

Implement an explicit, testable heuristic that classifies each PDF page as one of at least:

- `NATIVE_TEXT_USABLE`;
- `OCR_REQUIRED`;
- `EMPTY_OR_UNSUPPORTED` if needed.

The heuristic must be deterministic and documented. It may initially consider signals such as:

- non-whitespace character count;
- proportion of printable/meaningful characters;
- suspicious replacement/control characters;
- whether the page contains enough textual content to be plausibly useful.

Do not claim the heuristic proves OCR accuracy. It only decides routing.

A mixed PDF must be supported: some pages may use native text while other pages are marked for OCR.

### 4. Image routing

For JPG/JPEG/PNG documents:

- preserve the Stage 1 upload;
- identify them as image documents;
- mark them `OCR_REQUIRED` without attempting OCR in this stage.

### 5. Page rendering boundary

Define a page-rendering interface/path for later OCR processing. If the chosen PDF library can safely render pages, a minimal implementation may be added, but Stage 2 must not perform OCR.

Any rendered page artifacts must remain under ignored runtime storage and retain page-number linkage.

### 6. API integration

Extend the current local backend so the UI can obtain document inspection results after ingestion.

A reasonable Stage 2 response includes:

- job/document ID;
- document kind;
- page count;
- overall route summary;
- number of native-text pages;
- number of OCR-required pages;
- page-level status/evidence metadata.

Do not return huge full-document payloads if a separate detail endpoint is cleaner.

### 7. UI integration

Extend the Stage 1 interface only enough to show document-inspection status, for example:

- PDF page count;
- `native text usable` vs `OCR required` summary;
- per-page route counts;
- clear notice that OCR is not implemented yet.

Do not build the final audit workstation or PDF evidence highlighter yet.

### 8. Tests

Add deterministic regression coverage for at least:

- native-text PDF classified correctly;
- image input classified as OCR-required;
- PDF with no usable text classified as OCR-required;
- mixed-page PDF routing if test-fixture generation is practical;
- evidence IDs/page numbers remain stable within persisted job output;
- invalid/corrupt PDF failure is explicit and does not crash the service;
- Stage 1 upload/health tests continue to pass.

Use only synthetic or fully fictional fixtures.

## Out of scope

Do **not** add any of the following in Stage 2:

- PaddleOCR or another OCR engine;
- OCR text recognition;
- layout/table recognition;
- clause parsing/stitching;
- parties/dates/amount semantic extraction;
- legal corpus;
- embeddings/vector database;
- DeepSeek/Kimi/Qwen API calls;
- Agent framework;
- audit rules;
- legal-risk conclusions;
- real contracts or private benchmark data;
- public deployment;
- Windows `.exe` packaging.

If implementation reaches one of these areas, stop and leave it for its later stage.

## Suggested runtime layout

```text
runtime/uploads/<job-id>/source.pdf
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/rendered/<job-id>/page-0001.png   # only if rendering is implemented
```

Exact filenames may evolve, but persistence must remain local, ignored, deterministic, and traceable.

## Acceptance criteria

Stage 2 is complete only when all of the following are true:

1. Stage 1 health/upload behavior remains functional.
2. A valid native-text PDF can be inspected page by page.
3. PDF page count is returned and persisted.
4. Native text is preserved per page with stable evidence IDs.
5. A deterministic reliability heuristic routes pages to native-text use or future OCR.
6. Image uploads are explicitly marked `OCR_REQUIRED` without OCR being run.
7. A scan/image-only PDF is explicitly marked for OCR rather than producing a misleading empty success.
8. Mixed native/OCR-required page routing is represented correctly when applicable.
9. Corrupt PDF handling returns a clear failure state.
10. Runtime-derived evidence stays only in ignored local paths.
11. No API key is required.
12. No OCR/model dependency is introduced.
13. Backend tests pass.
14. Frontend build/typecheck passes.
15. CI remains green.
16. `README.md` documents the verified Stage 2 behavior before the stage is declared complete.

## Completion rule

Do not change this file to Stage 3 until the criteria above are actually verified.

When Stage 2 is complete, the next task should become **Stage 3 — OCR and layout evidence layer**, where PaddleOCR is introduced behind an OCR provider interface rather than embedded directly into unrelated application code.
