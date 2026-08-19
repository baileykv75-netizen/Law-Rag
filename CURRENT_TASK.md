# CURRENT_TASK.md

# Stage 15 — Official Legal Corpus Expansion + Versioning + Retrieval Tuning

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A–13G  COMPLETE / ISSUE_V1 production migration validated
Stage 14.1–14.7 COMPLETE / OCR distribution + DOCX + packaged Windows validation

Stage 15       NEXT — official legal corpus expansion + update/versioning + retrieval tuning
```

Stage 13 audit topology and Stage 14 source/distribution architecture are closed. Do not reopen them without new evidence. Stage 15 may improve the official legal corpus, version management and retrieval quality, but must not silently change the proven `ISSUE_V1` reasoning topology or the Stage 14 source-format/OCR distribution boundary.

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

## Stage 14 — COMPLETE

Stage 14 delivered and validated:

- cross-format Evidence identities with typed PDF/image/DOCX source anchors;
- safe modern DOCX OOXML ingestion without synthetic page numbers;
- logical DOCX Source Viewer navigation to exact paragraphs/table cells;
- Home/intake support for PDF, DOCX, JPG/JPEG and PNG;
- source warnings preserved through Home/Workspace;
- source-format-aware Pipeline loading for historical `PageEvidence[]` and DOCX `SourceEvidenceArtifact`;
- bundled Windows PaddlePaddle/PaddleOCR/PaddleX runtime;
- fixed local `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec` assets with archive/file SHA-256 verification;
- no runtime OCR model download/fallback;
- real frozen Windows OCR inference with outbound network unavailable;
- native DOCX real local STRUCTURE + RULES execution with `REQUIRE_APPROVAL` still blocking before the first Planner provider call;
- deterministic portable Windows RC ZIP + manifest + fresh-extraction user-flow smoke.

### Stage 14 final validation

Authoritative normal CI on the Stage 14.7 validated head:

```text
Law-Rag CI #755 (32245812433)
backend pytest                      320 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

Authoritative packaged Windows validation:

```text
Stage 14.7 final Windows release validation (32245812422)
clean Windows onedir + exact runtime/models      PASS
frozen OCR model integrity, network unavailable  PASS
packaged PDF/OCR/UI/privacy smoke                 PASS
packaged DOCX Pipeline + image OCR API smoke      PASS
deterministic portable RC ZIP + manifest          PASS
fresh-extracted final RC complete user-flow smoke PASS
model payload absent from Git                     PASS
onedir + RC artifact upload                       PASS
```

Artifacts from the authoritative run:

```text
law-rag-windows-onedir-stage14-7
law-rag-windows-x64-stage14-7
```

The remaining pytest warning is the existing Starlette TestClient/httpx deprecation warning.

## Stage 15 — NEXT

Stage 15 owns **official legal corpus expansion + update/versioning + retrieval tuning**.

Target scope:

1. expand the checked-in/public legal corpus only from authoritative public sources with explicit provenance;
2. preserve canonical authority -> version -> article / Legal Evidence identity;
3. make source updates/version transitions deterministic and reviewable rather than overwriting history;
4. improve coverage metadata so `CURATED_EXCERPT`, full-text and missing/ambiguous states stay explicit;
5. tune lexical/exact/semantic retrieval against an expanded public regression set;
6. preserve applicability semantics and fail-closed behavior for version ambiguity/no applicable version;
7. add deterministic corpus/retrieval regression evidence before claiming quality improvement;
8. keep private contracts, private benchmarks, model caches and secrets out of Git.

Stage 15 must **not** fold in Stage 16 expert benchmark/real-provider UAT, Stage 17 tray/history, Stage 18 encryption/report export or Stage 19 installer/signing/update infrastructure.

## Deferred after Stage 15

```text
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 14 is complete. Stage 15 is the only next implementation scope.**
