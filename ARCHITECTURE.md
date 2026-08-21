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
  +-- versioned official Legal Evidence
  +-- deterministic Issue -> legal-domain -> Corpus Pack routing
  +-- Exact + BM25/FTS5 + optional local BGE retrieval
  +-- DeepSeek issue-by-issue primary audit
  +-- Kimi issue-by-issue finding + coverage review
  +-- deterministic Issue comparison
  +-- append-only human review
  +-- architecture-aware Results / Workspace / Developer
  +-- writable local runtime corpus + persistence
  |
  +---- explicit bounded outbound calls ----> configured DeepSeek / Kimi APIs
```

Source navigation, Results/Workspace reads, Stage 13 Developer diagnostics, Human Review, local OCR and local legal retrieval do not implicitly execute external providers.

**Stage 15 is complete.** The production legal baseline is `three-domain-core@1.0.0`: 3 READY Corpus Packs, 14 Authorities, 15 Versions and 1274 unique Articles. Issue-level domain-aware retrieval and Windows baseline-corpus distribution are validated.

## 3. Authoritative job architectures

Runtime architecture states remain:

```text
ISSUE_V1     current production architecture for new jobs
LEGACY_RC2   historical Stage 8/9 contract-level architecture
CONFLICT     fail closed; do not guess which artifact family is authoritative
```

The resolver uses persisted production provenance, not a convenient filename check. Completed historical RC2 jobs remain readable and are not automatically rewritten.

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

## 5. Source-format boundary

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

Planner/domain routing/RAG/DeepSeek/Kimi/comparison/Human Review remain source-format neutral.

## 6. Provider boundary

`REQUIRE_APPROVAL` applies before the Audit Planner's first actual outbound call. Local STRUCTURE + RULES may complete first.

A provider must also be configured. Approval does not manufacture credentials. Planner, DeepSeek and Kimi requests cross persisted approval/cancellation checks independently. A request that has already started cannot be recalled, but cancellation prevents later calls.

Background limits remain bounded:

```text
Pipeline workers                    <= 4
local processing slots              <= 2
OCR slots                           <= 1
concurrent external provider calls  <= 2
```

## 7. Document and Evidence layer

Supported input:

```text
PDF
JPG / JPEG
PNG
modern DOCX
```

Legacy `.doc` is not supported as DOCX.

Reliable native PDF/DOCX text is preferred. OCR is used only where needed. Contract/OCR/DOCX text is untrusted data and never treated as developer/system instruction.

### 7.1 Cross-format Source Evidence

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

### 7.2 DOCX ingestion safety

DOCX ingestion uses local OOXML ZIP/XML processing and preserves paragraph/table order, Word numbering semantics, table row/cell/paragraph coordinates and embedded-image relationship identity.

Malformed/non-OOXML packages, unsafe archive paths, encrypted entries, macro/VBA payloads, pathological expansion/compression, oversized XML, DTD/entity input and password-protected Office containers fail explicitly.

Tracked changes, unresolved numbering, unsupported text boxes, omitted header/footer/footnote/endnote content or embedded image text create visible source warnings. Blocking warnings prevent a false claim of complete source coverage.

### 7.3 Canonical boundary

`contract.json` is the downstream canonical source of truth. PDF native text, OCR blocks and DOCX structural Evidence converge into the same `EvidenceUnit` stream and deterministic canonical extractor.

Clauses, blocks, parties, dates, amounts, percentages, identifiers and references retain Evidence IDs, typed source spans and extraction provenance.

## 8. Local OCR distribution

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

## 9. Deterministic rules

Machine-checkable conditions remain ordinary code. States:

```text
PASS
FAIL
REVIEW
NOT_APPLICABLE
```

`FAIL` means a configured deterministic condition failed; it is not itself a legal conclusion. Rule results may seed Planner hints but do not define complete review scope.

## 10. Audit Planner and planning coverage

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

`REVIEWED_NO_SPECIFIC_ISSUE` is planning coverage only, never a legal-safe conclusion.

## 11. Canonical legal identity and Corpus Packs

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

Corpus Pack is a classification/eligibility/distribution layer and never creates a second legal identity. Membership is many-to-many; one Authority/Version may belong to several Packs without duplicating legal body text.

Production baseline:

```text
Corpus Release: three-domain-core@1.0.0
Packs:          3 READY
Authorities:    14
Versions:       15
Articles:       1274 unique
```

The three READY packs are intellectual-property, enterprise-compliance and labor-dispute focused.

Application version, Corpus Release version, Pack version and Authority Version are independent.

## 12. Corpus Release and update safety

A Corpus Release is an immutable publication index over frozen Authority/Version manifests. It pins selected Packs, Authority/version lifecycle metadata, snapshot hashes, article counts and a deterministic release digest without duplicating legal text.

Legal text under an existing `(authority_id, version_id)` is immutable. Changed legal text requires a new Version identity.

The update planner fails closed on unsafe changes including historical Version removal, same-Version snapshot mutation, Authority metadata mutation, identity mutation, Pack removal/version regression and non-advancing Corpus Release ancestry.

Safe publication path:

```text
validated candidate Corpus Release
 -> deterministic update plan
 -> rebuild sibling temporary legal.db
 -> verify totals / identities / hashes
 -> atomic os.replace() only after complete success
```

Failure leaves the previous runtime legal database untouched.

## 13. Domain-aware Issue Legal RAG

Stage 15.4 inserts a deterministic eligibility layer before the existing retrieval engine:

```text
AuditPlan Issue
 -> deterministic domain route
 -> READY Corpus Pack domain tags
 -> eligible Authority allowlist
 -> applicable Authority Version for as_of
 -> Exact Citation + FTS5/BM25 + optional local BGE
 -> deterministic weighted RRF fusion
 -> IssueLegalEvidencePackage
```

Current route states:

```text
INTELLECTUAL_PROPERTY
ENTERPRISE_COMPLIANCE
LABOR_DISPUTE
CROSS_DOMAIN
UNMAPPED
```

Routing uses Issue signals such as topic, review rationale, questions, retrieval queries and legacy topic hints. Conservative matching is intentional: a false positive can wrongly narrow legal scope.

When no safe mapping exists, the route broadens explicitly to all eligible READY Packs rather than converting no match into a claim that no law exists.

Authority scope is enforced in every retrieval channel before fusion:

- Exact Citation rejects out-of-scope authorities/evidence IDs;
- FTS5/BM25 applies Authority predicates before lexical ranking;
- semantic retrieval filters eligible Legal Evidence IDs before vector ranking;
- final fusion checks eligibility again as defense in depth.

Applicability remains deterministic:

```text
effective_date <= as_of < end_date_exclusive
```

A frozen future Version therefore does not become prematurely applicable.

`IssueLegalContext` persists route provenance and a deterministic routing-catalog fingerprint. Pack/domain-membership changes make an old context visibly stale.

Legacy development stores with no overlap against Stage 15 Pack scope retain historical retrieval behavior with an explicit warning rather than silently producing empty legal evidence.

## 14. DeepSeek primary + Kimi secondary review

DeepSeek performs one bounded request per AuditPlan Issue. Kimi performs one bounded independent finding + coverage review per Issue. Both providers may cite only supplied canonical Contract/Legal Evidence identities. Unsupported identities fail validation. Results checkpoint per Issue; unchanged completed checkpoints are reused rather than repeating paid calls.

No extra global Kimi vote/synthesis pass exists without demonstrated evidence of a cross-Issue failure mode.

## 15. Deterministic Issue comparison and Human Review

`issue-review-report.json` compares DeepSeek/Kimi outputs without another model. Only `CONSISTENT` avoids mandatory human review. Two-model agreement is not proof or a correctness probability.

Human Review is append-only and fingerprint-bound to the current authoritative Issue report. Only fresh final `CONFIRMED` or `REJECTED` decisions resolve mandatory review. Stale revisions and incomplete planning coverage cannot silently close a job.

## 16. Results, Workspace and Developer

`/results` and `/workspace` resolve authoritative architecture before choosing artifacts. Workspace exposes Planner scope, Contract Evidence, Legal Evidence, DeepSeek, Kimi, deterministic comparison and Human Review.

`/developer` defaults to GET-only diagnostics over persisted Stage 13+ artifacts. Opening diagnostics must not create/re-run stages or call providers. Historical Stage 1–9 execution tools stay visibly isolated under Legacy/RC2.

## 17. Windows baseline corpus distribution

Stage 15.5 ships immutable packaged legal assets for `three-domain-core@1.0.0` instead of the historical curated seed.

Packaged assets include verified `legal.db`, `retrieval.db` and release metadata with pinned hashes and Corpus Release identity.

Normal first-launch installation is:

```text
verify packaged metadata + SHA-256
 -> stage complete legal directory beside runtime target
 -> verify staged legal.db/retrieval.db hashes
 -> write installed-corpus metadata
 -> atomic rename into writable runtime storage
```

If a complete runtime corpus already exists, it is left untouched. This prevents an application upgrade from rolling back an independently updated Stage 15.3 corpus.

If the runtime legal directory is incomplete, startup fails closed rather than mixing packaged and runtime files.

A non-mutating `--diagnose-corpus` offline retrieval smoke verifies the installed/packaged corpus without rewriting packaged baseline bytes.

## 18. Persistence and privacy

Private Issue V1 artifacts include document/evidence/OCR/canonical/rule/Pipeline/Issue review/human-review JSON under ignored runtime paths.

`evidence.json` remains intentionally source-format compatible rather than artificially uniform:

```text
PDF/image -> PageEvidence[]
DOCX      -> SourceEvidenceArtifact
```

Private runtime jobs, source contracts, API keys, downloaded model caches and private benchmark data must not enter the public repository or release bundle.

## 19. Stage 15 validation boundary — COMPLETE

Stage 15.4 domain-aware retrieval validation:

```text
Law-Rag Stage 15 CI #96 (32441338892)
backend pytest                      416 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

Final Stage 15.5 product-head validation:

```text
Law-Rag Stage 15 CI #117 (32444333939)
backend pytest                      422 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

Authoritative Windows baseline validation:

```text
Law-Rag Stage 15.5 Windows Baseline CI #6 (32444333963)
exact Windows release-lock onedir build           PASS
frozen baseline + writable runtime install check  PASS
packaged PDF/OCR/HTTP/privacy smoke                PASS
deterministic portable RC ZIP + manifest          PASS
fresh-extracted Stage 12–14 regression smokes     PASS
inspectable onedir + portable RC artifact upload  PASS
```

Draft PR #13 and #14 are stacked validation carriers and remain intentionally unmerged unless separately authorized.

## 20. Next boundary — Stage 16

Stage 16 owns expert benchmark + regression corpus + real-provider UAT.

It may measure and harden retrieval quality, Issue coverage, legal-citation correctness, provider behavior, end-to-end review quality and failure-state handling against the proven Stage 13–15 architecture.

It must preserve:

- canonical `Authority -> Version -> Article / Legal Evidence` identity;
- immutable historical legal versions;
- independent Corpus Release / Pack / Authority-Version identities;
- deterministic `as_of` applicability;
- explicit broad-fallback semantics for unmapped legal domains;
- existing ISSUE_V1 stage topology;
- Stage 14 source/OCR boundary;
- Stage 15 Windows baseline/runtime-corpus separation;
- explicit provider approval/cancellation boundaries;
- public/private benchmark data separation.

Stage 16 must not absorb Stage 17 tray/history, Stage 18 encryption/report-export/provider-settings, or Stage 19 installer/signing/update work.
