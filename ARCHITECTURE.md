# ARCHITECTURE.md

## 1. System objective

Law-Rag is a local-first contract audit assistant. The architecture optimizes for evidence traceability, explicit review coverage, reproducibility, replaceable providers, deterministic validation, visible uncertainty, human review and Windows-friendly distribution.

The browser UI is a local application interface. Real contract files remain local except for explicitly permitted bounded provider calls.

## 2. Runtime topology

```text
Windows user
  |
  v
Local React/Vite UI
  |
  v
Local FastAPI backend
  |
  +-- PDF/image/DOCX ingestion
  +-- bundled PDFium + Paddle OCR runtime + fixed local PP-OCR models
  +-- cross-format Source Evidence
  +-- Canonical Contract
  +-- deterministic audit rules
  +-- Audit Planner / complete canonical-object coverage
  +-- versioned Legal Evidence + issue-based retrieval
  +-- DeepSeek issue-by-issue primary audit
  +-- Kimi issue-by-issue finding + coverage review
  +-- deterministic Issue comparison
  +-- append-only human review
  +-- architecture-aware Results / Workspace / Developer
  +-- local persistence
  |
  +---- explicit bounded outbound calls ----> configured DeepSeek / Kimi APIs
```

Source navigation, Results/Workspace reads, Stage 13 Developer diagnostics, Human Review and local OCR do not implicitly execute external providers.

**Stage 14 is complete.** Home/Pipeline expose PDF, JPG/JPEG, PNG and modern DOCX; the Windows release contains the pinned OCR runtime and verified detector/recognizer assets; the complete packaged Windows onedir/RC flow has passed final combined validation.

## 3. Authoritative job architectures

Runtime architecture states remain:

```text
ISSUE_V1     current production architecture for new jobs
LEGACY_RC2   historical Stage 8/9 contract-level architecture
CONFLICT     fail closed; do not guess which artifact family is authoritative
```

The resolver uses persisted production provenance, not a convenient filename check. Completed historical RC2 jobs remain readable and are not automatically rewritten. Explicit unfinished-RC2 migration preserves the old Pipeline snapshot and leaves Stage 8/9 reports historical.

## 4. Issue V1 production Pipeline

```text
INGEST                    10%
  -> OCR                  25%
  -> STRUCTURE            38%
  -> RULES                48%
  -> AUDIT_PLAN           58%
  -> ISSUE_LEGAL_CONTEXT  68%
  -> ISSUE_PRIMARY_AUDIT  82%
  -> ISSUE_SECONDARY_REVIEW 92%
  -> ISSUE_REVIEW_REPORT  100%
```

The application owns mandatory stage ordering. Neither a model nor the UI may skip evidence/validation stages.

### 4.1 Source-format boundary

```text
PDF/image document.json + PageEvidence[]
DOCX      document.json + SourceEvidenceArtifact
             |
             v
      common DocumentInspection metadata
             |
             v
OCR decision -> STRUCTURE -> RULES -> unchanged Issue V1 chain
```

PDF/image keep their historical paginated evidence representation for compatibility. DOCX is validated as `SourceEvidenceArtifact`; it is never coerced into fake pages. Job identity, source kind, filename and media type must agree or the Pipeline fails closed as `DOCUMENT_EVIDENCE_INVALID`.

Native DOCX reports `ocr_required_pages=0` and skips OCR without constructing PaddleOCR. Native-text PDF keeps the same no-op behavior. Scanned PDF/images continue through the local OCR path.

Planner/RAG/DeepSeek/Kimi/comparison/Human Review remain source-format neutral.

### 4.2 Provider boundary

`REQUIRE_APPROVAL` applies before the Audit Planner's first actual outbound call. Local STRUCTURE + RULES may complete first.

A provider must also be configured. Approval does not manufacture credentials. Planner, DeepSeek and Kimi requests cross persisted approval/cancellation checks independently. A request that has already started cannot be recalled, but cancellation prevents later calls.

Validated Stage 14 behavior:

```text
current_stage     AUDIT_PLAN
progress_percent  48
failure_code      PROVIDER_APPROVAL_REQUIRED
```

before the configured Planner can execute.

Background limits remain bounded:

```text
Pipeline workers                    <= 4
local processing slots              <= 2
OCR slots                           <= 1
concurrent external provider calls  <= 2
```

## 5. Document and Evidence layer

Supported input:

```text
PDF
JPG / JPEG
PNG
modern DOCX
```

Legacy `.doc` is not supported as DOCX.

Reliable native PDF/DOCX text is preferred. OCR is used only where needed. Contract/OCR/DOCX text is untrusted data and never treated as developer/system instruction.

### 5.1 Cross-format Source Evidence

Evidence IDs are opaque identities. Location is represented by typed `source_anchor` values:

```text
PAGE_TEXT
PAGE_REGION
DOCX_PARAGRAPH
DOCX_TABLE_CELL
DOCX_EMBEDDED_IMAGE
```

PDF/image may carry real page/bbox/polygon/text-offset coordinates. DOCX has no stable source pagination and never receives synthetic page numbers.

DOCX `SourceEvidenceArtifact` preserves original source SHA-256/size, ordered structural Evidence and structured warnings. Before canonical structuring, original DOCX size/hash are revalidated; changed/missing source fails closed.

### 5.2 DOCX ingestion safety

DOCX ingestion uses local OOXML ZIP/XML processing and preserves paragraph/table order, Word numbering semantics, table row/cell/paragraph coordinates and embedded-image relationship identity.

Malformed/non-OOXML packages, unsafe archive paths, encrypted entries, macro/VBA payloads, pathological expansion/compression, oversized XML, DTD/entity input and password-protected Office containers fail explicitly.

Tracked changes, unresolved numbering, unsupported text boxes, omitted header/footer/footnote/endnote content or embedded image text create visible source warnings. Blocking warnings prevent a false claim of complete source coverage.

### 5.3 Canonical boundary

`contract.json` is the downstream canonical source of truth. PDF native text, OCR blocks and DOCX structural Evidence converge into the same `EvidenceUnit` stream and deterministic canonical extractor.

Clauses, blocks, parties, dates, amounts, percentages, identifiers and references retain Evidence IDs, typed source spans and extraction provenance.

### 5.4 Source navigation

```text
PDF/image Evidence
 -> real page / bbox / polygon / text offset
 -> rendered source page

DOCX Evidence
 -> typed structural anchor
 -> logical paragraph / table cell / image placeholder
```

`GET /api/documents/{job_id}/source/docx` is local/read-only. The paginated source endpoint refuses DOCX rather than inventing page 1.

Home and Workspace preserve source warnings. Home renders DOCX as structural Evidence counts instead of presenting `page_count=0` as malformed.

## 6. Local OCR distribution

Pinned Windows runtime:

```text
CPython 3.12.10
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
```

Pinned models:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

`release/ocr-models-manifest.json` freezes approved official Paddle archive URLs, license identity, archive SHA-256, packaged directory names, required inference files and per-file SHA-256 values.

Production OCR permits only those model identities, validates the local model file set/hashes before constructing PaddleOCR, and passes explicit local model directories plus Law-Rag's fixed minimal PaddleX configuration. There is no runtime fallback to Hugging Face, BOS, Paddle caches or another model.

The fixed configuration disables document orientation, unwarping and text-line-orientation model branches. The Windows CPU path keeps `enable_mkldnn=False` because packaged regression exposed a PaddlePaddle 3.3.0 oneDNN/PIR failure when that branch was enabled.

PyInstaller preserves PaddleX `ocr-core` distribution metadata and required native DLL/PYD files. PDFium/pypdfium2 provides bounded local rasterization for OCR-required PDFs and source-page rendering.

## 7. Deterministic rules

Machine-checkable conditions remain ordinary code. States:

```text
PASS
FAIL
REVIEW
NOT_APPLICABLE
```

`FAIL` means a configured deterministic condition failed; it is not itself a legal conclusion. Rule results may seed Planner hints but do not define complete review scope.

## 8. Audit Planner and planning coverage

`audit-plan.json` is the authoritative Issue V1 review scope.

```text
baseline checklist
+ deterministic rule/topic hints
+ bounded model planning
= validated AuditPlan
```

Every canonical clause/block receives explicit planning coverage:

```text
REVIEWED_WITH_ISSUE
REVIEWED_NO_SPECIFIC_ISSUE
```

`REVIEWED_NO_SPECIFIC_ISSUE` is planning coverage only, never a legal-safe conclusion. Short contracts use bounded DIRECT planning; long contracts use complete-object CHUNK passes plus bounded GLOBAL synthesis without character-truncating canonical objects merely to fit a prompt.

## 9. Versioned Legal Evidence and Issue Legal RAG

Canonical legal identity:

```text
authority -> authority version -> article / Legal Evidence ID
```

Applicability is deterministic:

```text
effective_date <= as_of < end_date_exclusive
```

Each AuditPlan Issue retrieves independently through exact citation lookup, SQLite FTS5 trigram/BM25, optional local BGE semantic retrieval and weighted reciprocal-rank fusion.

Support states remain explicit:

```text
EVIDENCE_FOUND
EVIDENCE_FOUND_WITH_LIMITATIONS
NO_MATCH_IN_LOCAL_CORPUS
VERSION_REVIEW_REQUIRED
```

Local absence or partial corpus coverage is never converted into a claim that no applicable law exists.

## 10. DeepSeek primary + Kimi secondary review

DeepSeek performs one bounded request per AuditPlan Issue. Kimi performs one bounded independent finding + coverage review per Issue. Both providers may cite only supplied canonical Contract/Legal Evidence identities. Unsupported identities fail validation. Results checkpoint per Issue; unchanged completed checkpoints are reused rather than repeating paid calls.

No extra global Kimi vote/synthesis pass exists without demonstrated evidence of a cross-Issue failure mode.

## 11. Deterministic Issue comparison and Human Review

`issue-review-report.json` compares DeepSeek/Kimi outputs without another model. Only `CONSISTENT` avoids mandatory human review. Two-model agreement is not proof or a correctness probability.

Human Review is append-only and fingerprint-bound to the current authoritative Issue report. Only fresh final `CONFIRMED` or `REJECTED` decisions resolve mandatory review. Stale revisions and incomplete planning coverage cannot silently close a job.

## 12. Results, Workspace and Developer

`/results` and `/workspace` resolve authoritative architecture before choosing artifacts. Workspace exposes Planner scope, Contract Evidence, Legal Evidence, DeepSeek, Kimi, deterministic comparison and Human Review.

`/developer` defaults to GET-only diagnostics over persisted Stage 13 artifacts. Opening diagnostics must not create/re-run stages or call providers. Historical Stage 1–9 execution tools stay visibly isolated under Legacy/RC2.

## 13. Persistence and privacy

Current private Issue V1 artifacts include document/evidence/OCR/canonical/rule/Pipeline/Issue review/human-review JSON under ignored runtime paths.

`evidence.json` is intentionally source-format compatible rather than artificially uniform:

```text
PDF/image -> PageEvidence[]
DOCX      -> SourceEvidenceArtifact
```

Private runtime jobs, source contracts, API keys, downloaded model caches and private benchmark data must not enter the release bundle or public repository.

## 14. Stage 14 validation boundary — COMPLETE

Authoritative normal CI on the validated Stage 14.7 head:

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

Validated artifacts:

```text
law-rag-windows-onedir-stage14-7
law-rag-windows-x64-stage14-7
```

Stage 14 is closed. Its proven source/OCR/distribution boundary should not be redesigned without new evidence.

## 15. Next boundary — Stage 15

Stage 15 owns official legal corpus expansion, update/versioning and retrieval tuning.

It must preserve:

- canonical authority -> version -> article / Legal Evidence identity;
- deterministic applicability and explicit ambiguity/no-applicable states;
- authoritative public-source provenance;
- explicit corpus coverage state;
- the existing Issue V1 reasoning topology;
- the Stage 14 source-format/OCR distribution boundary.

Stage 15 must not absorb Stage 16 expert benchmark/real-provider UAT, Stage 17 tray/history, Stage 18 encryption/report export or Stage 19 installer/signing/update infrastructure.
