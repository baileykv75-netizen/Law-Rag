# DOCX Logical Source Viewer — Stage 14.3

## Purpose

Stage 14.3 makes existing Contract Evidence navigation work for native DOCX evidence without pretending that Word's flow layout has stable source pages.

The viewer is local and read-only. It does not call Planner, DeepSeek, Kimi, OCR providers, external relationships, or any remote document service.

## Source modes

Law-Rag now keeps two source-view modes behind the same Evidence navigation action:

```text
PDF / image
  Evidence ID -> page / bbox / polygon / text offset -> rendered source page

DOCX
  Evidence ID -> typed structural anchor -> logical paragraph / table cell / image placeholder
```

The existing paginated PDF/image route remains unchanged. A DOCX request to the page route fails explicitly rather than inventing page 1.

## DOCX logical endpoint

`GET /api/documents/{job_id}/source/docx`

returns:

- original filename;
- `LOGICAL_NO_STABLE_PAGES` pagination semantics;
- complete/partial source-coverage state;
- Stage 14 source warnings;
- body blocks in persisted Evidence order;
- paragraphs with exact `DOCX_PARAGRAPH` Evidence IDs;
- tables grouped by table index and `parent_group_id`, preserving row/cell/paragraph coordinates;
- embedded-image Evidence placeholders reserved for later local OCR.

The endpoint reads only persisted local artifacts.

## Evidence resolution

`GET /api/documents/{job_id}/evidence/{evidence_id}` now resolves both evidence families:

- legacy/current paginated PDF/image Evidence;
- Stage 14 `SourceEvidenceArtifact` DOCX Evidence.

For DOCX, `page_number` remains `null`. `source_anchor` is authoritative and identifies the paragraph, table cell, or embedded image. If a current Canonical Contract span references the Evidence ID, canonical object references and quote information are returned without replacing the source anchor.

## Workspace behavior

Workspace Stage 2 validation is format-aware:

- PDF/image jobs validate the historical `PageEvidence[]` representation;
- DOCX jobs validate `SourceEvidenceArtifact` and surface its source warnings/coverage uncertainty.

A DOCX with zero stable pages is therefore not treated as malformed merely because `page_count == 0`.

In the Issue Workspace, selecting a Contract Evidence ID continues to use the existing cross-pane callback. `SourceViewerPane` determines source mode from `document_kind`, resolves the Evidence, scrolls to the matching logical block, and highlights the exact paragraph or table cell.

## Safety and fidelity rules

1. Never fabricate DOCX page numbers.
2. Never fetch external Word relationships.
3. Never hide source warnings that can block complete coverage.
4. Preserve table structure instead of rendering a flat cell stream.
5. Embedded images remain visible placeholders until a later local OCR stage handles them.
6. Source Viewer GETs must remain provider-free and must not mutate audit artifacts.
7. Existing PDF/image source rendering and Evidence resolution must remain backward compatible.

## Out of scope

Stage 14.3 does not bundle PaddleOCR, distribute OCR model weights, enable DOCX in Home/Pipeline product UX, or change the Stage 13 ISSUE_V1 reasoning topology. Those remain later Stage 14 slices.
