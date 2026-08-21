# CURRENT_TASK.md

# Stage 16 — Expert Benchmark + Regression Corpus + Real-Provider UAT

## Status

```text
Stage 11A–11E   COMPLETE / benchmark + quality + release foundations
Stage 12A–12F   COMPLETE / RC2 VALIDATED
Stage 13A–13G   COMPLETE / ISSUE_V1 production migration validated
Stage 14.1–14.7 COMPLETE / OCR distribution + DOCX + packaged Windows validation
Stage 15.1–15.5 COMPLETE / official three-domain corpus + domain-aware RAG + Windows baseline validated

Stage 16.1      IN PROGRESS
                versioned evaluation-suite architecture + evidence-class isolation

Stage 16.2      PENDING / public deterministic regression corpus expansion
Stage 16.3      PENDING / private expert benchmark protocol + metrics
Stage 16.4      PENDING / real-provider ISSUE_V1 UAT observation capture
Stage 16.5      PENDING / Stage 16 release-quality evidence matrix + final regression
```

Stage 16 measures and hardens the proven Stage 13–15 product. It does **not** redesign the production review topology.

## Stage 15 closeout baseline

Authoritative closeout head before Stage 16:

```text
2ea5b936723133ddf5eb8829534c0e1530c60f85
```

Validation triggered by the Stage 15 closeout documentation itself:

```text
Law-Rag Stage 15 CI #123
run 32456205510
SUCCESS

Law-Rag Stage 15.5 Windows Baseline CI #9
run 32456205586
SUCCESS
```

Windows closeout revalidated:

- exact Windows onedir build from release locks;
- frozen `three-domain-core@1.0.0` baseline and writable runtime install behavior;
- packaged PDF/OCR/HTTP/privacy smoke;
- deterministic portable RC ZIP + manifest;
- fresh-extracted Stage 12–14 regression smokes;
- inspectable onedir and portable RC artifact uploads.

Draft PR #13 and #14 remain stacked validation carriers only. They are not authorized for merge.

## Production architecture that Stage 16 must preserve

```text
Source file
 -> Source Evidence
 -> Canonical Contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> issue-based Legal RAG
      -> deterministic Issue domain route
      -> READY Corpus Pack eligibility
      -> applicable Authority Version for as_of
      -> Exact Citation + BM25/FTS5 + optional local BGE
      -> deterministic fusion
 -> one bounded DeepSeek primary request per AuditPlan Issue
 -> one bounded Kimi finding + coverage review per AuditPlan Issue
 -> deterministic Issue comparison
 -> append-only Issue human review
 -> architecture-aware Results / Workspace / Developer
```

Legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

The frozen packaged baseline remains:

```text
Corpus Release  three-domain-core@1.0.0
READY Packs     3
Authorities     14
Versions        15
Unique Articles 1274
```

## Stage 16 measurement principle

Stage 16 must keep three evidence classes explicit instead of blending them into one fake accuracy number:

```text
PUBLIC_REGRESSION
  checked-in synthetic/public/legal regression evidence

PRIVATE_EXPERT
  professionally labeled datasets and reviewer truth kept outside tracked Git paths

REAL_PROVIDER_UAT
  explicit paid/network ISSUE_V1 runs with provider/model/artifact provenance
```

A passing public regression suite is not a claim of professional legal accuracy. A private expert benchmark is not safe to publish merely because its aggregate score is useful. A real-provider UAT run is not reproducible unless its producer/model and artifact fingerprints are recorded.

## Stage 16.1 — Versioned Evaluation Suite Architecture

### Goal

Create one deterministic orchestration layer above the existing Stage 11 benchmark and quality evaluators so later Stage 16 work can run named/versioned evaluation suites without creating a second benchmark engine.

The suite evaluator must consume observations; it must **never call DeepSeek, Kimi, OCR or another model/provider by itself**.

### Required architecture

```text
EvaluationSuiteManifest
  -> ordered EvaluationSuiteEntry[]
       -> existing BenchmarkDataset + BenchmarkObservationSet evaluator
       OR
       -> existing public QualityGateProfile evaluator
  -> sanitized deterministic EvaluationSuiteRunReport
```

Real-provider execution is deferred. Stage 16.4 will generate Observation Sets; Stage 16.1 only defines how those observations are validated and evaluated.

### Acceptance criteria

1. Add a versioned `EvaluationSuiteManifest` schema with a stable suite ID/version and unique entry IDs.
2. Support explicit suite classes:
   - `PUBLIC_REGRESSION`
   - `PRIVATE_EXPERT`
   - `REAL_PROVIDER_UAT`
3. Reuse the existing Stage 11 `BenchmarkDataset -> BenchmarkObservationSet -> BenchmarkRunReport` evaluator for benchmark entries.
4. Reuse the existing Stage 11B public quality-profile evaluator for public deterministic quality entries.
5. Public suite inputs must remain inside the checked-in `benchmarks/public/` boundary.
6. Private expert inputs must be external or under ignored `benchmark_private/`; tracked public paths must fail closed.
7. Real-provider UAT Observation Sets must remain external/ignored and must identify real provider, model and artifact fingerprint for every observation; `fake` producers are invalid UAT evidence.
8. The suite report must be sanitized summary evidence. It must not embed benchmark expected/observed payloads, expert labels, private contract text, hidden reasoning, API keys or raw provider responses.
9. Preserve dataset/profile identity and SHA-256 fingerprints in the suite report so evidence can be reproduced/audited.
10. Do not emit `overall_accuracy`, `legal_accuracy` or another cross-task aggregate score.
11. Add a checked-in public Stage 16.1 orchestration smoke suite using only existing public benchmark/quality evidence.
12. Add a CLI for deterministic suite execution and JSON report output.
13. Add tests for public execution, private-data isolation, UAT producer provenance, duplicate/invalid manifests and report sanitization.
14. Add a Stage 16 CI workflow that runs backend pytest, existing public quality gates, the public Stage 16.1 suite and the frontend production build without provider secrets/network calls.

### Non-goals for 16.1

Do not yet:

- enlarge the Stage 15 retrieval benchmark/corpus;
- create professional expert labels;
- call DeepSeek/Kimi for UAT;
- change provider prompts or model topology;
- change legal corpus identity/version semantics;
- modify Windows packaging;
- add Stage 17 tray/history work;
- add Stage 18 encryption/report-export/provider-settings work;
- add Stage 19 installer/signing/update work.

## Stage 16 invariants

The entire stage must preserve:

- one canonical Contract model and exact Contract Evidence provenance;
- canonical `Authority -> Version -> Article / Legal Evidence` identity;
- immutable historical legal versions and deterministic `as_of` applicability;
- independent application / Corpus Release / Pack / Authority-Version identities;
- explicit broad fallback when domain routing cannot safely narrow legal scope;
- current ISSUE_V1 Planner/RAG/DeepSeek/Kimi/comparison/Human Review topology;
- Stage 14 PDF/image/DOCX source boundary and local OCR rules;
- Stage 15 immutable packaged baseline vs writable upgrade-preserving runtime corpus separation;
- explicit provider approval/cancellation boundaries;
- public/private benchmark separation;
- no credentials, private contracts, private reviewer labels or raw private provider payloads in Git.

## Deferred after Stage 16

```text
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Only Stage 16.1 is active. Finish and validate the evaluation-suite architecture before beginning Stage 16.2. Do not merge Stage 15 validation PRs or begin Stage 17+ without separate authorization.**
