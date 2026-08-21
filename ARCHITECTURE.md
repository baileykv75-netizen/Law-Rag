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

Source navigation, Results/Workspace reads, Developer diagnostics, Human Review, local OCR and local legal retrieval do not implicitly execute external providers.

**Stage 16.1–16.3 are complete.** The production legal baseline remains `three-domain-core@1.0.0`: 3 READY Corpus Packs, 14 Authorities, 15 Versions and 1274 unique Articles. Stage 16.3 validated private expert-label audit and scoped professional metric infrastructure without adding any real expert dataset or professional accuracy claim. The active next boundary is Stage 16.4 real-provider `ISSUE_V1` UAT observation capture.

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
INGEST                       10%
  -> OCR                     25%
  -> STRUCTURE               38%
  -> RULES                   48%
  -> AUDIT_PLAN              58%
  -> ISSUE_LEGAL_CONTEXT     68%
  -> ISSUE_PRIMARY_AUDIT     82%
  -> ISSUE_SECONDARY_REVIEW  92%
  -> ISSUE_REVIEW_REPORT    100%
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

Final Stage 15 closeout validation:

```text
Law-Rag Stage 15 CI #123 (32456205510)                  SUCCESS
Law-Rag Stage 15.5 Windows Baseline CI #9 (32456205586) SUCCESS
```

The Windows closeout revalidated exact release-lock build, frozen baseline installation, packaged PDF/OCR/HTTP/privacy smoke, deterministic portable RC packaging, fresh-extracted Stage 12–14 regressions and artifact upload.

Draft PR #13 and #14 are stacked validation carriers and remain intentionally unmerged unless separately authorized.

## 20. Stage 16 evaluation architecture

Stage 16 adds a measurement layer around the proven production architecture; it does not create another audit pipeline.

Evidence classes remain separate:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

### 20.1 Stage 16.1 suite layer

Stage 16.1 added:

```text
EvaluationSuiteManifest
  |
  +-- BENCHMARK
  |     BenchmarkDataset
  |       + BenchmarkObservationSet
  |       -> Stage 11A deterministic evaluator
  |
  +-- PUBLIC_QUALITY_PROFILE
        QualityGateProfile
        -> Stage 11B deterministic quality runner

  -> sanitized EvaluationSuiteRunReport
```

Final Stage 16.1 closeout:

```text
head 706ce85bc5b472896d33dcf4d926501755656247
Law-Rag Stage 16 CI #15 (32458037391)  SUCCESS
Law-Rag Stage 15 CI #130 (32458037327) SUCCESS
```

### 20.2 Stage 16.2 public regression layer

Stage 16.2 extends the suite with:

```text
PUBLIC_REGRESSION_PROFILE
  -> versioned PublicRegressionProfile
  -> named deterministic runner
  -> scoped QualityRunReport + diagnostics + source fingerprints
```

Historical Stage 11A/11B evaluator/profile meanings remain unchanged.

The Stage 16.2 public artifacts are:

```text
stage16b_three_domain_retrieval.dataset.json
stage16b_three_domain_regression.json
stage16b_evaluation_suite.json
```

The nine-case dataset is promoted unchanged from the Stage 15 three-domain retrieval fixture. Runtime semantic comparison fails closed if the promoted case truth diverges from its source fixture.

The profile pins `three-domain-core@1.0.0`. The selected Corpus Release Pack catalog must exactly match the current READY routing catalog on Pack ID/version/domain/member paths; otherwise the run fails closed instead of mixing old release truth with new routing metadata.

The runner deterministically rebuilds scratch legal/retrieval stores and evaluates broad/scoped lexical retrieval, routing scope, `UNMAPPED` fallback, cross-domain Pack union and trademark `as_of` version selection. No paid/network DeepSeek or Kimi call occurs.

Final Stage 16.2 validation:

```text
head 67407e54b27e595e82119b055774241ce708b971
Law-Rag Stage 16 CI #50 (32459347103) SUCCESS
backend pytest                             434 passed, 5 skipped, 1 warning
historical Stage 11B gates                PASS
Stage 16.2 regression gates               10 / 10 PASS
expanded Stage 16b suite                  3 / 3 PASS
frontend build                            PASS
```

Named nine-case values:

```text
scoped Recall@5 / MRR       1.00 / 1.00
broad Recall@5 / MRR        1.00 / 1.00
scoped-broad deltas         0.00 / 0.00
Authority compliance       1.00
route eligibility          1.00
UNMAPPED fallback           1.00
CROSS_DOMAIN union          1.00
trademark version boundary 1.00
Articles                    1274
```

These are scoped deterministic regression results, not professional legal accuracy.

### 20.3 Stage 16.3 private expert layer

Stage 16.3 adds a private professional truth/audit layer without adding another production analysis pipeline:

```text
ExpertBenchmarkProtocol
  + private BenchmarkDataset
  + private BenchmarkObservationSet
  + ExpertLabelAuditArtifact
  -> sanitized ExpertBenchmarkRunReport
```

All inputs remain external or under ignored `benchmark_private/`; tracked paths are rejected. Every expert case must use `PRIVATE_EXTERNAL` provenance.

Each private case has exactly one audited label state:

```text
AGREED
ADJUDICATED
AMBIGUOUS
```

The protocol requires at least two expert reviewers. `ADJUDICATED` requires an adjudicator; `AGREED` cannot claim one was needed. `AMBIGUOUS` truth remains visible and is excluded from professional performance metrics instead of being coerced into a positive/negative answer.

A canonical SHA-256 label fingerprint binds each expert audit to the current case version and complete expected assertions. Any post-review truth mutation invalidates the prior audit. Dataset, observations and label audit must also have exact case-ID/case-version coverage; selective removal of difficult cases fails closed.

Initial metric types are deliberately scoped:

```text
BINARY_CLASSIFICATION
  -> TP / FP / FN / TN
  -> precision / recall / F1

SET_EXTRACTION
  -> TP / FP / FN
  -> precision / recall / F1
```

Binary truth must include usable expert-positive and expert-negative cases. Set truth must be exhaustive `SET_EQUALS`; partial `SET_CONTAINS` labels are not accepted for precision/recall/F1.

The report also carries expert-truth quality:

```text
agreed / adjudicated / ambiguous / usable counts
agreement_rate
adjudication_rate
ambiguity_rate
usable_rate
minimum reviewer required / observed
```

Professional system metrics therefore stay attributable to the quality of the exact expert truth set.

The private expert evaluator is a companion metric layer to the Stage 16 suite architecture. The generic `PRIVATE_EXPERT` suite class can still orchestrate private BenchmarkDataset/ObservationSet evaluation, but Stage 16.3 deliberately does not invent a threshold-bearing expert-protocol suite PASS/FAIL entry before real dataset quality and release criteria exist.

Validated Stage 16.3 implementation:

```text
head 3393caa150e2baee459ca0969e8f17ee451d6156
Law-Rag Stage 16 CI #62 (32460155009) SUCCESS
backend pytest                            443 passed, 5 skipped, 1 warning
historical Stage 11B gates               PASS
Stage 16.2 public regression             PASS
Stage 16b public suite                   PASS
frontend build                           PASS
```

No real professionally labeled dataset was committed or executed. Stage 16.3 therefore validates the protocol/evaluator infrastructure only; it does not establish a professional accuracy, high-risk recall, citation relevance value or expert-derived release threshold.

### 20.4 Real-provider UAT boundary

`REAL_PROVIDER_UAT` observations remain external/ignored and record a current real provider, model and SHA-256 artifact fingerprint. Fake provider/producer identities are rejected.

Stage 16.4 owns the explicit capture path. It must reuse the existing production Planner/RAG/DeepSeek/Kimi/comparison chain and existing approval/cancellation/checkpoint semantics rather than creating a second model pipeline. Actual paid/network execution stays explicit opt-in and outside ordinary CI.

Real-provider observations are provider-specific behavior evidence. They are not expert truth and model agreement is not correctness.

### 20.5 No fake global accuracy

The evaluation layer deliberately does not emit cross-task `overall_accuracy`, `legal_accuracy` or an equivalent aggregate. Every metric retains its named dataset/profile version, label definition and scope.

## 21. Next boundary — Stage 16.4

Stage 16.4 owns **real-provider `ISSUE_V1` UAT observation capture**.

It must:

- reuse the current production Audit Planner -> Issue Legal RAG -> DeepSeek -> Kimi -> deterministic comparison topology;
- require configured providers plus existing explicit approval/cancellation checks;
- capture provider/model identity and authoritative input/output artifact SHA-256 fingerprints;
- preserve one-to-one AuditPlan Issue coverage and checkpoint/restart behavior;
- keep detailed UAT observations external or under ignored private paths;
- emit only sanitized provenance/summary suitable for Stage 16 evidence assembly;
- test capture mechanics in normal CI with provider doubles only;
- require explicit opt-in for actual paid/network UAT;
- keep UAT evidence separate from private expert correctness labels.

Stage 16.4 must not invent release thresholds from a small UAT sample, tune prompts merely to improve one run, redesign `ISSUE_V1`, or absorb Stage 17+ work.