# Source Evidence Architecture — Stage 14

## Status

Stage 14.1 froze the cross-format evidence contract. Stage 14.2 now implements safe native DOCX ingestion on top of that contract.

The Source Viewer remains PDF/image-oriented until Stage 14.3. Windows OCR runtime/model distribution remains deferred to Stage 14.4–14.5.

## Core rules

1. **Evidence IDs are opaque identities, not locations.**
   Business logic must never parse page, paragraph, table or cell coordinates from an Evidence ID.
2. **`source_anchor` is the authoritative source location.**
   It is a typed/discriminated object whose shape depends on the source representation.
3. **Do not fabricate pages for non-paginated formats.**
   PDF/image evidence may carry a page number. DOCX native evidence uses structural anchors and `page_number=None`.
4. **Every canonical object must remain traceable to source evidence.**
   Contract clauses, mentions and structured blocks continue to reference Evidence IDs through `SourceSpan`.
5. **Unsupported source content is visible.**
   DOCX constructs that cannot yet be represented with full legal confidence emit structured warnings; legally meaningful gaps block complete source coverage.
6. **Source-format differences stop at the Evidence / Canonical boundary.**
   Audit Planner, Legal RAG, DeepSeek, Kimi, comparison and Human Review consume the canonical contract/evidence identity rather than branching on PDF versus DOCX.

## Source document identity

`SourceDocumentIdentity` records:

- `job_id`;
- original filename;
- media type;
- `DocumentKind`;
- SHA-256 of the original local source bytes;
- source size.

The source hash distinguishes different files with the same display filename. Before DOCX Evidence is converted into `contract.json`, Stage 14.2 re-reads the original local source and verifies both byte size and SHA-256 against the persisted source identity. A changed/missing source fails closed.

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
paragraph_index
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

Cells from one Word table share a deterministic `parent_group_id`. The common canonical extractor converts the group into one `TABLE_CANDIDATE` while retaining individual cell Evidence spans.

### `DOCX_EMBEDDED_IMAGE`

For embedded image occurrences:

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

Stage 14.2 inventories image occurrences and their relationship identity but does not OCR them. Because an image could contain operative contract text, the current conservative behavior marks source coverage partial until a later local OCR path can resolve it.

## Source Evidence schema

Stage 14.2 uses Source Evidence schema `2.1.0`.

`SourceEvidence` contains:

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

`SourceEvidenceArtifact.warnings` contains structured `SourceEvidenceWarning` objects:

```text
code
message
source_locator?
blocks_complete_coverage
```

This lets ingestion distinguish an informational warning from a source gap that must prevent a document from being represented as completely covered.

## DOCX native ingestion

Stage 14.2 accepts modern `.docx` OOXML only. Legacy `.doc` is not accepted as DOCX.

The parser deliberately uses local OOXML/ZIP structures instead of flattening the document through a generic text extractor. It preserves information needed by deterministic legal-document processing:

- paragraph/table source order;
- Word automatic list/numbering semantics;
- paragraph styles that inherit numbering;
- table/row/cell/paragraph structural coordinates;
- table grouping;
- embedded-image relationship inventory;
- tracked-change/unsupported-construct warnings.

The parser does not execute macros and does not fetch external relationships.

### Safe package boundary

DOCX ingestion rejects or limits:

- malformed/non-OOXML ZIP packages;
- unsafe `..`/absolute ZIP entry paths;
- encrypted ZIP entries;
- macro/VBA payloads;
- excessive entry count;
- excessive expanded size;
- suspicious compression ratios;
- oversized XML parts;
- DTD/entity declarations;
- password-protected/encrypted Office compound-file containers.

External relationships are recorded as warnings and are never dereferenced by ingestion.

### Word numbering

Visible automatic numbering is reconstructed from `numbering.xml`, including multilevel `%1`–`%9` templates and paragraph-style inheritance where available. Supported numeric formats include decimal, zero-padded decimal, upper/lower letters, upper/lower Roman and common Chinese counting formats.

If a list paragraph declares numbering that cannot be resolved safely, ingestion does not invent a label. It emits a blocking warning so downstream review cannot present complete coverage on a potentially misidentified clause structure.

### Partial/unsupported constructs

Stage 14.2 explicitly detects high-risk constructs such as:

- tracked changes;
- text boxes;
- headers/footers not yet included as canonical text;
- footnotes/endnotes not yet included;
- comments;
- embedded images requiring later OCR;
- external relationships.

Tracked changes and other content gaps that can alter operative contract text set `blocks_complete_coverage=true`. The persisted DOCX inspection and generated `contract.json` then report `status="partial"` instead of silently claiming completeness.

## Canonical contract boundary

`contract.json` remains schema `1.1.0`; the deterministic extractor provenance is now `stage14-2.0.0`.

PDF native text, OCR blocks and DOCX Source Evidence all converge into the same `EvidenceUnit` stream and then the same deterministic canonical extractor. There is no DOCX-specific Planner or model audit path.

For DOCX:

- `EvidenceUnit.page_number=None`;
- `SourceSpan.page_number=None`;
- typed DOCX anchors survive into canonical `SourceSpan`;
- `Clause.page_start/page_end` remain `None` rather than fabricated;
- grouped table cells become canonical structured-table candidates;
- blocking Source Evidence warnings propagate into canonical extraction warnings and make the canonical contract partial.

For existing PDF/OCR jobs, real page numbers remain available and typed `PAGE_TEXT`/`PAGE_REGION` anchors are added by the common evidence stream.

## Legacy evidence compatibility

Existing PDF/image `evidence.json` files remain the original Stage 2 `PageEvidence[]` representation and are not eagerly rewritten.

`adapt_legacy_paginated_evidence(...)` provides a non-destructive read/adapter boundary:

- native PDF page Evidence keeps its existing Evidence ID and maps to `PAGE_TEXT`;
- OCR block Evidence keeps its existing Evidence ID and maps to `PAGE_REGION`;
- an OCR-required page placeholder without completed OCR text is not promoted into usable text evidence.

New DOCX jobs persist `evidence.json` as a `SourceEvidenceArtifact` object. Loaders must discriminate the authoritative source representation rather than pretending the old list and the new object are the same schema.

## Stage boundaries

Stage 14.3 will make the Source Viewer understand DOCX structural anchors and render a logical paragraph/table source view. It must not pretend DOCX pagination is stable.

Stage 14.4–14.5 will address self-contained Windows PaddleOCR/runtime/model distribution. Stage 14.6 will expose the complete supported-input flow in the product Home/Pipeline. Stage 14.7 will run final packaged Windows regression.
