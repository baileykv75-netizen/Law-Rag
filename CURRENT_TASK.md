# CURRENT_TASK.md

# Stage 14 — OCR Distribution + DOCX

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A–13G  COMPLETE / ISSUE_V1 production migration validated

Stage 14       IN PROGRESS — OCR distribution + DOCX
                14.1 cross-format Evidence architecture COMPLETE
                14.2 DOCX native ingestion COMPLETE
                14.3 DOCX Evidence + Source Viewer COMPLETE
                14.4 Windows OCR runtime distribution NEXT
                14.5 offline OCR model distribution PENDING
                14.6 Pipeline + Home integration PENDING
                14.7 full regression + packaged Windows smoke PENDING
```

Stage 13 is closed. Do not reopen the audit topology without new evidence. Stage 14 expands the reliable local input/distribution layer without changing the proven `ISSUE_V1` reasoning chain.

## Stage 13 production baseline

New jobs use:

```text
canonical contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> issue-based Legal RAG
 -> DeepSeek one bounded primary request per AuditPlan Issue
 -> Kimi one bounded finding + coverage review per AuditPlan Issue
 -> deterministic Issue comparison / issue-review-report.json
 -> append-only Issue human review
 -> architecture-aware Results / Workspace / Developer
```

Historical completed RC2 jobs remain readable as `LEGACY_RC2`; provenance conflicts fail closed as `CONFLICT`.

Final Stage 13G validation baseline before Stage 14:

```text
backend pytest                         275 passed, 5 skipped
public deterministic quality gates    PASS
frontend production build             PASS
Windows release-bundle smoke          PASS
Windows PaddleOCR dependency smoke    PASS
Windows real local BGE semantic smoke PASS
```

## Stage 14 goal

A normal Windows user should ultimately be able to install/use Law-Rag without knowing Python, pip, PaddleOCR or model-download details and reliably submit:

```text
native PDF
scanned PDF
JPG / JPEG / PNG
DOCX
```

All supported inputs converge on the same Evidence -> Canonical Contract boundary. Stage 13 must not branch on source format.

## 14.1 — Cross-format Evidence architecture — COMPLETE

Stage 14.1 froze the evidence contract before DOCX parsing.

Core rules:

1. Evidence IDs are opaque identities, not locations.
2. Typed `source_anchor` is the authoritative location.
3. PDF/image evidence may have real page coordinates; DOCX never fabricates page numbers.
4. Canonical objects continue to trace back through Evidence IDs.
5. Unsupported/partial source constructs remain visible rather than silently dropped.
6. Source-format differences stop at the Evidence / Canonical layer; Planner/RAG/DeepSeek/Kimi/comparison/Human Review remain format-neutral.

The detailed contract is documented in `docs/SOURCE_EVIDENCE_ARCHITECTURE.md`.

Authoritative Stage 14.1 CI run #593 (`32115798937`):

```text
backend pytest                      281 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

## 14.2 — DOCX native ingestion — COMPLETE

Stage 14.2 adds the safe local backend ingestion/canonical path for modern `.docx`.

Implemented:

- standard-library OOXML ZIP/XML processing; no generic Word text-flattening dependency;
- malformed/non-OOXML, unsafe paths, encrypted entries, VBA/macros, expansion/compression abuse, oversized XML and DTD/entity fail-closed checks;
- explicit password-protected/encrypted Office rejection;
- modern `.docx` only; legacy `.doc` is not accepted as DOCX;
- `DOCX_PARAGRAPH`, `DOCX_TABLE_CELL` and `DOCX_EMBEDDED_IMAGE` Evidence anchors;
- source-order preservation, Word automatic numbering and paragraph-style numbering inheritance;
- table grouping and canonical `TABLE_CANDIDATE` generation;
- tracked-change/unsupported-content warnings with explicit partial coverage;
- embedded-image inventory without OCR or external fetch;
- common `EvidenceUnit -> canonical_extraction.py -> contract.json` path shared by PDF/OCR/DOCX;
- original DOCX source size + SHA-256 revalidation before canonical structuring.

DOCX canonical spans use typed structural anchors and `page_number=None`; clause page ranges remain `None` rather than synthetic.

Authoritative Stage 14.2 code/integrity CI run #599 (`32117553117`):

```text
backend pytest                      289 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

Final 14.2 documentation head run #601 also passed backend/quality/frontend checks.

## 14.3 — DOCX Evidence navigation + logical Source Viewer — COMPLETE

Stage 14.3 makes the existing Contract Evidence navigation work for structural DOCX evidence without introducing fake pagination.

### Backend source navigation

`GET /api/documents/{job_id}/evidence/{evidence_id}` is now source-format aware:

```text
PDF/image Evidence -> page / bbox / polygon / text offset
DOCX Evidence      -> DOCX_PARAGRAPH / DOCX_TABLE_CELL / DOCX_EMBEDDED_IMAGE anchor
```

For DOCX, `page_number` remains `null`. Canonical references and the current canonical quote can be returned while the persisted typed source anchor remains authoritative.

`GET /api/documents/{job_id}/source/docx` returns a local, read-only logical source representation:

```text
paragraph
 -> table (row -> cell -> paragraph)
 -> paragraph
 -> embedded-image placeholder
```

Blocks preserve persisted Evidence order. Tables preserve their table index, row/cell coordinates and `parent_group_id`. Embedded images remain visible Evidence placeholders; Stage 14.3 does not OCR them.

The historical paginated route remains for PDF/image. Calling `/source/pages/{page}` for a DOCX fails explicitly instead of inventing page 1.

### Workspace integration

Workspace Stage 2 validation now discriminates the persisted source-evidence representation:

- PDF/image jobs validate historical `PageEvidence[]`;
- DOCX jobs validate `SourceEvidenceArtifact`.

Therefore `page_count=0` is valid for DOCX logical source semantics and does not make an otherwise valid DOCX job look corrupt.

The existing Issue Workspace Contract Evidence callback now drives the same `SourceViewerPane` in two modes:

```text
paginated source viewer  — PDF/image
logical structural viewer — DOCX
```

Clicking a DOCX Contract Evidence ID scrolls to and highlights the exact paragraph or table-cell paragraph. Source warnings such as tracked changes remain visible in the viewer, including whether they block complete source coverage.

All Source Viewer reads are local/provider-free and do not mutate audit artifacts.

### 14.3 validation

Authoritative Stage 14.3 code CI run #604 (`32120133931`):

```text
backend pytest                      295 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

The only warning remains the pre-existing Starlette TestClient/httpx deprecation warning.

New Stage 14.3 regression coverage verifies:

- DOCX paragraph Evidence resolves to a typed structural anchor with no fake page;
- DOCX table-cell Evidence resolves exact table/row/cell/paragraph coordinates with no fake page;
- logical DOCX source preserves paragraph/table order and table structure;
- blocking source warnings remain visible and make source coverage incomplete;
- DOCX page rendering endpoint refuses synthetic pagination;
- Workspace accepts structural DOCX Evidence and surfaces source uncertainty;
- unknown DOCX Evidence fails explicitly;
- existing PDF/image source-viewer regressions remain green;
- frontend TypeScript/Vite production build passes for both source-view modes.

Detailed viewer behavior is documented in `docs/DOCX_SOURCE_VIEWER.md`.

### Intentional 14.3 boundary

Stage 14.3 does not claim the complete end-user DOCX/OCR distribution path yet:

- embedded DOCX images are not OCR-processed yet;
- PaddlePaddle/PaddleOCR is not yet bundled into the normal Windows runtime;
- fixed OCR model weights/offline integrity behavior remain Stage 14.5;
- Home/Pipeline product rollout remains Stage 14.6;
- final packaged Windows validation remains Stage 14.7.

## 14.4 — Windows OCR runtime distribution — NEXT

The next slice is limited to making the current local PaddleOCR implementation available inside the normal Windows release runtime without requiring the user to install Python/Paddle dependencies manually.

Required behavior:

- determine and pin the Windows-compatible PaddlePaddle CPU + PaddleOCR dependency set used by the packaged runtime;
- extend the isolated release environment/build so OCR Python/native runtime dependencies are included deliberately rather than relying on a developer machine;
- keep OCR model weights separate from the 14.4 runtime decision unless a minimal runtime asset is strictly required;
- preserve existing OCR provider abstraction and Stage 3 evidence behavior;
- add packaged/runtime import and deterministic no-network dependency checks;
- make missing/broken OCR runtime fail visibly instead of silently falling back;
- do not begin offline model-weight distribution, Home/Pipeline rollout or installer work in 14.4.

## Remaining Stage 14 sequence

```text
14.5  bundle fixed local OCR models + integrity/offline behavior
14.6  unify PDF/image/DOCX paths in Pipeline + Home
14.7  full regression + packaged Windows validation
```

The intended final Windows UX is one self-contained installation experience. Internally Law-Rag should remain an onedir-style runtime rather than a giant self-extracting single EXE.

## Deferred after Stage 14

```text
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 14.1–14.3 are complete. Stage 14.4 — Windows OCR runtime distribution — is NEXT.**

Do not start 14.5–14.7 in the same iteration as 14.4.
