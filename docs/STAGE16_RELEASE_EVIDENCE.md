# Stage 16.5 — Release-Quality Evidence Matrix

## Purpose

Stage 16.5 assembles the Stage 16 evidence classes into one deterministic, privacy-safe matrix without changing the production `ISSUE_V1` pipeline and without inventing a cross-task legal-accuracy score.

The matrix keeps these evidence classes separate:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

It answers whether the required evidence artifacts are available and structurally usable. It does **not** decide that Law-Rag is legally correct in all cases, and it does not create an unstated professional release threshold.

## Status semantics

Each evidence class receives one of:

```text
PASS
PRESENT
PENDING
FAIL
```

Current meaning:

- `PUBLIC_REGRESSION = PASS` means the pinned Stage 16b deterministic evaluation suite passed.
- `PRIVATE_EXPERT = PRESENT` means a sanitized real private expert report exists outside tracked Git paths and contains usable scoped metrics.
- `PRIVATE_EXPERT = PENDING` means no real private expert report was supplied to this matrix run.
- `REAL_PROVIDER_UAT = PASS` means a private Stage 16.4 `UAT_CAPTURE` suite validated a complete real-provider `ISSUE_V1` chain.
- `REAL_PROVIDER_UAT = PENDING` means no real-provider UAT suite was supplied.
- `FAIL` preserves a present but structurally unusable or incomplete evidence state.

Synthetic pytest fixtures never become `PRIVATE_EXPERT` or `REAL_PROVIDER_UAT` evidence.

## Two independent completion flags

The report deliberately distinguishes:

```text
engineering_ready
stage16_evidence_complete
```

`engineering_ready=true` means the pinned public deterministic Stage 16 suite passed. This is suitable for ordinary CI and allows external/private evidence to remain `PENDING`.

`stage16_evidence_complete=true` requires:

```text
PUBLIC_REGRESSION = PASS
PRIVATE_EXPERT    = PRESENT
REAL_PROVIDER_UAT = PASS
```

Even then, the flag means Stage 16 evidence assembly is complete; it is not automatic product release authorization.

## Pinned public evidence

Stage 16.5 accepts only:

```text
suite_id      law-rag-stage16-public-evaluation
suite_version 1.1.0
```

from:

```text
benchmarks/public/stage16b_evaluation_suite.json
```

This preserves the existing Stage 11A/11B and Stage 16.2 deterministic regression semantics.

## Private expert evidence

A supplied expert report must be:

- external to the repository, or under ignored `benchmark_private/`;
- valid `ExpertBenchmarkRunReport` JSON;
- backed by valid SHA-256 source fingerprints;
- non-empty in usable expert cases and scoped metric evidence.

The release matrix records only the expert report file SHA-256 and generic status. It does not copy protocol IDs, dataset IDs, case IDs, labels or reviewer identities into its output.

No new precision/recall/F1 threshold is created by Stage 16.5. The scoped metrics remain evidence for professional review, not a hidden global pass/fail rule.

## Real-provider UAT evidence

A supplied UAT suite must:

- be external or under ignored `benchmark_private/`;
- use `suite_class = REAL_PROVIDER_UAT`;
- contain only Stage 16.4 `UAT_CAPTURE` entries;
- preserve `architecture = ISSUE_V1`;
- pass the existing Stage 16.4 provider/artifact/fingerprint/coverage checks.

A complete provider chain is not treated as professional correctness. It proves only that the captured production provider path completed with valid provenance.

## CLI

From `backend/`, ordinary provider-free engineering validation is:

```text
python -m app.release_evidence_cli --repo-root ..
```

Expected before external evidence is supplied:

```text
engineering_ready        true
stage16_evidence_complete false
PRIVATE_EXPERT            PENDING
REAL_PROVIDER_UAT         PENDING
```

After the external evidence exists, final Stage 16 evidence closure is:

```text
python -m app.release_evidence_cli \
  --repo-root .. \
  --expert-report <external-or-benchmark_private/expert-report.json> \
  --uat-suite <external-or-benchmark_private/uat-suite.json> \
  --require-complete-evidence
```

`--require-complete-evidence` exits non-zero unless all three evidence classes satisfy the matrix requirements.

## Provider boundary

The Stage 16.5 runner never invokes:

```text
DeepSeek
Kimi
OCR
another paid/network model provider
```

It consumes existing artifacts only. Real provider execution remains a separate explicit action under the production provider approval/cancellation boundary.

## CI role

Stage 16 CI runs the matrix in provider-free mode after:

1. backend pytest;
2. historical Stage 11B public quality gates;
3. Stage 16.2 direct three-domain regression;
4. Stage 16b public evaluation suite.

The matrix CI step must pass while external evidence remains explicitly `PENDING`. This allows remaining engineering work to continue without relabeling missing external evidence as complete.

## Evidence boundary

The matrix intentionally does not emit fields named or equivalent to:

```text
overall_accuracy
legal_accuracy
global professional score
automatic release authorization
```

Stage 16 evidence classes remain independently interpretable and independently auditable.
