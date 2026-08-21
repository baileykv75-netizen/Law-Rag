# Stage 16 Evaluation Architecture

## Purpose

Stage 16 measures and hardens the Stage 13–15 production architecture. It does not introduce a second contract-analysis pipeline and does not let an evaluator call model providers on its own.

Stage 16.1 adds a versioned orchestration layer above the existing Stage 11 benchmark and quality evaluators.

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

The suite layer therefore preserves the original separation between **truth**, **observations**, and **evaluation**.

## Evidence classes

A suite has exactly one evidence class.

### PUBLIC_REGRESSION

Repository-safe deterministic regression evidence.

Rules:

- manifest must be under `benchmarks/public/`;
- benchmark dataset/observations must be under `benchmarks/public/`;
- a checked-in dataset cannot contain `PRIVATE_EXTERNAL` cases;
- public quality profiles are allowed only in this class;
- no provider secret or paid/network call is required.

A pass means only that the named checked-in regression evidence still passes.

### PRIVATE_EXPERT

Professionally labeled evaluation data.

Rules:

- manifest and benchmark inputs must be external or under ignored `benchmark_private/`;
- every benchmark case must declare `PRIVATE_EXTERNAL` provenance;
- detailed expected/observed labels stay in the private benchmark report boundary;
- the suite-level report contains summary counts and SHA-256 input fingerprints rather than assertion payloads.

This keeps professional reviewer truth useful for metrics without making it public repository material.

### REAL_PROVIDER_UAT

Explicit paid/network observations from the current production provider path.

Rules:

- suite manifest is external/ignored;
- Observation Sets are external/ignored;
- the dataset may reuse public-safe benchmark truth or private external truth;
- every observation must identify a non-fake provider and model;
- every observation must include a SHA-256 artifact fingerprint;
- the suite evaluator only consumes those observations and never creates them.

Real-provider execution itself belongs to a later Stage 16 substage. Keeping execution separate from scoring makes normal CI deterministic, secret-free, and network-independent.

## Sanitized suite report

`EvaluationSuiteRunReport` records:

- suite ID/version/class;
- suite-manifest fingerprint;
- per-entry pass/fail;
- underlying evaluator version;
- dataset/profile identity and version;
- number of cases or gates passed/failed;
- SHA-256 fingerprints of evaluation inputs;
- privacy-safe provider/model/artifact summaries for real-provider UAT.

It intentionally does **not** include:

- assertion expected/observed payloads;
- expert label text;
- contract text;
- raw provider responses;
- hidden model reasoning;
- credentials;
- a cross-task `overall_accuracy` or `legal_accuracy` score.

When deeper diagnostics are required, reviewers inspect the underlying benchmark/quality report inside the data boundary appropriate to that suite.

## Public Stage 16.1 smoke

The checked-in public orchestration smoke is:

```text
benchmarks/public/stage16a_evaluation_suite.json
```

It contains two entries:

1. existing Stage 11A nine-task schema smoke;
2. existing Stage 11B public deterministic quality profile.

This intentionally reuses existing evidence. Stage 16.1 proves orchestration and isolation only; corpus expansion and new quality claims belong to later Stage 16 substages.

Run from `backend/`:

```text
python -m app.evaluation_suite_cli \
  --repo-root .. \
  --suite ../benchmarks/public/stage16a_evaluation_suite.json
```

The CLI exits:

```text
0  all suite entries passed
1  valid suite executed but at least one entry failed
2  invalid suite/input/policy boundary
```

## Stage 16.1 non-goals

Stage 16.1 does not:

- call DeepSeek or Kimi;
- add expert labels;
- enlarge the legal corpus;
- tune retrieval thresholds;
- change ISSUE_V1 prompts or comparison semantics;
- change provider approval/cancellation;
- change Windows packaging;
- implement later desktop/history/export/installer work.

## Next Stage 16 sequence

After Stage 16.1 is validated:

```text
16.2  expand public deterministic regression corpus and integrate Stage 15 three-domain retrieval evidence
16.3  define/run private expert benchmark and scoped professional metrics
16.4  capture current ISSUE_V1 real-provider UAT observations under explicit opt-in
16.5  assemble the Stage 16 release-quality evidence matrix and final regression
```

Every substage must preserve the distinction between public regression evidence, private expert truth, and provider-specific UAT evidence.
