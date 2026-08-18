# CURRENT_TASK.md

# Stage 14 — OCR Distribution + DOCX

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A–13G  COMPLETE / ISSUE_V1 production migration validated

Stage 14       IN PROGRESS — OCR distribution + DOCX
                14.1 cross-format Evidence architecture COMPLETE
                14.2 DOCX native ingestion NEXT
                14.3 DOCX Evidence + Source Viewer PENDING
                14.4 Windows OCR runtime distribution PENDING
                14.5 offline OCR model distribution PENDING
                14.6 Pipeline + Home integration PENDING
                14.7 full regression + packaged Windows smoke PENDING
```

Stage 13 is closed. Do not reopen the audit topology without new evidence. Stage 14 must expand the reliable local input/distribution layer without changing the proven `ISSUE_V1` reasoning chain.

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

A normal Windows user should be able to install/use Law-Rag without knowing Python, pip, PaddleOCR or model-download details and reliably submit:

```text
native PDF
scanned PDF
JPG / JPEG / PNG
DOCX
```

All supported inputs must converge on the same Evidence -> Canonical Contract boundary. Stage 13 must not branch on source format.

## 14.1 — Cross-format Evidence architecture — COMPLETE

Stage 14.1 intentionally freezes the evidence contract before implementing DOCX parsing.

### Evidence rules

1. Evidence IDs are opaque identities, not source locations.
2. Typed `source_anchor` is the authoritative location.
3. PDF/image evidence may have real page coordinates; DOCX must never fabricate page numbers.
4. Canonical objects continue to trace back through Evidence IDs.
5. Unsupported/partial source constructs must be visible rather than silently dropped.
6. Source-format differences stop at the Evidence / Canonical layer; Planner/RAG/DeepSeek/Kimi/comparison/Human Review remain format-neutral.

The detailed contract is documented in `docs/SOURCE_EVIDENCE_ARCHITECTURE.md`.

### Implemented schema foundation

`backend/app/evidence_models.py` defines:

```text
SourceDocumentIdentity
SourceEvidenceArtifact
SourceEvidence

PAGE_TEXT
PAGE_REGION
DOCX_PARAGRAPH
DOCX_TABLE_CELL
DOCX_EMBEDDED_IMAGE
```

`SourceEvidence` carries opaque Evidence identity plus typed source location, deterministic debug locator, confidence, block kind and optional grouping.

`adapt_legacy_paginated_evidence(...)` provides a non-destructive adapter for existing Stage 2/3 PDF/OCR artifacts. Historical `evidence.json` files are not rewritten.

### Canonical compatibility

`contract.json` schema is now `1.1.0` / extractor `stage14-1.0.0`.

`SourceSpan` and `EvidenceUnit` accept either:

- a real legacy/paginated `page_number`; or
- a typed `source_anchor` for non-paginated evidence.

`Clause.page_start/page_end` and `UnnumberedBlock.page_start/page_end` are optional, so future DOCX clauses do not require fake pagination.

Current PDF/OCR behavior remains valid and existing page-shaped evidence remains readable.

### 14.1 validation

Authoritative Stage 14.1 CI run #593 (`32115798937`):

```text
backend pytest                      281 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

The only warning is the pre-existing Starlette TestClient/httpx deprecation warning.

The Stage 14.1 regression specifically verifies:

- DOCX paragraph anchors work with `page_number=None`;
- DOCX table-cell structural locations remain explicit;
- a human/debug locator cannot disagree with its typed anchor;
- page-number/anchor conflicts fail validation;
- legacy native PDF Evidence IDs survive adaptation unchanged;
- legacy OCR Evidence IDs, bbox/polygon/confidence survive adaptation into page-region anchors.

No DOCX parser, OCR distribution, installer behavior or Stage 13 model topology was implemented in 14.1.

## 14.2 — DOCX native ingestion — NEXT

The next slice is limited to local `.docx` ingestion and Evidence generation.

Required behavior:

- accept modern `.docx` only; do not pretend legacy `.doc` is supported;
- validate the OPC/ZIP package safely and reject malformed/encrypted/unsupported inputs explicitly;
- preserve source order for paragraphs and tables;
- preserve visible Word numbering/list semantics required by deterministic clause parsing;
- emit `DOCX_PARAGRAPH` and `DOCX_TABLE_CELL` Evidence anchors with stable structural indices;
- preserve table grouping rather than flattening cells into unrelated text;
- detect legally meaningful partial/unsupported constructs, especially tracked changes, instead of silently dropping them;
- inventory embedded images for later local OCR via the reserved `DOCX_EMBEDDED_IMAGE` anchor;
- produce the same EvidenceUnit / Canonical Contract boundary consumed by Stage 13;
- add deterministic fixtures and tests with no real/confidential contracts.

Do not implement the DOCX Source Viewer in 14.2; that is 14.3. Do not start OCR Windows packaging in 14.2.

## Remaining Stage 14 sequence

```text
14.3  DOCX Evidence navigation + logical Source Viewer
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

**Stage 14.1 is complete. Stage 14.2 — DOCX native ingestion — is NEXT.**

Do not start 14.3–14.7 in the same iteration as 14.2.
