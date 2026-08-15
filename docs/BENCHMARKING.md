# Benchmarking and Evaluation

Stage 11 measures Law-Rag by layer before release hardening or Windows packaging. The benchmark system is deliberately evidence-aware and does not collapse unrelated tasks into one number.

## 1. Stage 11A architecture

```text
versioned BenchmarkDataset
        +
versioned BenchmarkObservationSet
        ↓
deterministic Stage 11A evaluator
        ↓
BenchmarkRunReport
  ├─ per-task summaries
  ├─ per-case pass/fail
  └─ assertion-level expected / observed / reason
```

The current schema is `1.0.0`; evaluator version is `stage11a-1.0.0`.

`BenchmarkDataset` describes expected behavior. `BenchmarkObservationSet` records what a particular producer/run actually returned. The evaluator compares them deterministically and never calls DeepSeek, Kimi, OCR, RAG or another model/provider by itself.

## 2. Task separation

The schema represents these task families independently:

```text
OCR
CANONICAL_STRUCTURE
DETERMINISTIC_RULE
LEGAL_RETRIEVAL
LEGAL_CITATION_VALIDITY
CONTRACT_EVIDENCE_LOCALIZATION
PRIMARY_AUDIT_FINDING
SECONDARY_REVIEW
HUMAN_REVIEW_INTEGRITY
```

This separation is intentional. A retrieval hit, a valid citation, a correctly localized Contract Evidence span, and a correct model finding are different claims and must remain separately measurable.

Stage 11A therefore exposes `all_cases_passed` only as a harness/smoke status. It does **not** expose `overall_accuracy` or `legal_accuracy`. Precision/recall/F1, high-risk recall and regression thresholds belong to Stage 11B and must be scoped to a named dataset/version.

## 3. Case identity and provenance

Each case records:

- stable `case_id` and `case_version`;
- `fixture_id`;
- task type;
- title/tags;
- provenance data class;
- source name/URI where safe;
- explicit benchmark scope;
- one or more versioned expectations.

Allowed provenance classes:

```text
PUBLIC_SYNTHETIC
PUBLIC_LEGAL
PRIVATE_EXTERNAL
```

`PRIVATE_EXTERNAL` describes local evaluation data and does not authorize committing it. Repository policy in `docs/DATA_POLICY.md` still governs what may enter Git.

## 4. Expectations

Expectations use JSON Pointer so benchmark assertions can target nested structured output without defining a new evaluator for every field.

Supported Stage 11A comparison modes:

- `EXACT`
- `ONE_OF`
- `SET_EQUALS`
- `SET_CONTAINS`
- `NUMERIC_WITHIN`
- `NORMALIZED_TEXT_EQUALS`

`NUMERIC_WITHIN` requires an explicit non-negative tolerance. `ONE_OF` represents genuine allowed alternatives instead of silently accepting arbitrary output. Set comparisons are order-insensitive. Normalized text comparison uses Unicode NFKC plus whitespace folding and should be used only where that normalization is appropriate to the task.

## 5. Observations and producer metadata

An observation records:

- case ID/version;
- structured `observed` payload;
- producer ID/version;
- optional provider/model metadata;
- optional artifact fingerprint.

Provider/model fields are metadata only. The evaluator does not invoke providers and does not treat a model name as evidence of correctness.

Dataset identity/version mismatch is a hard evaluation error. Missing observations, case-version mismatches and missing JSON Pointer targets become explicit failed cases rather than disappearing from the denominator.

## 6. Failure diagnostics

Every failed assertion keeps safe structured diagnostics:

```text
assertion ID
JSON Pointer
comparison mode
expected value
observed value
reason code
```

Representative reason codes include:

- `OBSERVED_POINTER_MISSING`
- `EXACT_MISMATCH`
- `NOT_IN_ALLOWED_ALTERNATIVES`
- `SET_MISMATCH`
- `EXPECTED_SET_NOT_CONTAINED`
- `OUTSIDE_TOLERANCE`
- `NORMALIZED_TEXT_MISMATCH`
- `MISSING_OBSERVATION`
- `CASE_VERSION_MISMATCH`

The framework does not store hidden model reasoning, API secrets or private contract payloads as benchmark diagnostics.

## 7. Public schema smoke

The checked-in `benchmarks/public/stage11a_schema_smoke.*.json` pair exercises all nine task types with fictional/public-safe values. It validates schema/evaluator mechanics only.

Passing it must never be reported as:

- OCR accuracy;
- full-corpus retrieval recall;
- legal correctness;
- audit precision/recall;
- professional benchmark performance;
- release readiness.

The existing Stage 7 `legal_data/fixtures/retrieval_benchmark.json` remains the current retrieval-specific regression benchmark. Stage 11A does not silently redefine or replace its existing Recall@5/MRR gate. Later Stage 11B work may adapt or extend those measurements through the common schema only after metric semantics and thresholds are documented.

## 8. Running the evaluator

From `backend/`:

```text
python -m app.benchmark_cli \
  --dataset ../benchmarks/public/stage11a_schema_smoke.dataset.json \
  --observations ../benchmarks/public/stage11a_schema_smoke.observations.json
```

Optional JSON report output:

```text
python -m app.benchmark_cli \
  --dataset <dataset.json> \
  --observations <observations.json> \
  --output <report.json>
```

Exit codes:

```text
0 = every benchmark case passed
1 = at least one case failed
2 = dataset/observation input could not be loaded or validated
```

Private expert benchmarks can use an external local path such as ignored `benchmark_private/`; they do not need to be copied into the repository.
