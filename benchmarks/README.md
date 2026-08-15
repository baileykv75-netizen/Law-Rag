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

## CLI

From `backend/`:

```text
python -m app.benchmark_cli \
  --dataset ../benchmarks/public/stage11a_schema_smoke.dataset.json \
  --observations ../benchmarks/public/stage11a_schema_smoke.observations.json
```

For private local evaluation, point `--dataset` and/or `--observations` to external ignored paths. The evaluator has no requirement that benchmark files live inside the repository.
