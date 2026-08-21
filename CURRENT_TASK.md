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
Stage 16.2      COMPLETE / public deterministic three-domain regression corpus + gates
Stage 16.3      COMPLETE / private expert protocol + label audit + scoped metric evaluator validated
Stage 16.4      IN PROGRESS / capture + suite mechanics VALIDATED; READY_FOR_REAL_UAT; paid/network UAT NOT RUN
Stage 16.5      PENDING / Stage 16 release-quality evidence matrix + final regression
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

Final Stage 16.1 closeout head:

```text
706ce85bc5b472896d33dcf4d926501755656247
```

Final closeout validation:

```text
Law-Rag Stage 16 CI #15 (32458037391)  SUCCESS
Law-Rag Stage 15 CI #130 (32458037327) SUCCESS
```

Draft PR #15 is validation-only and remains unmerged without separate authorization.

## Stage 16.2 — Public deterministic regression corpus expansion — COMPLETE

Stage 16.2 promotes the existing nine-case Stage 15 three-domain retrieval fixture into a versioned public Stage 16 dataset instead of leaving the quality evidence only inside pytest.

Public artifacts:

```text
benchmarks/public/stage16b_three_domain_retrieval.dataset.json
benchmarks/public/stage16b_three_domain_regression.json
benchmarks/public/stage16b_evaluation_suite.json
```

The original source fixture remains unchanged:

```text
legal_data/fixtures/stage15_domain_retrieval_benchmark.json
```

The runner fails closed if the promoted Stage 16 dataset diverges semantically from that Stage 15 source fixture. A changed benchmark truth therefore requires an explicit dataset/source version change rather than silent relabeling.

Stage 16.2 adds a separate `PUBLIC_REGRESSION_PROFILE` suite entry instead of mutating the historical Stage 11B quality profile. The expanded public suite remains backward-compatible with the Stage 16.1 smoke:

```text
stage16a suite -> 2 historical entries
stage16b suite -> those same 2 entries + Stage16b three-domain regression
```

The three-domain runner deterministically rebuilds `legal.db` + FTS5 retrieval from the pinned Corpus Release and evaluates:

- scoped lexical Recall@5;
- scoped lexical MRR;
- broad lexical Recall@5;
- broad lexical MRR;
- scoped-vs-broad regression deltas;
- Authority allowlist compliance;
- expected-Authority routing eligibility;
- frozen release article count;
- `UNMAPPED` all-READY-Pack fallback;
- IP + enterprise `CROSS_DOMAIN` Pack union without labor leakage;
- exact `as_of` trademark-version selection at the 2027-01-01 boundary.

Reproducibility guards:

- profile pins `three-domain-core@1.0.0` identity;
- Release Pack ID/version/domain/member metadata must equal the current READY routing catalog or execution fails closed;
- profile, promoted dataset, Stage 15 source fixture, Corpus Release and routing catalog are SHA-256 fingerprinted;
- public CI is lexical/deterministic only and never invokes paid/network DeepSeek or Kimi.

Direct deterministic metrics are exposed through:

```text
python -m app.public_regression_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage16b_three_domain_regression.json
```

Authoritative Stage 16.2 closeout head:

```text
67407e54b27e595e82119b055774241ce708b971
```

Final Stage 16.2 validation:

```text
Law-Rag Stage 16 CI #50
run 32459347103
SUCCESS

backend pytest
434 passed, 5 skipped, 1 third-party warning

historical Stage 11B public quality gates
PASS

Stage 16.2 direct three-domain regression
10 / 10 gates PASS
no diagnostics

expanded Stage 16b evaluation suite
3 / 3 entries PASS

frontend production build
PASS
```

Measured values on the named nine-case public dataset:

```text
scoped lexical Recall@5                         1.00
scoped lexical MRR                              1.00
broad lexical Recall@5                          1.00
broad lexical MRR                               1.00
scoped Recall@5 - broad Recall@5                0.00
scoped MRR - broad MRR                          0.00
scoped candidate Authority compliance           1.00
expected Authority routing eligibility          1.00
frozen Corpus Release article count             1274
UNMAPPED broad fallback preserved               1.00
CROSS_DOMAIN Pack union preserved               1.00
trademark as_of version-boundary exact rate     1.00
```

These are **scoped deterministic regression results for this named public dataset**, not a claim that Law-Rag has 100% legal correctness, professional audit accuracy, or production recall over Chinese law.

Draft PR #16 is the validation-only Stage 16.2 carrier and is not authorized for merge.

## Stage 16.3 — Private expert benchmark protocol + scoped professional metrics — COMPLETE

Stage 16.3 adds the evaluation machinery needed to use professionally labeled private truth without committing private contracts or reviewer labels to this public repository.

Implemented private artifact model:

```text
ExpertBenchmarkProtocol
  + private BenchmarkDataset
  + private BenchmarkObservationSet
  + ExpertLabelAuditArtifact
  -> ExpertBenchmarkRunReport
```

All four inputs must remain external or under ignored `benchmark_private/`. Every expert benchmark case must use `PRIVATE_EXTERNAL` provenance. Tracked repository paths fail closed.

### Expert truth controls

Every case receives exactly one audited label state:

```text
AGREED
ADJUDICATED
AMBIGUOUS
```

Rules include:

- protocol minimum reviewer count is at least 2;
- `AGREED` cannot carry an adjudicator;
- `ADJUDICATED` requires at least one adjudicator;
- `AMBIGUOUS` stays visible and is excluded from performance scoring rather than silently coerced into a label;
- Dataset, Observation Set and label audit must cover exactly the same case IDs and case versions;
- selective omission of difficult/failed cases is rejected.

Each audit record is bound to the current expected truth by a canonical SHA-256 `label_fingerprint` over case identity/version and complete expectations. If expected truth changes after review, the old expert audit becomes stale and execution fails closed.

### Professional metric semantics

Initial supported metric families are deliberately narrow:

```text
BINARY_CLASSIFICATION
  -> TP / FP / FN / TN
  -> precision / recall / F1

SET_EXTRACTION
  -> TP / FP / FN
  -> precision / recall / F1
```

Binary metrics require explicit positive/negative classes and at least one usable expert-positive and expert-negative case. Set metrics require exhaustive `SET_EQUALS` truth; partial `SET_CONTAINS` labels cannot be treated as complete gold truth.

Every metric is scoped by protocol ID/version, private dataset ID/version, assertion ID and optional task/tag filters. There is no cross-task professional `legal_accuracy` or `overall_accuracy` number.

### Label-quality evidence

The sanitized aggregate report records both system metrics and expert-label quality:

```text
total / agreed / adjudicated / ambiguous / usable case counts
agreement_rate
adjudication_rate
ambiguity_rate
usable_rate
minimum reviewer count required / observed
```

These label-quality values must be read alongside system precision/recall/F1. A model score without the underlying expert-truth quality context is not treated as sufficient professional evidence.

### Privacy-safe report + CLI

The report contains protocol/dataset identity, aggregate label-quality counts/rates, scoped metrics and SHA-256 fingerprints for protocol/dataset/observations/label audit. It omits private case IDs, contract text, expected labels, per-case observed values, reviewer identities and raw provider payloads.

CLI:

```text
python -m app.expert_benchmark_cli \
  --repo-root .. \
  --protocol <external-or-benchmark_private/protocol.json>
```

The evaluator consumes an existing Observation Set and never calls DeepSeek/Kimi itself.

### Validation

Public pytest uses only synthetic temporary private fixtures to attack the protocol mechanics. It does **not** represent professional expert data.

Validated implementation head:

```text
3393caa150e2baee459ca0969e8f17ee451d6156
```

Validation:

```text
Law-Rag Stage 16 CI #62
run 32460155009
SUCCESS

backend pytest
443 passed, 5 skipped, 1 third-party warning

historical Stage 11B public quality gates
PASS

Stage 16.2 direct public regression
PASS

Stage 16b public evaluation suite
PASS

frontend production build
PASS
```

The new regression set covers successful aggregate metrics plus fail-closed behavior for tracked paths, non-private provenance, Observation/Audit case omission, insufficient reviewers, stale label fingerprints, partial set truth and degenerate one-class binary truth.

**Important evidence boundary:** no real professionally labeled dataset has been added or executed in this repository. Therefore Stage 16.3 completion means the private expert **protocol/evaluator infrastructure is validated**; it does **not** mean Law-Rag currently has a measured professional audit accuracy, high-risk recall, citation relevance score or release threshold.

Draft PR #17 is the validation-only Stage 16.3 carrier:

```text
head: stage16-3-private-expert-benchmark
base: stage16-2-public-regression-corpus
```

PR #17 is not authorized for merge.

## Stage 16.4 — Real-provider ISSUE_V1 UAT observation capture — IN PROGRESS / READY_FOR_REAL_UAT

### Goal

Capture explicit, reproducible **real DeepSeek/Kimi observations** from the current production `ISSUE_V1` path without confusing provider behavior with expert truth or deterministic regression.

### Provider-free capture mechanics — VALIDATED

Stage 16.4 now provides a bounded, read-only capture path over an already-executed production `ISSUE_V1` job:

```text
existing production ISSUE_V1 artifacts
 -> validate job/run/fingerprint/Issue/stage-state provenance
 -> private IssueV1UATObservation
 -> sanitized IssueV1UATSanitizedReport
 -> optional REAL_PROVIDER_UAT / UAT_CAPTURE evaluation-suite entry
```

Implemented boundaries:

- the capture reader never invokes Audit Planner, DeepSeek, Kimi, OCR or another provider/network boundary;
- detailed observations may live only outside Git or under ignored `benchmark_private/` and are append-only;
- `TEST_DOUBLE` and `REAL_PROVIDER` capture modes remain explicit;
- `REAL_PROVIDER` requires explicit operator confirmation and rejects fake/test/stub/mock/double/dummy provider/model identities;
- current real-provider identity mapping is Planner/Primary -> DeepSeek and Secondary -> Kimi;
- canonical job identity, `as_of`, semantic mode, contract source/content fingerprints and AuditPlan schema/planner version must reconcile;
- Legal Context must cover exactly the AuditPlan Issue set;
- Primary, Secondary and final comparison counts/Issue identities must reconcile with the AuditPlan;
- AuditPlan -> Legal Context -> Primary -> Secondary -> final report fingerprint links are validated;
- provider-call Issue identity, raw-response SHA-256 and persisted-result linkage are validated;
- pipeline stage records must agree with COMPLETE / PRIMARY_INTERRUPTED / SECONDARY_INTERRUPTED artifact states;
- contradictory or stale provenance fails closed rather than being normalized;
- sanitized output omits job IDs, Issue IDs, request IDs, raw-response hashes, private text, credentials and hidden reasoning;
- Stage 16 evaluation suites now have a dedicated `UAT_CAPTURE` entry valid only in `REAL_PROVIDER_UAT` suites;
- `UAT_CAPTURE passed=true` means only that a captured production provider chain reached COMPLETE with consistent provenance; it does not mean legal correctness.

CLI capture of an already-executed real job:

```text
python -m app.uat_capture_cli \
  --repo-root .. \
  --job-id <existing-issue-v1-job-uuid> \
  --output <external-or-benchmark_private/observation.json> \
  --mode REAL_PROVIDER \
  --confirm-real-provider-uat
```

The confirmation flag does not itself call a provider. It only permits an already-persisted provider run to be labeled/captured as explicit real-provider UAT evidence after all guards pass.

Detailed operating procedure: `docs/REAL_PROVIDER_UAT.md`.

### Provider-free validation baseline

Validated provider-free implementation head:

```text
1775eb2fef049835cb29160d128a004e5ba75f2e
```

Validation:

```text
Law-Rag Stage 16 CI #104
run 32463233240
SUCCESS

backend pytest
466 passed, 5 skipped, 1 third-party warning

historical Stage 11B public quality gates
PASS

Stage 16.2 direct public regression
PASS

Stage 16b public evaluation suite
PASS

frontend production build
PASS
```

The regression set covers successful complete capture, Primary/Secondary interrupted checkpoints, private/sanitized boundaries, append-only behavior, explicit real-provider opt-in, fake-provider rejection, stale fingerprints, `as_of`/semantic mismatch, legacy-stage rejection, Issue coverage mismatch, observation tamper detection, pipeline/artifact stage-state contradictions, CLI confirmation forwarding, and `UAT_CAPTURE` evaluation-suite integration.

Public CI remains provider-free. Synthetic `REAL_PROVIDER`-shaped test fixtures exercise schema/evidence isolation only and are **not** real UAT observations.

### Remaining Stage 16.4 closure action — explicit real-provider run

No paid/network DeepSeek/Kimi UAT has been executed as part of this stage yet.

The remaining closure action is an explicitly authorized production `ISSUE_V1` run against a bounded selected UAT contract, followed by private capture through the validated reader. That action may transmit the selected contract evidence to configured DeepSeek/Kimi APIs and may incur provider cost, so it must not be inferred from ordinary development instructions or executed by CI.

Until such an explicit real-provider run is authorized, executed and captured, Stage 16.4 remains **IN PROGRESS / READY_FOR_REAL_UAT**, not `COMPLETE`.

### Non-goals for 16.4

Do not yet:

- reinterpret provider UAT as professional correctness;
- invent release thresholds from a tiny UAT sample;
- tune prompts merely to improve one UAT run;
- redesign `ISSUE_V1`;
- begin Stage 16.5 or Stage 17+.

Draft PR #18 is the stacked Stage 16.4 validation carrier:

```text
head: stage16-4-real-provider-uat
base: stage16-3-private-expert-benchmark
```

PR #18 remains Draft and is not authorized for merge.

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
- public/private/UAT evaluation separation;
- no credentials, private contracts, private reviewer labels or raw private provider payloads in Git.

## Deferred after Stage 16

```text
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 16.1–16.3 are COMPLETE. Stage 16.4 provider-free capture/evaluation mechanics are VALIDATED and READY_FOR_REAL_UAT, but actual paid/network UAT is NOT RUN. Stage 16.4 remains the only active scope. Do not begin Stage 16.5+, Stage 17+, or merge Draft PR #13/#14/#15/#16/#17/#18 without separate authorization.**
