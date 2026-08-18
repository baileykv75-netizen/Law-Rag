# Source Evidence Architecture — Stage 14

## Status

Stage 14.1 freezes the cross-format evidence contract before DOCX ingestion is implemented.

This document defines source identity and source-location semantics for PDF, image/OCR and future DOCX inputs. It does **not** mean DOCX upload/parse support is complete.

## Core rules

1. **Evidence IDs are opaque identities, not locations.**
   Business logic must never parse page, paragraph, table or cell coordinates from an Evidence ID.
2. **`source_anchor` is the authoritative source location.**
   It is a typed/discriminated object whose shape depends on the source representation.
3. **Do not fabricate pages for non-paginated formats.**
   PDF/image evidence may carry a page number. DOCX native evidence must use structural anchors and must not invent `page_number=1` or synthetic pagination.
4. **Every canonical object must remain traceable to source evidence.**
   Contract clauses, mentions and structured blocks continue to reference Evidence IDs through `SourceSpan`.
5. **Unsupported source content must be visible.**
   Later DOCX ingestion must report unsupported/partial constructs instead of silently dropping them and presenting complete coverage.
6. **Source-format differences stop at the Evidence / Canonical boundary.**
   Audit Planner, Legal RAG, DeepSeek, Kimi, comparison and Human Review must consume the canonical contract/evidence identity rather than branch on PDF versus DOCX.

## Source document identity

`SourceDocumentIdentity` records:

- `job_id`
- original filename
- media type
- `DocumentKind`
- SHA-256 of the original local source bytes
- source size

The source hash distinguishes two different files with the same display filename and provides a stable input identity for provenance checks.

## Typed source anchors

### `PAGE_TEXT`

For native PDF text:

```text
page_number
char_start? / char_end?
```

Canonical locator example:

```text
page:0012:text
```

### `PAGE_REGION`

For OCR/image evidence:

```text
page_number
bbox?
polygon?
```

Canonical locator example:

```text
page:0012:region
```

### `DOCX_PARAGRAPH`

For native Word paragraphs:

```text
part
a paragraph index
char_start? / char_end?
```

Canonical locator example:

```text
docx:document:paragraph:000037
```

This anchor intentionally has no page number.

### `DOCX_TABLE_CELL`

For text in Word tables:

```text
part
table_index
row_index
cell_index
paragraph_index
char_start? / char_end?
```

Canonical locator example:

```text
docx:document:table:0002:row:0003:cell:0002:paragraph:0001
```

Table-cell Evidence may also carry a `parent_group_id` so downstream deterministic structuring can retain the relationship between cells from the same table.

### `DOCX_EMBEDDED_IMAGE`

Reserved for embedded images that may later be routed through local OCR:

```text
part
image_index
relationship_id?
parent_locator?
```

Canonical locator example:

```text
docx:document:image:0003
```

The anchor exists now so later DOCX-image OCR does not require another evidence-schema redesign.

## `SourceEvidence`

Cross-format evidence contains:

```text
schema_version
evidence_id
order_index
text
source_method
source_anchor
source_locator
confidence?
block_kind
parent_group_id?
```

`source_locator` is a deterministic human/debug representation of the typed anchor. The typed anchor is authoritative; an explicitly supplied locator that disagrees with the anchor is invalid.

## Canonical contract compatibility

`SourceSpan` and `EvidenceUnit` now allow either:

- a real page number for legacy/paginated evidence; or
- a typed `source_anchor` for non-paginated evidence.

`Clause.page_start/page_end` and `UnnumberedBlock.page_start/page_end` are optional so a future DOCX clause does not need fake pagination.

Existing PDF/OCR contracts remain valid because their real page numbers are still accepted. `contract.json` schema version is bumped from `1.0.0` to `1.1.0` for the additive cross-format location capability.

## Legacy evidence compatibility

Existing `evidence.json` files remain the original Stage 2 `PageEvidence[]` representation. Stage 14.1 does **not** rewrite persisted historical jobs.

`adapt_legacy_paginated_evidence(...)` provides a read/adapter boundary:

- native PDF page Evidence keeps its existing Evidence ID and maps to `PAGE_TEXT`;
- OCR block Evidence keeps its existing Evidence ID and maps to `PAGE_REGION`;
- an OCR-required page placeholder without completed OCR text is not promoted into usable text evidence.

This lets old jobs coexist with the Stage 14 cross-format model without an eager migration.

## DOCX requirements reserved for Stage 14.2+

Stage 14.2 must preserve visible numbering and source order when forming DOCX evidence units. It must detect and surface constructs that may change legal meaning, including tracked changes and other unsupported/partial content. It must not silently normalize a visually numbered contract into unnumbered plain text if that would change clause identification.

Stage 14.3 will make the Source Viewer understand DOCX structural anchors and provide a logical document/table view. The viewer must not pretend DOCX pagination is stable.

## Non-goals of Stage 14.1

- accepting `.docx` uploads;
- extracting Word XML/content;
- DOCX Source Viewer rendering;
- bundling PaddleOCR into Windows distribution;
- bundling OCR model weights;
- changing Stage 13 provider or reasoning topology.
