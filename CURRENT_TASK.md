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
                14.4 Windows OCR runtime distribution COMPLETE
                14.5 offline OCR model distribution NEXT
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

`GET /api/documents/{job_id}/evidence/{evidence_id}` is source-format aware:

```text
PDF/image Evidence -> page / bbox / polygon / text offset
DOCX Evidence      -> DOCX_PARAGRAPH / DOCX_TABLE_CELL / DOCX_EMBEDDED_IMAGE anchor
```

For DOCX, `page_number` remains `null`. `GET /api/documents/{job_id}/source/docx` returns a local read-only logical source representation preserving paragraph/table/image order and table row/cell structure.

Workspace Stage 2 discriminates historical PDF/image `PageEvidence[]` from DOCX `SourceEvidenceArtifact`. The Source Viewer uses paginated mode for PDF/image and structural mode for DOCX; Contract Evidence navigation scrolls to and highlights the exact DOCX paragraph/table-cell paragraph.

Authoritative Stage 14.3 code CI run #604 (`32120133931`):

```text
backend pytest                      295 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

Detailed viewer behavior is documented in `docs/DOCX_SOURCE_VIEWER.md`.

## 14.4 — Windows OCR runtime distribution — COMPLETE

Stage 14.4 makes the Paddle OCR **runtime** part of the normal Windows onedir without requiring an end user to install Python, pip, PaddlePaddle or PaddleOCR manually.

### Exact Windows runtime closure

The existing CPython `3.12.10` Windows release baseline is retained. PaddlePaddle `3.3.0` is installed from the official PaddlePaddle CPU wheel index and PaddleOCR `3.7.0` plus its transitive runtime closure are pinned in:

```text
backend/requirements-release-ocr-lock-windows.txt
```

The build sequence is:

```text
fresh release venv
 -> base requirements-release-lock-windows.txt --no-deps
 -> paddlepaddle==3.3.0 official CPU wheel --no-deps
 -> requirements-release-ocr-lock-windows.txt --no-deps
 -> pip check
 -> local Paddle/PaddleOCR import + paddle.utils.run_check()
 -> PyInstaller onedir
```

The base release pins remain authoritative for overlaps such as `pypdfium2==5.12.1` and `Pillow==12.3.0`; OCR packaging does not silently upgrade the validated PDF/image stack.

### Frozen runtime validation

`Law-Rag.exe --diagnose-ocr-runtime` validates the bundled distributions, imports Paddle/PaddleOCR and runs Paddle's local native self-check. It deliberately does **not** construct `PaddleOCR`, select a model or download weights.

The Windows release smoke runs the frozen OCR diagnostic with HTTP/HTTPS/ALL proxies pointed at an unusable local endpoint, proving the runtime import/native check does not require network/model downloads.

PyInstaller explicitly collects Paddle/PaddleOCR/PaddleX Python modules, data, native DLL/PYD files and distribution metadata. The final onedir is checked for:

- exact PaddlePaddle/PaddleOCR/PaddleX pins;
- Paddle native DLL/PYD presence;
- existing `pdfium.dll` presence;
- no Law-Rag root runtime/uploads/jobs/logs/private data;
- no `.paddlex`, `.paddleocr`, `model_cache`, `official_models` or PP-OCR detector/recognizer model directories.

Generic dependency-internal code directories named `runtime` are allowed; the RC scanner no longer confuses PaddleX package code with Law-Rag private runtime data. Private application data remains forbidden at the bundle root, while OCR cache/model identities remain recursively forbidden.

### Release/notices boundary

The release build collects third-party NOTICE/license material across both exact base and OCR locks. `release-metadata.json` fingerprints both locks. PaddlePaddle/PaddleOCR/PaddleX are now classified as bundled runtime components in `release/dependency-inventory.json`.

**PP-OCR model weights are not bundled in Stage 14.4.** Model licensing, fixed model identity, hashes, offline startup and actual OCR inference without downloads are Stage 14.5.

### 14.4 validation

Authoritative Stage 14.4 full Windows CI run #648 (`32125214669`):

```text
backend pytest                               304 passed, 5 skipped, 1 third-party warning
public deterministic quality gates          PASS
frontend production build                   PASS
Windows exact OCR dependency/pip-check       PASS
Windows OCR import/native check offline      PASS
PyInstaller onedir build                     PASS
packaged exact pins/Paddle native/PDFium     PASS
private/cache/model bundle scans             PASS
frozen base diagnostics                      PASS
frozen OCR native diagnostic offline         PASS
packaged HTTP/PDF/privacy smoke               PASS
deterministic RC ZIP + manifest              PASS
final extracted RC user-flow smoke            PASS
Windows onedir + portable RC artifact upload PASS
```

The only warning remains the pre-existing Starlette TestClient/httpx deprecation warning.

## 14.5 — Offline OCR model distribution — NEXT

The next slice owns the model layer, not the Python/native runtime.

Required direction:

- choose/freeze the exact PP-OCR detector + recognizer model identities used by Law-Rag;
- review the exact model redistribution/license boundary before bundling weights;
- define deterministic local model paths and SHA-256/integrity metadata;
- ensure production OCR never silently downloads or switches models;
- validate a packaged OCR inference path with network unavailable;
- make missing/corrupt model assets fail visibly and recoverably;
- keep Stage 13 reasoning topology unchanged;
- do not begin Home/Pipeline rollout or installer work in 14.5.

## Remaining Stage 14 sequence

```text
14.6  unify PDF/image/DOCX paths in Pipeline + Home
14.7  full regression + packaged Windows validation
```

The intended final Windows UX is one self-contained installation experience. Internally Law-Rag remains an onedir-style runtime rather than a giant self-extracting single EXE.

## Deferred after Stage 14

```text
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 14.1–14.4 are complete. Stage 14.5 — offline OCR model distribution — is NEXT.**

Do not start 14.6–14.7 in the same iteration as 14.5.
