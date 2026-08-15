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

The existing Stage 7 `legal_data/fixtures/retrieval_benchmark.json` remains the current retrieval-specific regression benchmark. Stage 11A does not silently redefine or replace its existing Recall@5/MRR gate.

## 8. Stage 11B metric layer

Stage 11B adds a separate typed quality layer with evaluator version `stage11b-1.0.0`.

Reusable deterministic metric helpers currently support:

```text
binary classification
  -> TP / FP / FN / TN
  -> precision / recall / F1

set extraction / Evidence-ID recovery
  -> micro TP / FP / FN
  -> precision / recall / F1

ranked retrieval
  -> Recall@K
  -> MRR
  -> explicit-citation exact-hit rate
```

These functions are infrastructure. Merely having a precision/recall function does not create a valid audit-accuracy claim. A metric is reportable only when its named dataset/version contains appropriate labels.

This distinction matters for future expert evaluation. A private professionally labeled contract set can use the same metric functions from an ignored local path, while the public repository continues to expose only repository-safe results.

## 9. Public deterministic CI profile

The checked-in gate profile is:

```text
benchmarks/public/stage11b_quality_gates.json
```

Normal backend CI now has a dedicated step:

```text
Run public deterministic quality gates
```

It is separate from pytest. The quality runner rebuilds the checked-in legal seed and lexical retrieval index in a temporary directory and executes the current code against the named public retrieval benchmark. No DeepSeek/Kimi call or secret is required.

Current public gates are:

```text
schema-smoke case pass rate        = 1.00
schema-smoke assertion pass rate   = 1.00
schema task-family coverage        = 9
retrieval Recall@5                 >= 0.90
retrieval MRR                      >= 0.80
explicit citation exact-hit rate   = 1.00
```

The retrieval thresholds intentionally preserve the Stage 7 regression contract. The exact-citation gate covers only explicit-article cases actually present in that named benchmark.

A quality gate fails closed if its metric is missing. Thresholds must not be silently lowered or labels changed merely to restore green CI.

## 10. Stage 11B diagnostics

`QualityRunReport` contains:

- metric key/value;
- dataset ID/version;
- numerator/denominator where meaningful;
- explicit scope text;
- gate threshold/operator/observed value;
- per-case diagnostics for retrieval misses or exact-citation failures;
- warnings that public metrics are scoped regression evidence rather than general legal accuracy.

For a retrieval miss, diagnostics preserve the case ID, expected Legal Evidence IDs and observed ranked IDs. For benchmark assertion failures, Stage 11A continues to preserve expected/observed values and reason codes.

The quality layer never stores hidden model reasoning.

## 11. Running the evaluators

From `backend/`, Stage 11A evaluator:

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

Stage 11B public quality profile:

```text
python -m app.quality_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage11b_quality_gates.json
```

Private expert benchmarks can use external ignored paths. Their results must identify their own dataset/version and must not be copied into the public repository unless independently safe for public release.

## 12. Interpretation rule

A metric must always be read together with its scope.

For example, a perfect result on the current 10-case public retrieval benchmark means only that the current code retrieved the expected evidence on those 10 checked-in cases. It does **not** establish full Chinese-law retrieval recall, legal correctness, model risk precision, or production readiness.

Stage 11C runtime hardening begins only after these measurement boundaries are explicit and the deterministic public gate is reproducible.
