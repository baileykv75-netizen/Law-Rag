# CURRENT_TASK.md

# Stage 16 — Expert Benchmark + Regression Corpus + Real-Provider UAT

## Status

```text
Stage 11A–11E   COMPLETE / benchmark + quality + release foundations
Stage 12A–12F   COMPLETE / RC2 VALIDATED
Stage 13A–13G   COMPLETE / ISSUE_V1 production migration validated
Stage 14.1–14.7 COMPLETE / OCR distribution + DOCX + packaged Windows validation
Stage 15.1–15.5 COMPLETE / official three-domain corpus + domain-aware RAG + Windows baseline validated

Stage 16.1      COMPLETE / versioned evaluation-suite architecture + evidence-class isolation
Stage 16.2      NEXT     / public deterministic regression corpus expansion
Stage 16.3      PENDING  / private expert benchmark protocol + metrics
Stage 16.4      PENDING  / real-provider ISSUE_V1 UAT observation capture
Stage 16.5      PENDING  / Stage 16 release-quality evidence matrix + final regression
```

Stage 16 measures and hardens the proven Stage 13–15 product. It does **not** redesign the production review topology.

## Stage 15 closeout baseline

Authoritative closeout head before Stage 16:

```text
2ea5b936723133ddf5eb8829534c0e1530c60f85
```

Closeout validation:

```text
Law-Rag Stage 15 CI #123
run 32456205510
SUCCESS

Law-Rag Stage 15.5 Windows Baseline CI #9
run 32456205586
SUCCESS
```

The frozen packaged baseline remains:

```text
Corpus Release  three-domain-core@1.0.0
READY Packs     3
Authorities     14
Versions        15
Unique Articles 1274
```

Draft PR #13 and #14 remain stacked Stage 15 validation carriers only. They are not authorized for merge.

## Production architecture Stage 16 must preserve

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

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

## Stage 16 measurement principle

Stage 16 keeps three evidence classes explicit:

```text
PUBLIC_REGRESSION
  checked-in synthetic/public/legal deterministic regression evidence

PRIVATE_EXPERT
  professionally labeled reviewer truth kept outside tracked Git paths

REAL_PROVIDER_UAT
  explicit paid/network ISSUE_V1 observations with provider/model/artifact provenance
```

These evidence classes must never be collapsed into one invented `overall_accuracy` or `legal_accuracy` score.

## Stage 16.1 — Versioned Evaluation Suite Architecture — COMPLETE

Stage 16.1 added one deterministic orchestration layer above the existing Stage 11 benchmark and quality evaluators:

```text
EvaluationSuiteManifest
  -> ordered EvaluationSuiteEntry[]
       -> existing BenchmarkDataset + BenchmarkObservationSet evaluator
       OR
       -> existing public QualityGateProfile evaluator
  -> sanitized deterministic EvaluationSuiteRunReport
```

Implemented boundaries:

- versioned suite schema and evaluator identity;
- explicit `PUBLIC_REGRESSION`, `PRIVATE_EXPERT`, `REAL_PROVIDER_UAT` suite classes;
- public suite data restricted to `benchmarks/public/`;
- private expert suite/data restricted to external or ignored `benchmark_private/` locations;
- real-provider UAT observations restricted to external/ignored paths;
- current production UAT provider identity limited to DeepSeek/Kimi and fake producer identities rejected;
- provider/model/SHA-256 artifact provenance required for UAT observations;
- suite summaries omit assertion-level expected/observed values, expert labels, private contract text, raw provider payloads, hidden reasoning and credentials;
- dataset/profile/evaluation-input SHA-256 fingerprints retained for auditability;
- checked-in public Stage 16.1 orchestration smoke;
- deterministic CLI and Stage 16 CI.

The suite evaluator consumes observations only. It never calls DeepSeek, Kimi, OCR or another provider itself.

Authoritative Stage 16.1 implementation validation on head `de9fb64d3b03316eb3427f0137fc0c9086d145f3`:

```text
Law-Rag Stage 16 CI #9
run 32457699628
SUCCESS

backend pytest
428 passed, 5 skipped, 1 third-party warning

existing public deterministic quality gates
PASS

Stage 16 public evaluation suite
2 / 2 entries PASS

frontend production build
PASS

Law-Rag Stage 15 regression CI #127
run 32457699622
SUCCESS

Stage 15.5 Windows workflow on this PR
SKIPPED as intended
```

Draft PR #15 is the validation-only Stage 16.1 carrier:

```text
head: stage16-1-evaluation-suite-architecture
base: stage15-5-windows-baseline-corpus
```

PR #15 is not authorized for merge.

See `docs/STAGE16_EVALUATION.md`.

## Stage 16.2 — Public deterministic regression corpus expansion — NEXT

### Goal

Promote the strongest already-public deterministic Stage 13–15 regression evidence into versioned Stage 16 benchmark datasets/suite entries so the public suite measures more than harness integrity and the old Stage 7 curated retrieval seed.

### Required focus

Stage 16.2 should reuse and formalize existing repository-safe evidence before inventing new cases. Priority sources include:

1. Stage 15 three-domain retrieval benchmark (`legal_data/fixtures/stage15_domain_retrieval_benchmark.json`);
2. domain-routing eligibility and broad-vs-scoped retrieval invariants;
3. legal-version / `as_of` applicability cases;
4. ISSUE_V1 deterministic artifact/fingerprint/integrity regression cases that can be expressed without paid providers;
5. public synthetic failure-state cases for missing/stale/conflicting evidence where repository-safe fixtures already exist.

### Acceptance direction

Stage 16.2 must:

- create explicit versioned public datasets rather than burying evaluation only inside pytest;
- preserve task-level metrics/scope instead of inventing one cross-task score;
- include deterministic case diagnostics;
- keep all checked-in cases repository-safe;
- reuse the Stage 16.1 suite runner rather than adding another evaluator;
- preserve Stage 15 domain routing and Authority eligibility semantics;
- keep provider calls entirely out of public CI.

### Non-goals for 16.2

Do not yet:

- create or publish private expert labels;
- run paid DeepSeek/Kimi UAT;
- tune production prompts merely to improve benchmark numbers;
- enlarge the legal corpus without independent corpus evidence;
- change ISSUE_V1 topology;
- begin Stage 17+.

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

**Stage 16.1 is COMPLETE and validated. Stage 16.2 is the only NEXT implementation scope. Do not begin Stage 16.3+, Stage 17+, or merge Draft PR #13/#14/#15 without separate authorization.**
