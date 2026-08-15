# CURRENT_TASK.md

# Stage 3 — OCR and Layout Evidence Layer

## Goal

Add a replaceable OCR layer for pages that Stage 2 has already classified as `OCR_REQUIRED`, while preserving page/evidence traceability and avoiding changes to pages whose native PDF text is already trusted.

At the end of this stage, image documents and OCR-required PDF pages should produce traceable OCR evidence with text, page number, source coordinates when available, confidence information, and explicit failure/low-confidence states.

This stage does **not** implement contract clause semantics, legal RAG, LLM legal reasoning, audit rules, or Agent behavior.

## Core routing rule

Stage 3 must respect Stage 2 decisions:

```text
NATIVE_TEXT_USABLE page
    -> keep native evidence
    -> do not OCR by default

OCR_REQUIRED PDF page
    -> render only that page
    -> OCR it
    -> preserve page linkage

JPG/JPEG/PNG document
    -> OCR source image
```

Do not regress to "convert every PDF page to an image and OCR everything".

## Dependency and licensing rule

Before introducing PaddleOCR/PaddlePaddle or a PDF renderer:

1. verify the current official installation path and supported Python/Windows combinations;
2. verify licenses from primary project sources;
3. record the adopted versions and distribution implications in `docs/DECISIONS.md`;
4. avoid adding an unnecessary GPU dependency for the first CPU-capable local implementation;
5. keep model downloads/caches outside Git.

If a renderer introduces problematic redistribution/licensing constraints, evaluate alternatives instead of silently accepting it.

## In scope

### 1. OCR provider abstraction

Define a provider-neutral OCR interface under the document/OCR tool layer.

The application layer should depend on an interface such as:

- OCR request containing source image/page identity;
- OCR result containing blocks/lines;
- provider/model/version provenance;
- success/partial/failure status.

PaddleOCR should be the first concrete provider unless technical verification reveals a blocker.

Do not import Paddle-specific SDK objects directly into FastAPI endpoint/domain code.

### 2. PDF page rendering implementation

Implement the Stage 2 `PdfPageRenderer` boundary with a concrete renderer suitable for Windows local use.

Requirements:

- render only pages routed to OCR;
- stable 1-based page linkage;
- deterministic output filename such as `page-0001.png`;
- configurable/render-quality setting documented;
- rendered files only under ignored runtime storage;
- clear errors for failed rendering;
- no silent page-number shifts.

Target runtime layout:

```text
runtime/rendered/<job-id>/page-0001.png
```

### 3. OCR evidence schema

Extend source evidence so OCR blocks preserve at least:

- stable evidence/block ID;
- document/job ID linkage;
- page number;
- recognized text;
- bounding box/polygon when provider supplies it;
- recognition confidence when provider supplies it;
- OCR provider/model/version;
- source method (`ocr` or more specific value);
- low-confidence flag/reason;
- source image/render path reference internally only.

Do not discard coordinates after concatenating text.

### 4. OCR processing

For image inputs:

- OCR the original image;
- preserve the original file as source evidence.

For PDF inputs:

- process only `OCR_REQUIRED` pages;
- preserve existing `NATIVE_TEXT_USABLE` page evidence unchanged;
- combine native and OCR evidence in page order without losing provenance.

### 5. Confidence and uncertainty

Do not convert OCR confidence into fake certainty.

Define explicit thresholds/flags for:

- low-confidence OCR blocks;
- pages with no recognized text;
- OCR/provider failures.

Amounts, dates, percentages, article numbers, and identifiers are especially sensitive, but semantic legal validation of those values belongs to later stages.

### 6. API integration

Extend document processing/status so the UI can distinguish:

- native-text page complete;
- OCR page complete;
- OCR low confidence;
- OCR failed;
- processing incomplete.

Failures on one page should remain visible and should not silently turn into a successful empty document.

### 7. UI integration

Only extend the current interface enough to show OCR processing state:

- pages processed n/N;
- native vs OCR source method;
- OCR low-confidence warning count;
- OCR failure count;
- clear statement that legal audit has not started yet.

Do not build the final PDF highlighter/workstation UI yet.

### 8. Regression fixtures/tests

Use synthetic/fictional fixtures only.

Add coverage for at least:

- image OCR returns text evidence;
- scanned PDF page is rendered and OCRed;
- mixed PDF preserves native page while OCRing only required page;
- page number remains correct after rendering/OCR;
- OCR coordinates/confidence survive persistence;
- no-text OCR result is explicit;
- OCR failure is explicit;
- low-confidence block is flagged;
- Stage 2 native-text tests continue passing;
- source/render/OCR artifacts remain under ignored runtime paths.

Provider-heavy tests may use a fake OCR provider for deterministic unit tests, while at least one opt-in/local integration smoke test should verify the real PaddleOCR adapter when dependencies/models are present.

## Out of scope

Do **not** add any of the following in Stage 3:

- clause/section reconstruction;
- party/date/amount semantic extraction;
- deterministic legal/business audit rules;
- legal statutes/corpus ingestion;
- embeddings/vector database;
- DeepSeek/Kimi/Qwen API calls;
- legal risk conclusions;
- Agent framework;
- second-model review;
- real/private contract fixtures;
- public deployment;
- Windows `.exe` packaging.

## Acceptance criteria

Stage 3 is complete only when all of the following are true:

1. Stage 2 native-text routing remains intact.
2. OCR is behind a provider-neutral interface.
3. A real PaddleOCR adapter is implemented or an explicit verified blocker is documented before choosing another provider.
4. A suitable PDF page renderer is selected with its license/packaging decision recorded.
5. Only `OCR_REQUIRED` PDF pages are rendered/OCRed by default.
6. Image files are OCRed without changing their original source file.
7. OCR text remains linked to page number and stable evidence IDs.
8. Coordinates/polygons and confidence are preserved when available.
9. Low-confidence/no-text/failure states are explicit.
10. Mixed native/OCR evidence can coexist in one document in correct page order.
11. Runtime OCR/render artifacts remain ignored and local.
12. No external LLM API key is required.
13. Backend deterministic tests pass.
14. Frontend build/typecheck passes.
15. CI remains green for tests that do not require downloading heavyweight OCR models.
16. README documents verified Stage 3 setup/behavior before completion.

## Completion rule

Do not change this file to Stage 4 until the above criteria are verified.

When Stage 3 is complete, the next task becomes **Stage 4 — Canonical Contract Structure**, where page evidence is reconstructed into clauses, parties, dates, amounts, tables, and attachment relationships without losing source evidence links.
