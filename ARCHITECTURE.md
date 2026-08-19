# ARCHITECTURE.md

## 1. System objective

Law-Rag is a local-first contract audit assistant. The architecture optimizes for evidence traceability, explicit review coverage, reproducibility, replaceable model providers, deterministic validation, visible uncertainty, human review and Windows-friendly distribution.

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
  +-- ingestion / native PDF + safe DOCX OOXML inspection
  +-- bundled PaddlePaddle/PaddleOCR runtime + fixed local PP-OCR models + PDFium rendering
  +-- cross-format Source Evidence + canonical contract
  +-- deterministic audit rules
  +-- Audit Planner / complete canonical-object coverage
  +-- versioned Legal Evidence + issue-based hybrid retrieval
  +-- DeepSeek issue-by-issue primary audit
  +-- Kimi issue-by-issue finding + coverage review
  +-- deterministic Issue comparison
  +-- append-only human review
  +-- architecture-aware Results / Workspace / Developer
  +-- local persistence
  |
  +---- explicit bounded outbound calls ----> configured DeepSeek / Kimi APIs
```

Source navigation, Results reads, Workspace reads, Stage 13 Developer diagnostics, Human Review and local OCR do not implicitly execute external providers.

As of Stage 14.5 the Windows release contains both the pinned OCR Python/native runtime and the exact verified PP-OCR detector/recognizer assets required for local inference. Runtime OCR does not download or substitute model weights.

## 3. Authoritative job architectures

Stage 13G defines three runtime architecture states:

```text
ISSUE_V1     current production architecture for new jobs
LEGACY_RC2   historical Stage 8/9 contract-level architecture
CONFLICT     fail closed; do not guess which artifact family is authoritative
```

The architecture resolver uses persisted production state and provenance rather than merely checking whether a convenient JSON filename exists.

An explicit unfinished-RC2 migration:

1. preserves the old `pipeline.json` as `pipeline-legacy-rc2.json`;
2. records a SHA-256 snapshot reference;
3. initializes the Issue V1 pipeline;
4. leaves old Stage 8/9 reports as historical artifacts.

A missing or modified migration snapshot forces `CONFLICT`.

Completed historical RC2 jobs remain readable and are not automatically rewritten.

## 4. Issue V1 production pipeline

The application-owned production sequence for new jobs is:

```text
INGEST                  10%
  -> OCR                25%
  -> STRUCTURE          38%
  -> RULES              48%
  -> AUDIT_PLAN         58%
  -> ISSUE_LEGAL_CONTEXT 68%
  -> ISSUE_PRIMARY_AUDIT 82%
  -> ISSUE_SECONDARY_REVIEW 92%
  -> ISSUE_REVIEW_REPORT 100%
```

The Pipeline owns mandatory stage ordering. Neither a model nor the UI may skip mandatory evidence/validation stages.

### 4.1 Provider boundary

`REQUIRE_APPROVAL` applies before the Audit Planner's first actual outbound call. Local rules may complete first.

A provider must also be configured. Missing provider configuration may yield `WAITING_CONFIGURATION` before an outbound request is possible; approval does not manufacture credentials.

Planner, DeepSeek and Kimi calls cross the persisted provider/cancellation boundary independently. An already-started request cannot be recalled, but cancellation blocks later requests.

Background limits remain bounded:

```text
Pipeline workers                    <= 4
local processing slots              <= 2
OCR slots                           <= 1
concurrent external provider calls  <= 2
```

The external-provider slot is acquired per actual model call, not for the entire multi-Issue stage. This preserves Stage 13 checkpoint/resume behavior and avoids monopolizing the provider budget while local work runs.

## 5. Document and evidence layer

Backend-supported source input includes:

- PDF;
- JPG/JPEG;
- PNG;
- modern DOCX.

The Home/Pipeline product picker is not considered fully rolled out for the complete source set until Stage 14.6. Legacy `.doc` is not supported as DOCX.

Reliable native PDF/DOCX text is preferred. OCR is used only where needed. DOCX native evidence never receives synthetic page numbers.

Current OCR family:

```text
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

The Windows onedir contains the pinned OCR runtime plus the exact fixed local detector/recognizer assets. `release/ocr-models-manifest.json` freezes approved official Paddle archive URLs, Apache-2.0 model-license identity, archive SHA-256, packaged directory names, required inference files and per-file SHA-256.

Production OCR permits only those two model identities. It verifies the exact local model file set and hashes before constructing PaddleOCR and supplies explicit local model directories plus Law-Rag's fixed minimal PaddleX OCR configuration. There is no runtime fallback to Hugging Face, BOS, Paddle caches or a different model.

The fixed OCR configuration disables document orientation classification, document unwarping and text-line-orientation branches, so the packaged path does not implicitly request additional models. The CPU release also keeps `enable_mkldnn=False` for this pinned PaddlePaddle 3.3.0/PP-OCR path because Windows regression exposed a oneDNN/PIR `ArrayAttribute<Double>` failure when that branch was enabled.

PDFium/pypdfium2 provides bounded local rasterization for OCR-required PDF pages and source-page rendering.

### 5.1 Cross-format Source Evidence

Evidence IDs are opaque identities. Location is represented by typed `source_anchor` values:

```text
PAGE_TEXT
PAGE_REGION
DOCX_PARAGRAPH
DOCX_TABLE_CELL
DOCX_EMBEDDED_IMAGE
```

PDF/image jobs retain their historical `PageEvidence[]` persistence for compatibility. New DOCX jobs persist a `SourceEvidenceArtifact` with original source SHA-256/size, ordered structural Evidence and structured warnings.

DOCX ingestion uses local standard-library OOXML ZIP/XML processing. It preserves paragraph/table order, Word numbering semantics, table/row/cell/paragraph coordinates and embedded-image relationship identity. It does not execute VBA/macros or fetch external relationships.

Malformed/non-OOXML packages, unsafe archive paths, encrypted entries, macro/VBA payloads, pathological archive expansion, oversized XML/DTD/entity input and password-protected Office containers fail explicitly.

Unsupported legally meaningful constructs such as tracked changes, unresolved numbering, text boxes, omitted header/footer/footnote/endnote content or embedded image text produce visible source warnings. Blocking source warnings make source/canonical status partial instead of silently claiming complete coverage.

### 5.2 Canonical boundary

`contract.json` is the downstream canonical contract source of truth. PDF native text, OCR blocks and DOCX structural Evidence converge into the same `EvidenceUnit` stream and the same deterministic canonical extractor.

Clauses, blocks, parties, dates, money, percentages, identifiers and references retain source spans/Evidence IDs and extraction provenance. For DOCX, source spans carry typed structural anchors with `page_number=None`; clause page ranges remain unset rather than fabricated.

Before DOCX Evidence is structured, the original local source size and SHA-256 are revalidated against the persisted source identity. A changed/missing source fails closed.

Contract/OCR/DOCX text is untrusted data. It is never treated as a developer/system instruction.

### 5.3 Source navigation

Source navigation is dual-mode behind the same Contract Evidence action:

```text
PDF / image
  Evidence ID -> real page / bbox / polygon / text offset -> rendered source page

DOCX
  Evidence ID -> typed structural anchor -> logical paragraph / table cell / image placeholder
```

`GET /api/documents/{job_id}/source/docx` is local/read-only. It preserves persisted paragraph/table order and reconstructs table rows/cells from structural Evidence. Source warnings remain visible in the logical viewer.

DOCX has no stable source pagination. The paginated source endpoint refuses DOCX rather than inventing page 1. Embedded-image Evidence is visible as a placeholder until a later local OCR path handles it.

## 6. Deterministic rules

Machine-checkable conditions remain ordinary code.

States:

```text
PASS
FAIL
REVIEW
NOT_APPLICABLE
```

`FAIL` means a configured deterministic condition failed; it is not itself a legal conclusion.

Deterministic rule results may seed Planner hints but do not define the complete legal-review scope.

## 7. Audit Planner and planning coverage

`audit-plan.json` is the authoritative Issue V1 review scope.

It combines:

```text
baseline checklist
+ deterministic rule/topic hints
+ bounded model planning
= validated AuditPlan
```

The model cannot delete mandatory baseline scope and may reference only supplied canonical object identities.

Every canonical clause/block receives one explicit coverage state:

```text
REVIEWED_WITH_ISSUE
REVIEWED_NO_SPECIFIC_ISSUE
```

`REVIEWED_NO_SPECIFIC_ISSUE` is planning coverage, never a safety/legal-validity conclusion.

Short contracts use a bounded DIRECT Planner pass. Long contracts use complete-object CHUNK passes followed by bounded GLOBAL planning synthesis. A canonical object is not character-truncated merely to fit a prompt.

## 8. Versioned Legal Evidence and Issue Legal RAG

Canonical legal identity is:

```text
authority
  -> authority version
       -> article / Legal Evidence ID
```

Applicability is deterministic:

```text
effective_date <= as_of < end_date_exclusive
```

The local SQLite corpus preserves public-source provenance, hashes, effective intervals, status and coverage semantics such as `FULL_TEXT` / `CURATED_EXCERPT`.

Each AuditPlan Issue drives Stage 13D retrieval independently:

```text
Issue retrieval queries
  -> exact article/citation lookup
  -> SQLite FTS5 trigram + BM25
  -> optional local BGE semantic channel
  -> weighted reciprocal-rank fusion
  -> applicable versioned Legal Evidence IDs
```

Issue support states:

```text
EVIDENCE_FOUND
EVIDENCE_FOUND_WITH_LIMITATIONS
NO_MATCH_IN_LOCAL_CORPUS
VERSION_REVIEW_REQUIRED
```

Local absence/partial coverage is never converted into a claim that no applicable law exists.

## 9. DeepSeek Issue Primary Audit

Stage 13E schedules one bounded DeepSeek request per AuditPlan Issue.

Terminal states:

```text
SUPPORTED_FINDING
NO_MATERIAL_RISK_FOUND
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Every planned Issue must receive exactly one terminal result for a complete artifact.

The provider receives bounded target/related canonical evidence, deterministic context, global facts and that Issue's Legal Evidence package. Invented canonical, Contract Evidence or Legal Evidence IDs fail validation.

A legal conclusion requires supplied Legal Evidence. A confident `NO_MATERIAL_RISK_FOUND` requires reliable contract evidence, applicable Legal Evidence and unqualified Stage 13D support.

Results checkpoint after each Issue. Resume reuses an unchanged completed Issue instead of repeating a paid call. Oversized evidence context is not silently truncated and sent.

## 10. Kimi Issue Finding + Coverage Review

Stage 13F schedules one bounded Kimi request per AuditPlan Issue.

It performs two distinct tasks:

1. independently challenge/support the DeepSeek Issue result;
2. review whether the planned Issue was adequately covered.

Finding assessments:

```text
SUPPORTED
PARTIALLY_SUPPORTED
DISAGREED
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Coverage assessments:

```text
COVERED
COVERED_BUT_QUESTIONABLE
POSSIBLE_OMISSION
INSUFFICIENT_EVIDENCE
```

`POSSIBLE_OMISSION` requires supplied Contract Evidence and explicit omission reasoning. Legal propositions additionally require supplied Legal Evidence.

Kimi may cite only Evidence IDs supplied in its bounded Issue context. Results checkpoint per Issue and resume only when the primary/context fingerprints still match.

No extra global Kimi coverage-synthesis pass is part of Stage 13. Stage 13G regression did not demonstrate a cross-Issue failure mode that justifies another provider call. Reconsider this only if later expert/benchmark evidence demonstrates systematic global omissions.

## 11. Deterministic Issue comparison

`issue-review-report.json` is generated without another model.

There is exactly one deterministic comparison for each AuditPlan Issue. Comparison considers validated primary/secondary states, severity distance, Contract Evidence alignment, Legal Evidence alignment, coverage assessment and upstream evidence limitations.

Representative states:

```text
CONSISTENT
CONSISTENT_WITH_REVIEW
MATERIAL_DISAGREEMENT
POSSIBLE_OMISSION
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Only `CONSISTENT` avoids mandatory human review. The program decides comparison state; neither model votes on which provider is correct.

The report is fingerprint-bound to the AuditPlan, primary audit and secondary review. Stale upstream artifacts invalidate freshness.

## 12. Human review

Human Review is append-only and architecture-aware.

For Issue V1:

```text
target_type = issue
target_id   = AuditPlan.issue_id
```

For Legacy RC2, historical `finding` / `omission` identities remain unchanged.

The server derives the Contract/Legal Evidence snapshot and stores the current authoritative report fingerprint; it does not trust browser-supplied Evidence IDs as the review source of truth.

If the underlying report changes, prior revisions remain visible as stale and cannot close the current review.

Only fresh final `CONFIRMED` or `REJECTED` decisions resolve a mandatory Issue review. `UNREVIEWED`, `NEEDS_MORE_REVIEW`, stale revisions and incomplete planning coverage remain outstanding.

## 13. Results and professional Workspace

`/results` and `/workspace` resolve the authoritative job architecture before selecting artifacts.

### Issue V1 Workspace

The Workspace displays every AuditPlan Issue, including no-material-risk, evidence-insufficient and review-required states. It exposes:

- Planner reasoning/questions;
- planning coverage;
- Contract Evidence;
- Issue Legal RAG and Legal Evidence;
- DeepSeek result;
- Kimi finding and coverage review;
- deterministic comparison;
- current human-review revision/state.

Workspace summary is lightweight; detailed Issue context is loaded on selection rather than serializing all legal text for potentially hundreds of Issues.

Workspace Stage 2 source validation is source-format aware: PDF/image jobs validate historical page evidence while DOCX jobs validate `SourceEvidenceArtifact`. DOCX `page_count=0` therefore means “no stable source pages”, not malformed evidence.

Selecting Contract Evidence uses one navigation callback. PDF/image Evidence selects the real source page/coordinate. DOCX Evidence scrolls to and highlights the exact logical paragraph or table-cell paragraph. Blocking DOCX source warnings remain visible and cannot be hidden by the audit result view.

### Legacy Workspace

Historical RC2 jobs retain their original Finding/Omission view without schema fabrication.

### Results ordering

The result queue uses strict workload priority:

```text
unresolved human review
> possible omission
> material disagreement
> critical
> high
> insufficient evidence
> medium
> low
```

This is an operational review queue, not a legal-risk probability.

## 14. Developer diagnostics

`/developer` defaults to a Stage 13 GET-only diagnostic surface over persisted artifacts:

```text
architecture
pipeline
Audit Plan
Issue Legal Context
Issue Primary Audit
Issue Secondary Review
Issue Comparison
Human Review
```

The view explicitly distinguishes available, missing, stale/conflicting and invalid artifacts. It does not create or rerun stages.

Historical Stage 1–9 tools remain under a collapsed `Legacy / RC2` area because some of those tools intentionally expose execution/POST actions.

## 15. Legacy RC2 boundary

The historical production topology used contract-level Stage 8/9 artifacts and a bounded Agent path. Those implementations remain in the repository for RC2 compatibility and explicit legacy inspection; they are **not** the authoritative production path for new jobs.

Legacy artifacts:

```text
ai-audit.json
secondary-review.json
review-report.json
```

Do not fabricate these schemas from Issue V1 data and do not fabricate Issue V1 data from them.

## 16. Persistence and freshness

Current private Issue V1 job artifacts include:

```text
document.json
evidence.json
ocr.json
contract.json
audit-rules.json
pipeline.json
pipeline-control.json
audit-plan.json
issue-legal-context.json
issue-primary-audit.json
issue-secondary-review.json
issue-review-report.json
human-review.json
```

Artifacts are local and ignored by Git. Important derived stages carry fingerprints tying them to authoritative upstream state. Stale artifacts remain inspectable where appropriate but must not silently become current authority.

The shape of `evidence.json` is source-format compatible rather than artificially uniform on disk: historical PDF/image jobs may still contain `PageEvidence[]`, while DOCX jobs contain a `SourceEvidenceArtifact`. Readers must discriminate source representation explicitly.

## 17. Windows distribution boundary

The portable Windows onedir/ZIP build is produced from an isolated exact base release lock plus a separate exact OCR runtime lock. The packaged runtime contains PaddlePaddle CPU `3.3.0`, PaddleOCR `3.7.0`, PaddleX `3.7.2`, their pinned runtime closure, required native DLL/PYD files and the two fixed PP-OCRv6 medium inference assets.

Private runtime jobs, source contracts, API keys, downloaded Paddle caches and BGE model weights remain excluded.

### 17.1 Runtime and model reproducibility

The release build:

- installs exact base + OCR runtime locks in a fresh Windows build environment;
- fetches only the detector/recognizer archives listed in `release/ocr-models-manifest.json`;
- validates archive SHA-256 before extraction;
- rejects unsafe tar entries/links/devices;
- validates the exact required inference file set and per-file hashes;
- places verified models at deterministic release paths;
- records release/asset metadata and third-party notice evidence;
- never commits model payloads to Git.

The frozen executable exposes separate runtime/model/inference diagnostics. Missing/corrupt/unexpected model assets fail visibly instead of causing an implicit download.

### 17.2 PaddleX/PyInstaller compatibility boundary

PaddleX `3.7.2` checks its `ocr-core` extra through `importlib.metadata.version(...)`. The PyInstaller bundle must therefore preserve distribution metadata for:

```text
imagesize
opencv-contrib-python
pyclipper
pypdfium2
python-bidi
shapely
```

Those packages are already part of the exact OCR runtime closure; preserving their `.dist-info` prevents the frozen executable from falsely reporting that the OCR extra is missing.

Law-Rag also packages its fixed minimal OCR pipeline configuration as a release asset and passes it explicitly through `paddlex_config`. The production path does not depend on PaddleX locating a package-relative default `OCR.yaml`, and the minimal configuration contains only the approved detector/recognizer models.

For the pinned PaddlePaddle `3.3.0` CPU path, `enable_mkldnn=False` is a release compatibility requirement because the Windows real-inference regression exposed a oneDNN/PIR `ArrayAttribute<Double>` failure with that branch enabled.

### 17.3 Validation

Stage 14.4 established the frozen OCR runtime. Stage 14.5 extends that evidence to real packaged model inference.

Authoritative Stage 14.5 Windows run #64 (`32145367670`) proves:

- clean onedir build with exact runtime + fixed official models;
- local model resolution and SHA-256 integrity;
- frozen model validation with network unavailable;
- real frozen OCR inference with network unavailable;
- existing packaged application/PDF workflow smoke;
- deterministic portable RC ZIP + manifest;
- fresh extraction of the final RC ZIP and user-flow smoke;
- no model payload tracked in Git;
- successful onedir + portable RC artifact upload.

Companion normal CI #727 (`32145367680`) passed `315` backend tests with `5` skipped and the existing single Starlette/httpx deprecation warning, plus deterministic quality gates, frontend production build and the exact Windows OCR dependency smoke.

Stage 14.6 owns Home/Pipeline exposure of the complete source-format paths. Stage 14.7 owns the final combined Stage 14 release closeout/regression.

## 18. Validation and next boundary

Stage 13G final provider-free regression runs with fake Planner/DeepSeek/Kimi providers and hard-fails on attempted outbound HTTP. It proves one-to-one Issue identity across:

```text
AuditPlan
= Issue Legal Context
= Issue Primary Audit
= Issue Secondary Review
= Issue Comparison
```

Stage 14.1–14.3 preserve that model/audit topology while extending the source boundary. Stage 14.4 added the frozen Paddle runtime, and Stage 14.5 added fixed verified offline detector/recognizer assets plus real network-blocked packaged inference.

**Stage 14.1–14.5 are complete. The next implementation scope is Stage 14.6 — Pipeline + Home integration.** Do not begin Stage 14.7 in the same implementation slice.
