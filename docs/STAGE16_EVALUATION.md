# Stage 16 Evaluation Architecture

## Purpose

Stage 16 measures and hardens the proven Stage 13–15 production architecture. It does not introduce a second contract-analysis pipeline and does not let evaluation silently execute paid/network model providers.

The stage keeps three kinds of evidence separate:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

No cross-task `overall_accuracy` or `legal_accuracy` number is produced.

## Stage 16.1 — Evaluation-suite architecture — COMPLETE

Stage 16.1 added a versioned orchestration layer above the existing Stage 11 benchmark and quality evaluators:

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

The suite layer preserves the separation between truth, observations and evaluation.

### Evidence boundaries

`PUBLIC_REGRESSION` material lives under `benchmarks/public/` and cannot contain `PRIVATE_EXTERNAL` cases.

`PRIVATE_EXPERT` manifests/datasets/observations remain external or under ignored `benchmark_private/`; detailed expected/observed labels remain in that private boundary.

`REAL_PROVIDER_UAT` manifests/observations also remain external/ignored. Every UAT observation identifies a current real provider, model and SHA-256 artifact fingerprint; fake producer/provider identities are rejected.

### Sanitized suite report

`EvaluationSuiteRunReport` records identity, version, pass/fail counts, evaluator versions and source fingerprints. It intentionally omits private labels, assertion payloads, contract text, raw provider responses, hidden reasoning and credentials.

Historical Stage 16.1 smoke:

```text
benchmarks/public/stage16a_evaluation_suite.json
```

It remains unchanged and contains the Stage 11 schema smoke plus the historical Stage 11B public quality profile.

Final Stage 16.1 closeout validation:

```text
head 706ce85bc5b472896d33dcf4d926501755656247
Law-Rag Stage 16 CI #15 (32458037391)  SUCCESS
Law-Rag Stage 15 CI #130 (32458037327) SUCCESS
```

## Stage 16.2 — Public deterministic regression corpus — COMPLETE

Stage 16.2 promotes repository-safe deterministic evidence that previously lived mainly in Stage 15 pytest/fixtures into explicit versioned Stage 16 regression artifacts.

### Public artifacts

```text
benchmarks/public/stage16b_three_domain_retrieval.dataset.json
benchmarks/public/stage16b_three_domain_regression.json
benchmarks/public/stage16b_evaluation_suite.json
```

New backend layer:

```text
PublicRegressionProfile
  -> deterministic named runner
  -> QualityRunReport + source fingerprints
  -> PUBLIC_REGRESSION_PROFILE suite entry
```

The historical Stage 11B quality profile is not redefined. Stage 16.2 therefore adds a new evaluation layer without changing what older Stage 11 evidence meant.

### Promoted Stage 15 dataset

The nine Stage 16.2 cases are promoted from:

```text
legal_data/fixtures/stage15_domain_retrieval_benchmark.json
```

The promoted dataset contains the same case ID, topic, query, contract type, `as_of` date and expected Authority identity for every case. At runtime the runner compares the promoted dataset to the source fixture and fails closed on any semantic difference.

A future change to benchmark truth therefore requires an explicit new dataset/source version; it cannot be hidden under the same Stage 16.2 identity.

### Pinned corpus + routing reproducibility

The regression profile pins:

```text
Corpus Release: three-domain-core@1.0.0
3 READY Packs
14 Authorities
15 Versions
1274 unique Articles
```

The runner rebuilds a scratch legal database and FTS5 retrieval index from the selected immutable Corpus Release.

Before scoring, it also compares the Release Pack catalog with the current READY routing catalog using:

```text
pack_id
pack_version
domain_tags
authority_manifest_paths
```

A mismatch fails closed. This prevents an old release from being scored against silently changed Pack-routing metadata and reported as if it were directly comparable.

### Deterministic regression dimensions

The Stage 16.2 profile measures:

```text
three-domain scoped lexical Recall@5
three-domain scoped lexical MRR
three-domain broad lexical Recall@5
three-domain broad lexical MRR
scoped-vs-broad Recall/MRR deltas
scoped candidate Authority compliance
expected Authority route eligibility
frozen release Article count
UNMAPPED all-READY-Pack fallback
CROSS_DOMAIN IP + enterprise Pack union
trademark exact as_of version boundary
```

The trademark boundary explicitly verifies:

```text
2026-12-31 -> effective-2019-11-01
2027-01-01 -> effective-2027-01-01
```

### Stage 16.2 gates

```text
scoped Recall@5                              >= 0.90
scoped MRR                                   >= 0.80
scoped Recall@5 - broad Recall@5             >= 0.00
scoped MRR - broad MRR                       >= 0.00
Authority-scope compliance                    = 1.00
expected Authority routing eligibility        = 1.00
release article count                         = 1274
UNMAPPED broad fallback                       = 1.00
CROSS_DOMAIN Pack union                       = 1.00
trademark as_of version-boundary exact rate   = 1.00
```

### Direct report CLI

From `backend/`:

```text
python -m app.public_regression_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage16b_three_domain_regression.json
```

### Expanded suite

The Stage 16.2 suite is:

```text
benchmarks/public/stage16b_evaluation_suite.json
```

It contains:

1. unchanged Stage 11A schema smoke;
2. unchanged historical Stage 11B quality profile;
3. Stage 16.2 three-domain public regression profile.

The Stage 16.1 `stage16a` suite remains available as historical evidence.

### Final Stage 16.2 validation

```text
head 67407e54b27e595e82119b055774241ce708b971
Law-Rag Stage 16 CI #50 (32459347103) SUCCESS
backend pytest                            434 passed, 5 skipped, 1 warning
historical Stage 11B gates               PASS
Stage 16.2 direct regression gates       10 / 10 PASS
Stage 16b evaluation-suite entries       3 / 3 PASS
frontend production build                PASS
```

Direct metric values:

```text
scoped lexical Recall@5                         1.00
scoped lexical MRR                              1.00
broad lexical Recall@5                          1.00
broad lexical MRR                               1.00
scoped Recall@5 - broad Recall@5                0.00
scoped MRR - broad MRR                          0.00
scoped candidate Authority compliance           1.00
expected Authority routing eligibility          1.00
frozen release Article count                    1274
UNMAPPED broad fallback                         1.00
CROSS_DOMAIN Pack union                         1.00
trademark as_of version-boundary exact rate     1.00
```

These results apply only to the named nine-case public regression dataset and pinned corpus/routing configuration. They are **not** professional legal accuracy, audit-finding precision/recall, or full Chinese-law retrieval coverage.

## Stage 16.3 — Private expert benchmark — COMPLETE

Public deterministic evidence cannot establish whether legal/audit judgments are professionally correct. Stage 16.3 therefore adds the private expert-label protocol and deterministic professional metric evaluator while keeping the real labels outside the public repository.

### Private artifact boundary

```text
ExpertBenchmarkProtocol
  + BenchmarkDataset
  + BenchmarkObservationSet
  + ExpertLabelAuditArtifact
  -> ExpertBenchmarkRunReport
```

The protocol, dataset, observations and label audit must all be external or under ignored `benchmark_private/`. Tracked repository paths are rejected, and every private benchmark case must declare `PRIVATE_EXTERNAL` provenance.

The expert evaluator is a **companion professional metric layer** rather than a new production pipeline. It consumes existing observations and never calls DeepSeek/Kimi.

The Stage 16 `PRIVATE_EXPERT` suite class remains available for privacy-safe BenchmarkDataset/ObservationSet orchestration. Stage 16.3 does not add a threshold-bearing suite entry for `ExpertBenchmarkProtocol`, because the expert evaluator deliberately defines measurement semantics without inventing a release pass/fail threshold before real dataset quality is established.

### Label audit states

Each case has one explicit truth-audit state:

```text
AGREED
ADJUDICATED
AMBIGUOUS
```

Rules:

- protocol minimum reviewer count is at least 2;
- `AGREED` means no adjudicator was needed;
- `ADJUDICATED` requires at least one adjudicator;
- `AMBIGUOUS` means professional truth remains materially uncertain;
- `AMBIGUOUS` cases remain visible in label-quality denominators and are excluded from performance metrics rather than silently relabeled.

### Label fingerprint integrity

Every audit record stores a canonical SHA-256 `label_fingerprint` over:

```text
case_id
case_version
sorted complete expectations:
  assertion_id
  JSON pointer
  comparison mode
  expected value
  tolerance
```

Before scoring, the evaluator recomputes the fingerprint. Any post-review change to the expected truth invalidates the previous audit and fails closed.

Dataset, Observation Set and label audit must also cover exactly the same case IDs and case versions. Selective omission of difficult or failed cases is rejected.

### Initial professional metric families

Stage 16.3 supports only metric semantics that can be deterministically scored once professional truth exists.

```text
BINARY_CLASSIFICATION
  TP / FP / FN / TN
  precision / recall / F1

SET_EXTRACTION
  TP / FP / FN
  precision / recall / F1
```

Binary metrics require explicit disjoint positive/negative values and at least one usable expert-positive and expert-negative case. Degenerate one-class truth is rejected rather than producing misleading precision/recall.

Set metrics require exhaustive `SET_EQUALS` gold truth. A partial `SET_CONTAINS` label cannot be used for precision/recall/F1 because unknown valid extra items would otherwise be incorrectly counted as false positives.

Each metric records its exact protocol/dataset version, assertion definition, task filters/tags and human-readable scope. No cross-task professional global score is emitted.

### Label-quality summary

Professional performance metrics are accompanied by explicit expert-truth quality:

```text
total_case_count
agreed_case_count
adjudicated_case_count
ambiguous_case_count
usable_case_count
agreement_rate
adjudication_rate
ambiguity_rate
usable_rate
minimum_reviewer_count_required
minimum_reviewer_count_observed
```

These values describe the private truth set and must be reviewed alongside system precision/recall/F1.

### Sanitized professional report

`ExpertBenchmarkRunReport` includes only:

- evaluator/protocol/dataset identities and versions;
- aggregate label-quality counts/rates;
- scoped aggregate metric counts and precision/recall/F1;
- SHA-256 fingerprints of protocol, dataset, observations and label audit;
- explicit warnings/limitations.

It omits private case IDs, contract text, expected expert labels, per-case observed values, reviewer identities, raw provider responses, hidden reasoning and credentials.

### CLI

From `backend/`:

```text
python -m app.expert_benchmark_cli \
  --repo-root .. \
  --protocol <external-or-benchmark_private/protocol.json>
```

### Synthetic protocol regression

Public pytest may create synthetic files in temporary private directories solely to validate evaluator mechanics. Current regressions cover:

- valid aggregate binary/set scoring;
- visible `AMBIGUOUS` exclusion;
- tracked-path rejection;
- `PRIVATE_EXTERNAL` provenance enforcement;
- exact Observation/Audit case coverage;
- minimum reviewer count;
- stale label-fingerprint rejection;
- partial set-truth rejection;
- degenerate one-class binary-truth rejection.

Synthetic fixture values are **not professional Law-Rag accuracy evidence**.

### Validated Stage 16.3 implementation

```text
head 3393caa150e2baee459ca0969e8f17ee451d6156
Law-Rag Stage 16 CI #62 (32460155009) SUCCESS
backend pytest                            443 passed, 5 skipped, 1 warning
historical Stage 11B gates               PASS
Stage 16.2 direct public regression      PASS
Stage 16b public evaluation suite        PASS
frontend production build                PASS
```

No real professionally labeled benchmark was committed or executed. Consequently there is currently **no professional audit-accuracy/high-risk-recall/citation-relevance value and no expert-derived release threshold** to report. Stage 16.3 completion means the protocol/evaluator infrastructure is ready for real private expert data; it does not mean expert evaluation has already occurred.

Detailed policy: `docs/STAGE16_EXPERT_BENCHMARK.md`.

## Stage 16.4 — Real-provider ISSUE_V1 UAT — NEXT

Stage 16.4 owns explicit capture of current production DeepSeek/Kimi behavior under the existing `ISSUE_V1` provider boundary.

The capture path must:

- reuse the production Planner -> Issue Legal RAG -> DeepSeek -> Kimi -> deterministic comparison chain;
- require existing provider configuration and explicit approval/cancellation semantics;
- record provider/model identity and authoritative artifact/request SHA-256 fingerprints;
- preserve one-to-one AuditPlan Issue coverage and existing checkpoint/restart rules;
- keep detailed UAT observations external or under ignored private paths;
- emit only sanitized provenance/summary suitable for Stage 16 evidence assembly;
- never treat model agreement as professional correctness.

Normal public CI may test UAT-capture mechanics with provider doubles only. Actual paid/network calls are explicit opt-in and never part of ordinary CI.

Stage 16.4 remains separate from `PRIVATE_EXPERT`; expert truth and real-provider observations are different evidence classes.

## Remaining sequence

```text
16.4  real-provider ISSUE_V1 UAT observation capture
16.5  release-quality evidence matrix + final regression
```

Every substage must preserve the distinction between public deterministic regression, private expert truth and provider-specific UAT evidence.
