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
                14.6 Pipeline + Home integration COMPLETE
                14.7 full regression + packaged Windows smoke NEXT
```

Stage 13 is closed. Do not reopen the audit topology without new evidence. Stage 14 extends the reliable local input/distribution boundary without changing the proven `ISSUE_V1` reasoning chain.

## Production baseline

New jobs use:

```text
Source file
 -> Source Evidence
 -> Canonical Contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> issue-based Legal RAG
 -> one bounded DeepSeek primary request per AuditPlan Issue
 -> one bounded Kimi finding + coverage review per AuditPlan Issue
 -> deterministic Issue comparison
 -> append-only Issue human review
 -> architecture-aware Results / Workspace / Developer
```

Historical completed RC2 jobs remain readable as `LEGACY_RC2`; provenance conflicts fail closed as `CONFLICT`.

## Stage 14 completed work

### 14.1 — Cross-format Evidence architecture — COMPLETE

- Evidence IDs are opaque identities.
- Typed `source_anchor` carries location semantics.
- PDF/image use real page/region anchors; DOCX never fabricates page numbers.
- Unsupported/partial source constructs remain visible.

### 14.2 — DOCX native ingestion — COMPLETE

- modern `.docx` OOXML only; legacy `.doc` is not accepted;
- unsafe/encrypted/macro/pathological packages fail closed;
- paragraphs, Word numbering, tables and embedded-image inventory preserve source identity;
- tracked changes and unsupported meaningful constructs create explicit warnings;
- DOCX enters the same deterministic canonical extraction boundary as PDF/OCR.

### 14.3 — DOCX Evidence + Source Viewer — COMPLETE

- source navigation is source-format aware;
- DOCX Source Viewer resolves exact logical paragraph/table-cell anchors;
- `page_count=0` means no stable source pagination, not malformed evidence;
- source warnings remain visible in Workspace.

### 14.4 — Windows OCR runtime distribution — COMPLETE

Pinned packaged runtime:

```text
CPython 3.12.10
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
```

### 14.5 — Offline OCR model distribution — COMPLETE

Pinned local models:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

The clean Windows build fetches only approved official Paddle archives, verifies archive and inference-file SHA-256 values, and packages fixed local detector/recognizer assets. Production OCR does not silently download or substitute weights.

Authoritative Stage 14.5 Windows run: `32145367670`.
Companion normal CI: `32145367680` — backend `315 passed, 5 skipped, 1 warning`, quality/frontend/Windows OCR dependency smoke PASS.

## 14.6 — Pipeline + Home integration — COMPLETE

Implemented on `stage14-6-pipeline-home-integration`:

- Home accepts PDF, modern DOCX, JPG/JPEG and PNG;
- Home preserves backend `document_kind`, `evidence_count` and source warnings;
- DOCX is shown as structural Source Evidence instead of fake `0 pages` pagination;
- Pipeline loading discriminates persisted source representation explicitly:
  - PDF/image -> historical `PageEvidence[]`;
  - DOCX -> validated `SourceEvidenceArtifact`;
- DOCX evidence identity must match job/document metadata or fail closed as `DOCUMENT_EVIDENCE_INVALID`;
- native DOCX with `ocr_required_pages=0` skips OCR without initializing PaddleOCR;
- PDF/image paginated behavior remains backward compatible;
- source-format differences stop before STRUCTURE/RULES/Audit Planner;
- the Stage 13 Issue V1 stage sequence and Legacy RC2 compatibility remain unchanged;
- `REQUIRE_APPROVAL` still blocks the first actual Planner call after local STRUCTURE + RULES.

### 14.6 validation

Authoritative final head CI: **Law-Rag CI #746 (`32244495929`)**.

```text
backend pytest                      320 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

The 320-test suite includes a persisted DOCX Pipeline regression that uses the real local STRUCTURE + RULES stages and proves `REQUIRE_APPROVAL` stops at `AUDIT_PLAN`, progress `48`, with `PROVIDER_APPROVAL_REQUIRED` before the configured synthetic Planner can execute.

The remaining warning is the existing Starlette TestClient/httpx deprecation warning.

## 14.7 — NEXT: full regression + packaged Windows validation

Stage 14.7 closes Stage 14. It is validation/release hardening only; it must not redesign the audit topology.

Required acceptance:

1. normal backend + public deterministic quality gates + frontend build PASS on final Stage 14 head;
2. clean Windows onedir build from exact base/OCR locks;
3. fixed local OCR model hashes verify with network unavailable;
4. real frozen OCR inference succeeds offline;
5. packaged Home accepts PDF/DOCX/JPG/JPEG/PNG;
6. packaged native DOCX enters the authoritative Pipeline, runs real local STRUCTURE + RULES, and preserves source warnings/provenance;
7. packaged scanned PDF/image OCR still works with the fixed local models;
8. `REQUIRE_APPROVAL` still pauses before the first actual Planner call after local work;
9. `/`, `/results`, `/workspace`, `/developer` load from the final bundle;
10. private runtime data, source contracts, API keys and model caches are absent from release payloads;
11. deterministic portable RC ZIP + manifest + fresh-extraction smoke PASS;
12. final docs close Stage 14 and set Stage 15 as NEXT.

Do not add legal-corpus expansion, expert benchmarking, tray/history, encryption/report export, installer/signing or update infrastructure in Stage 14.7.

## Deferred after Stage 14

```text
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 14.6 is complete. Stage 14.7 is the only next implementation scope.**
