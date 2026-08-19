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
                14.5 offline OCR model distribution COMPLETE
                14.6 Pipeline + Home integration NEXT
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

The Windows release smoke runs the frozen OCR diagnostic with HTTP/HTTPS/ALL proxy variables pointed at an unusable local endpoint, proving the runtime import/native check does not require network/model downloads.

PyInstaller explicitly collects Paddle/PaddleOCR/PaddleX Python modules, data, native DLL/PYD files and distribution metadata.

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

## 14.5 — Offline OCR model distribution — COMPLETE

Stage 14.5 closes the model layer on top of the Stage 14.4 runtime. The normal Windows onedir/portable RC now contains the exact local PP-OCR detector and recognizer used by production OCR. Git stores only the manifest/configuration and integrity logic; model payloads are fetched from the approved official Paddle source during the clean release build and are never committed to the repository.

### Fixed model identity and integrity

Approved models:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

`release/ocr-models-manifest.json` freezes:

- official Paddle BOS archive URLs;
- Apache-2.0 model-license identity;
- archive SHA-256 values;
- exact packaged directory names;
- exact required inference files;
- per-file SHA-256 values.

The locked archive SHA-256 values are:

```text
PP-OCRv6_medium_det  144d0621e059566e5086e228829171591c144c2deb07b2dad4962214fbabfcf7
PP-OCRv6_medium_rec  4eecc1c6a4623765042e6fc15446da0da110b7d875b6b72b2d351d2b2dbd4da6
```

The release build downloads only those approved archives, validates archive identity before extraction, rejects unsafe tar paths/links/devices, verifies the exact file set and hashes, and places the verified models under the frozen release asset root. Upstream content drift therefore fails the build rather than silently changing the OCR model.

### Runtime no-download boundary

Production `PaddleOcrProvider`:

- permits only the two pinned PP-OCRv6 medium model identities;
- resolves and SHA-256-verifies the packaged local model directories before importing/constructing PaddleOCR;
- supplies explicit local detector/recognizer directories;
- supplies Law-Rag's fixed minimal `paddlex_config` instead of relying on PaddleX package-relative/default configuration discovery;
- disables document orientation, unwarping and text-line-orientation model branches so no third/fourth model is implicitly requested;
- fails visibly when the model root, model manifest, fixed OCR pipeline config or any approved model file is missing/corrupt/unexpected;
- never falls back to Hugging Face/BOS/Paddle model cache at runtime.

### Frozen Windows compatibility hardening

The real packaged inference regression exposed two frozen/runtime-specific issues and both are now locked by tests/configuration:

1. PaddleX `ocr-core` availability is checked through `importlib.metadata.version(...)`. PyInstaller therefore explicitly preserves distribution metadata for `imagesize`, `opencv-contrib-python`, `pyclipper`, `pypdfium2`, `python-bidi` and `shapely`; the packages were already installed, but without their `.dist-info` PaddleX falsely reported the OCR extra as missing.
2. PaddlePaddle `3.3.0` CPU inference on this PP-OCR path hit a oneDNN/PIR `ArrayAttribute<Double>` regression. Production keeps the pinned static CPU engine but sets `enable_mkldnn=False`, which maps the CPU inference path away from the failing oneDNN branch. This is a tested release compatibility requirement, not an optional performance toggle.

The frozen inference diagnostic also preserves the exception cause chain so future packaging regressions expose the underlying Paddle/PaddleX error instead of only a generic Law-Rag wrapper message.

### 14.5 validation

Authoritative dedicated Windows run: **Stage 14.5 OCR model assets #64 (`32145367670`)**.

```text
clean Windows onedir build + locked official models PASS
verified local model resolution/hash integrity       PASS
frozen model integrity with network unavailable      PASS
frozen real OCR inference with network unavailable   PASS
base packaged workflow smoke                          PASS
deterministic portable RC ZIP + manifest             PASS
fresh extraction of final RC ZIP                      PASS
final extracted RC user-flow smoke                    PASS
model payload not tracked in Git                      PASS
onedir + portable RC artifact upload                  PASS
```

Companion normal CI #727 (`32145367680`):

```text
backend pytest                      315 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

The remaining warning is the existing Starlette TestClient/httpx deprecation warning.

## 14.6 — Pipeline + Home integration — NEXT

The next slice owns product exposure of the input capabilities that are already implemented below the UI/orchestration boundary.

Required direction:

- make Home/intake explicitly accept the supported PDF, JPG/JPEG, PNG and modern DOCX source set;
- ensure native PDF, scanned PDF/image OCR and DOCX all enter the authoritative Pipeline without format-specific Stage 13 branches;
- ensure OCR no-op/native-retained behavior remains correct for native-text PDF and DOCX;
- surface source/OCR partial/failure states clearly instead of silently continuing;
- preserve Provider approval semantics before the first model-provider call;
- keep Legacy RC2 readability and Issue V1 architecture resolution unchanged;
- do not begin Stage 14.7 final release closeout in the same implementation slice.

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

**Stage 14.1–14.5 are complete. Stage 14.6 — Pipeline + Home integration — is NEXT.**

Do not start Stage 14.7 in the same iteration as Stage 14.6.
