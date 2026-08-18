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
                14.3 DOCX Evidence + Source Viewer NEXT
                14.4 Windows OCR runtime distribution PENDING
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

### Evidence rules

1. Evidence IDs are opaque identities, not source locations.
2. Typed `source_anchor` is the authoritative location.
3. PDF/image evidence may have real page coordinates; DOCX never fabricates page numbers.
4. Canonical objects continue to trace back through Evidence IDs.
5. Unsupported/partial source constructs remain visible rather than silently dropped.
6. Source-format differences stop at the Evidence / Canonical layer; Planner/RAG/DeepSeek/Kimi/comparison/Human Review remain format-neutral.

The detailed contract is documented in `docs/SOURCE_EVIDENCE_ARCHITECTURE.md`.

### 14.1 validation

Authoritative Stage 14.1 CI run #593 (`32115798937`):

```text
backend pytest                      281 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

## 14.2 — DOCX native ingestion — COMPLETE

Stage 14.2 adds the local backend ingestion/canonical path for modern `.docx` while deliberately leaving UI/Pipeline rollout and Source Viewer work for later slices.

### Safe local OOXML parsing

`backend/app/docx_ingestion.py` uses Python standard-library ZIP/XML processing rather than flattening the file through a generic Word text extractor. No macro is executed and no external relationship is fetched.

The parser validates/fails closed on:

- malformed or non-OOXML ZIP packages;
- absolute/path-traversal ZIP entries;
- encrypted ZIP entries;
- macro/VBA payloads;
- excessive ZIP entry count, expanded size or compression ratio;
- oversized XML parts;
- DTD/entity declarations;
- password-protected/encrypted Office compound-file containers.

Legacy `.doc` is not accepted as `.docx`.

### Structural DOCX Evidence

New DOCX jobs persist `evidence.json` as Source Evidence schema `2.1.0` rather than the historical page-list representation.

Native Word content preserves:

```text
DOCX_PARAGRAPH
DOCX_TABLE_CELL
DOCX_EMBEDDED_IMAGE
source order
Word automatic numbering
paragraph-style numbering inheritance
table/row/cell/paragraph coordinates
table parent_group_id
```

Visible list/heading prefixes are reconstructed from `numbering.xml`. Unsupported/missing numbering definitions produce blocking warnings rather than invented clause labels.

Embedded images are inventoried for later OCR but are not OCR-processed in 14.2.

### Partial source semantics

The parser exposes legally meaningful unsupported/partial constructs through structured warnings. Tracked changes, text boxes, omitted header/footer/footnote/endnote content and unresolved embedded-image text can block complete source coverage.

When a blocking source warning exists:

```text
document inspection status = partial
contract.json status         = partial
```

The system does not silently present that source as completely covered.

### Common Canonical Contract boundary

`backend/app/canonical_extraction.py` is now the shared deterministic extractor for PDF native text, OCR and DOCX. DOCX does not have a separate clause/entity extraction implementation.

All formats converge:

```text
source-specific evidence
        ↓
EvidenceUnit
        ↓
shared deterministic canonical extraction
        ↓
contract.json
```

DOCX canonical spans retain typed structural anchors and `page_number=None`. `Clause.page_start/page_end` remain `None` rather than receiving synthetic pagination.

Grouped DOCX table cells become a canonical `TABLE_CANDIDATE` while retaining individual Evidence spans.

`contract.json` remains schema `1.1.0`; extractor provenance is `stage14-2.0.0`.

Before DOCX Evidence is converted into `contract.json`, the original local source is re-read and its byte size + SHA-256 are checked against `SourceDocumentIdentity`. A missing/replaced source fails closed.

### 14.2 validation

Authoritative Stage 14.2 CI run #599 (`32117553117`):

```text
backend pytest                      289 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

The only warning remains the pre-existing Starlette TestClient/httpx deprecation warning.

New deterministic fictional fixtures verify:

- backend `.docx` upload with no fake pages;
- paragraph/table source order;
- Word automatic numbering reaching the existing clause parser;
- table grouping and canonical structured blocks;
- typed DOCX SourceSpan anchors surviving into `contract.json`;
- tracked changes produce partial coverage rather than silent normalization;
- embedded-image relationships are inventoried without OCR or network fetch;
- generic ZIPs named `.docx` are rejected and cleaned up;
- VBA-bearing packages are rejected;
- legacy `.doc` is rejected;
- encrypted Office containers are rejected explicitly;
- source SHA-256 mismatch blocks canonical structuring.

Existing PDF/OCR/Stage 13 regressions remain green.

### Intentional 14.2 boundary

The backend can ingest and structure DOCX now, but the product is **not yet claiming full DOCX UX support**:

- `/workspace` Source Viewer does not yet navigate DOCX anchors;
- embedded DOCX images are not OCR-processed yet;
- the Home file picker/Pipeline rollout remains Stage 14.6;
- Windows OCR runtime/model bundling remains Stage 14.4–14.5.

Do not advertise DOCX as a fully completed end-user path until those later slices pass.

## 14.3 — DOCX Evidence navigation + logical Source Viewer — NEXT

The next slice is limited to source navigation and evidence inspection for DOCX.

Required behavior:

- resolve `DOCX_PARAGRAPH` and `DOCX_TABLE_CELL` Evidence IDs from persisted Source Evidence;
- render a local logical DOCX source view without inventing pagination;
- preserve paragraph/table order and table structure in the viewer;
- clicking Contract Evidence from Issue Workspace must select/highlight the exact paragraph/table cell;
- expose source warnings/partial-coverage state visibly;
- keep PDF/image page rendering unchanged;
- Source Viewer reads must remain local/provider-free;
- do not start Windows OCR packaging in 14.3.

## Remaining Stage 14 sequence

```text
14.4  bundle Windows PaddlePaddle/PaddleOCR runtime
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

**Stage 14.1 and 14.2 are complete. Stage 14.3 — DOCX Evidence navigation + logical Source Viewer — is NEXT.**

Do not start 14.4–14.7 in the same iteration as 14.3.
