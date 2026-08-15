# Law-Rag Benchmarks

This directory contains **repository-safe public benchmark definitions only**.

## What may be committed

Allowed benchmark material:

- fully fictional/synthetic contracts and expected labels;
- synthetic OCR/layout fixtures created for Law-Rag;
- verified public legal evidence already permitted by `docs/DATA_POLICY.md`;
- non-sensitive expected IDs, structured values and evaluator metadata.

Do not commit real contracts, private reviewer labels, private benchmark observations, customer data, runtime artifacts, logs, API keys, model caches or private databases.

Private/professional evaluation data should remain outside Git, for example under ignored `benchmark_private/`, and can be passed to the evaluator with an explicit local path.

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

Reusable metric helpers now support:

- binary classification precision / recall / F1;
- micro-averaged set extraction precision / recall / F1;
- ranking Recall@K / MRR;
- explicit-citation exact-hit rate;
- versioned threshold profiles with `GTE`, `LTE`, and `EQ` operators;
- case-level structured failure diagnostics.

The checked-in gate profile is:

```text
public/stage11b_quality_gates.json
```

Normal CI rebuilds the public legal seed and FTS5 retrieval index, then runs the named public retrieval benchmark against the current code. Current deterministic gates are deliberately narrow:

```text
Stage 11A schema-smoke case pass rate       = 1.00
Stage 11A schema-smoke assertion pass rate  = 1.00
represented benchmark task families         = 9
public retrieval Recall@5                   >= 0.90
public retrieval MRR                        >= 0.80
explicit-article exact-hit rate              = 1.00
```

These are regression gates for the named repository-safe fixtures only. In particular, the 10-case retrieval dataset covers the current `CURATED_EXCERPT` legal seed; its score must never be described as general legal recall or production legal accuracy.

Precision/recall/F1 helpers are available for future labeled audit/OCR/extraction datasets, including private expert benchmarks, but no public audit-finding precision/recall claim is made until such a labeled dataset actually exists.

## CLIs

From `backend/`, Stage 11A evaluator:

```text
python -m app.benchmark_cli \
  --dataset ../benchmarks/public/stage11a_schema_smoke.dataset.json \
  --observations ../benchmarks/public/stage11a_schema_smoke.observations.json
```

Stage 11B public quality gates:

```text
python -m app.quality_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage11b_quality_gates.json
```

For private local evaluation, point benchmark dataset/observation inputs to external ignored paths. Private labels do not need to enter the repository or normal CI.
