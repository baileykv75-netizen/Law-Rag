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
                14.6 Pipeline + Home integration IMPLEMENTATION COMPLETE / HEAD CI CLOSEOUT PENDING
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

## Stage 14 goal

A normal Windows user should be able to use Law-Rag without knowing Python, pip, PaddleOCR or model-download details and reliably submit:

```text
native PDF
scanned PDF
JPG / JPEG / PNG
modern DOCX
```

All supported inputs must converge on the same Evidence -> Canonical Contract -> Issue V1 Pipeline boundary. Source format must not create a second Stage 13 reasoning topology.

## Completed Stage 14 foundations

### 14.1 — Cross-format Evidence architecture — COMPLETE

- Evidence IDs are opaque identities.
- Typed `source_anchor` carries source location.
- PDF/image use real page/region anchors; DOCX never fabricates page numbers.
- Canonical objects retain Evidence IDs and provenance.
- Unsupported/partial source constructs remain visible.

### 14.2 — DOCX native ingestion — COMPLETE

- safe modern OOXML ZIP/XML ingestion;
- malformed/encrypted/macro/unsafe-path/expansion/DTD/entity cases fail closed;
- paragraphs, numbering, tables and embedded-image inventory preserve source identity;
- tracked changes and unsupported meaningful constructs produce explicit warnings;
- DOCX enters the same deterministic canonical extraction boundary as PDF/OCR.

### 14.3 — DOCX Evidence + Source Viewer — COMPLETE

- Evidence lookup is source-format aware;
- DOCX Source Viewer navigates exact logical paragraphs/table cells;
- DOCX `page_count=0` means no stable source pagination, not malformed evidence;
- source warnings remain visible in Workspace.

### 14.4 — Windows OCR runtime distribution — COMPLETE

Pinned packaged path:

```text
CPython 3.12.10
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
```

The frozen runtime includes required Python/native dependencies and passes offline import/native diagnostics.

### 14.5 — Offline OCR model distribution — COMPLETE

Pinned models:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

The clean Windows build fetches approved official Paddle archives, verifies archive and inference-file SHA-256 values, packages only the fixed detector/recognizer path, and production OCR refuses silent runtime download/substitution.

Authoritative Stage 14.5 Windows run: `32145367670`.
Companion normal CI: `32145367680` — backend `315 passed, 5 skipped, 1 warning`, quality/frontend/Windows OCR dependency smoke PASS.

## 14.6 — Pipeline + Home integration — IMPLEMENTATION COMPLETE / HEAD CI CLOSEOUT PENDING

Implemented on `stage14-6-pipeline-home-integration`:

- Home accepts PDF, modern DOCX, JPG/JPEG and PNG;
- Home preserves backend `document_kind`, `evidence_count` and source warnings instead of dropping them;
- DOCX is presented as structural Source Evidence, never as fake `0 pages` pagination;
- Pipeline document loading discriminates persisted source representation explicitly:
  - PDF/image -> historical `PageEvidence[]`;
  - DOCX -> validated `SourceEvidenceArtifact`;
- DOCX evidence identity must match job/document metadata or the Pipeline fails closed with `DOCUMENT_EVIDENCE_INVALID`;
- native DOCX with `ocr_required_pages=0` skips OCR without initializing PaddleOCR;
- PDF/image paginated behavior remains backward compatible;
- source-format differences stop before STRUCTURE/RULES/Audit Planner; the Stage 13 Issue V1 sequence is unchanged;
- `REQUIRE_APPROVAL` still blocks the first actual Planner provider call after local STRUCTURE + RULES.

### 14.6 validation evidence

PR #7 first complete CI run #742 (`32214315999`) passed:

```text
backend pytest                      319 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

A stronger regression was then added at commit `8a80ff4531f1b861fb483c57594aa236a110b467` to run a persisted DOCX job through the real local STRUCTURE + RULES stages and assert it pauses at `AUDIT_PLAN`, progress `48`, with `PROVIDER_APPROVAL_REQUIRED` before the configured synthetic Planner can execute.

GitHub Actions run #744 (`32214430221`) for that strengthened head is currently stuck in `queued` before any backend/frontend job starts. This is a CI-platform queue state, not a test failure. Do **not** record the strengthened head as fully validated until a head CI actually runs.

## 14.7 — NEXT after 14.6 head CI closes

Stage 14.7 is the final Stage 14 combined release validation. It must not change the audit topology.

Required acceptance:

1. normal backend + public deterministic quality gates + frontend build PASS on the final Stage 14 head;
2. clean Windows onedir build from exact base/OCR locks;
3. fixed local OCR models verify by hash with network unavailable;
4. real frozen OCR inference succeeds offline;
5. packaged Home accepts PDF/DOCX/JPG/JPEG/PNG;
6. packaged native DOCX runs through real local STRUCTURE + RULES and preserves source warnings/provenance;
7. packaged scanned PDF/image OCR path still works with the fixed local model set;
8. `REQUIRE_APPROVAL` still stops before the first actual Planner call after local work;
9. `/`, `/results`, `/workspace`, `/developer` all load from the final bundle;
10. private runtime artifacts, API keys, model caches and source contracts are absent from release payloads;
11. deterministic portable RC ZIP + manifest + fresh-extraction smoke PASS;
12. final docs/decisions record Stage 14 closed and Stage 15 next.

Do not add corpus expansion, expert benchmark work, tray/history, encryption/report export, installer/signing or update infrastructure in Stage 14.7.

## Deferred after Stage 14

```text
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Finish 14.6 head CI closeout first. Then Stage 14.7 is the only next implementation scope.**
