# Law-Rag Benchmarks

This directory contains **repository-safe public benchmark definitions only**.

## What may be committed

Allowed benchmark material:

- fully fictional/synthetic contracts and expected labels;
- synthetic OCR/layout fixtures created for Law-Rag;
- verified public legal evidence already permitted by `docs/DATA_POLICY.md`;
- non-sensitive expected IDs, structured values and evaluator metadata;
- public Stage 16 evaluation-suite/regression manifests that reference only repository-safe public inputs;
- schemas, documentation and synthetic tests for private expert/UAT evaluation mechanics.

Do not commit real contracts, private reviewer labels, private benchmark observations, customer data, runtime artifacts, logs, API keys, model caches or private databases.

Private/professional evaluation data must remain outside Git or under ignored `benchmark_private/`.

## Stage 11A format

Stage 11A separates three concepts:

```text
BenchmarkDataset
  = what should be true

BenchmarkObservationSet
  = what one system/run actually produced

BenchmarkRunReport
  = deterministic comparison + diagnostics
```

The schema version is `1.0.0`. The evaluator version is `stage11a-1.0.0`.

Supported task types are deliberately separate:

- `OCR`
- `CANONICAL_STRUCTURE`
- `DETERMINISTIC_RULE`
- `LEGAL_RETRIEVAL`
- `LEGAL_CITATION_VALIDITY`
- `CONTRACT_EVIDENCE_LOCALIZATION`
- `PRIMARY_AUDIT_FINDING`
- `SECONDARY_REVIEW`
- `HUMAN_REVIEW_INTEGRITY`

The framework does **not** compute one aggregate "legal accuracy" score.

## Public schema smoke

`public/stage11a_schema_smoke.dataset.json` and its matching observation file exist only to exercise the schema/evaluator across all task types. Passing this smoke means the evaluation mechanics work; it does not establish product OCR quality, retrieval recall, legal accuracy, model precision/recall, or release readiness.

## Stage 11B quality metrics and CI gates

Stage 11B adds a separate quality layer with evaluator version `stage11b-1.0.0`.

Reusable metric helpers support:

- binary classification precision / recall / F1;
- micro-averaged set extraction precision / recall / F1;
- ranking Recall@K / MRR;
- explicit-citation exact-hit rate;
- versioned threshold profiles with `GTE`, `LTE`, and `EQ` operators;
- case-level structured failure diagnostics.

The historical checked-in gate profile is:

```text
public/stage11b_quality_gates.json
```

Normal CI rebuilds the public curated legal seed and FTS5 retrieval index, then runs the named public retrieval benchmark. These historical gates remain unchanged:

```text
Stage 11A schema-smoke case pass rate       = 1.00
Stage 11A schema-smoke assertion pass rate  = 1.00
represented benchmark task families         = 9
public retrieval Recall@5                   >= 0.90
public retrieval MRR                        >= 0.80
explicit-article exact-hit rate              = 1.00
```

They are regression gates for the named repository-safe fixtures only. In particular, the 10-case retrieval dataset covers the historical `CURATED_EXCERPT` seed; its score must never be described as general legal recall or production legal accuracy.

## Stage 16 evaluation evidence classes

Stage 16 keeps three evidence classes explicit:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

They are intentionally not mixed into one overall score.

### Public regression

Stage 16 adds orchestration above the historical evaluators:

```text
EvaluationSuiteManifest
  -> BenchmarkDataset + BenchmarkObservationSet
       -> Stage 11A evaluator
  OR
  -> public QualityGateProfile
       -> Stage 11B evaluator
  OR
  -> public deterministic regression profile
       -> Stage 16 evaluator
  -> sanitized EvaluationSuiteRunReport
```

Suite schema version remains `1.0.0`. The active public suite evaluator version after Stage 16.2 is `stage16b-1.0.0`.

`public/stage16a_evaluation_suite.json` remains unchanged as the historical 16.1 orchestration smoke.

Stage 16.2 adds:

```text
public/stage16b_three_domain_retrieval.dataset.json
public/stage16b_three_domain_regression.json
public/stage16b_evaluation_suite.json
```

The dataset promotes the nine cases from:

```text
legal_data/fixtures/stage15_domain_retrieval_benchmark.json
```

without changing their expected Authority identities. The runner compares the promoted dataset against the Stage 15 fixture semantically and fails closed if they diverge.

The Stage 16.2 profile pins:

```text
Corpus Release: three-domain-core@1.0.0
Articles:       1274
```

It also requires the selected Release Pack ID/version/domain/member catalog to match the current READY routing catalog.

Final Stage 16.2 values on the named nine-case dataset were:

```text
scoped Recall@5                  1.00
scoped MRR                       1.00
broad Recall@5                   1.00
broad MRR                        1.00
scoped-broad Recall delta        0.00
scoped-broad MRR delta           0.00
all remaining invariant rates    1.00
article count                    1274
```

These numbers mean only that the current deterministic code passes the named public regression evidence. They are **not** professional legal correctness, audit accuracy, or full Chinese-law retrieval coverage.

### Private expert — Stage 16.3

Stage 16.3 defines a separate private expert protocol/evaluator:

```text
ExpertBenchmarkProtocol
  + private BenchmarkDataset
  + private BenchmarkObservationSet
  + ExpertLabelAuditArtifact
  -> sanitized ExpertBenchmarkRunReport
```

The protocol/dataset/observations/label audit must stay external or under ignored `benchmark_private/`. Every case must use `PRIVATE_EXTERNAL` provenance. Tracked repository paths are rejected.

Expert label states are:

```text
AGREED
ADJUDICATED
AMBIGUOUS
```

Each label audit is SHA-256 bound to the case's current expected truth. If the expected labels change after expert review, the old audit fingerprint becomes stale and evaluation fails closed.

The evaluator also requires exact Dataset/Observation/Audit case coverage and case-version alignment, so difficult or failed cases cannot be silently removed from a scored run.

Initial professional metric types are:

```text
BINARY_CLASSIFICATION
  TP / FP / FN / TN
  precision / recall / F1

SET_EXTRACTION
  TP / FP / FN
  precision / recall / F1
```

Binary metrics require both expert-positive and expert-negative usable truth. Set metrics require exhaustive `SET_EQUALS` labels; partial `SET_CONTAINS` gold sets are rejected for precision/recall/F1.

The sanitized report records label-quality context alongside system metrics:

```text
agreed / adjudicated / ambiguous / usable counts
agreement_rate
adjudication_rate
ambiguity_rate
usable_rate
reviewer-count bounds
```

`AMBIGUOUS` cases remain visible in those counts/rates and are excluded from performance scoring rather than silently relabeled.

No real expert dataset or professional metric value is checked into this repository. Synthetic pytest fixtures validate evaluator mechanics only.

### Real-provider UAT

`REAL_PROVIDER_UAT` suite manifests and Observation Sets must also be external/ignored. Every UAT observation must identify a current real provider/model and SHA-256 artifact fingerprint. Fake provider/producer identities are invalid UAT evidence.

Stage 16.4 will add explicit opt-in capture from the current production `ISSUE_V1` path. Actual paid/network calls must never run in ordinary public CI.

## CLIs

From `backend/`, Stage 11A evaluator:

```text
python -m app.benchmark_cli \
  --dataset ../benchmarks/public/stage11a_schema_smoke.dataset.json \
  --observations ../benchmarks/public/stage11a_schema_smoke.observations.json
```

Historical Stage 11B public quality gates:

```text
python -m app.quality_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage11b_quality_gates.json
```

Stage 16.2 direct public regression report:

```text
python -m app.public_regression_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage16b_three_domain_regression.json
```

Expanded Stage 16 public suite:

```text
python -m app.evaluation_suite_cli \
  --repo-root .. \
  --suite ../benchmarks/public/stage16b_evaluation_suite.json
```

Stage 16.3 private expert evaluator:

```text
python -m app.expert_benchmark_cli \
  --repo-root .. \
  --protocol <external-or-benchmark_private/protocol.json>
```

Optional sanitized JSON output is supported by the Stage 16 CLIs. Private labels do not need to enter the repository or normal CI.
