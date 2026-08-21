# Stage 16.3 Private Expert Benchmark Protocol

## Purpose

Stage 16.3 adds a **private, professionally labeled evaluation protocol** for Law-Rag behaviors that public deterministic regression cannot establish.

It does not change the production `ISSUE_V1` audit pipeline and it does not create a public expert-label dataset.

The evidence boundary remains:

```text
PUBLIC_REGRESSION
  checked-in repository-safe deterministic evidence

PRIVATE_EXPERT
  external / ignored professional truth + observations + label audit

REAL_PROVIDER_UAT
  explicit provider/model observations handled separately in Stage 16.4
```

These evidence classes must not be merged into one `legal_accuracy` or `overall_accuracy` score.

## Private file boundary

The following Stage 16.3 files must live either outside the repository or under ignored `benchmark_private/`:

```text
ExpertBenchmarkProtocol
BenchmarkDataset
BenchmarkObservationSet
ExpertLabelAuditArtifact
```

Every private expert `BenchmarkCase` must declare:

```text
data_class = PRIVATE_EXTERNAL
```

Tracked repository paths are rejected by the expert benchmark runner.

Public Git may contain only:

- schemas and runner code;
- protocol documentation;
- synthetic tests of the evaluation mechanics;
- sanitized aggregate evidence that cannot reconstruct private cases, contracts or expert labels.

## Expert label lifecycle

Each private case has one label-audit record with one of three states:

```text
AGREED
  minimum reviewer count met and no adjudicator was needed

ADJUDICATED
  reviewer disagreement was resolved with at least one adjudicator

AMBIGUOUS
  professional truth remains materially uncertain
```

`AMBIGUOUS` is not silently converted into a positive or negative label. It remains visible in label-quality counts and is excluded from professional performance metrics.

### Label fingerprint

Every label-audit record contains a SHA-256 `label_fingerprint` calculated from the case identity/version plus its complete benchmark expectations.

```text
case identity/version
+ sorted assertion IDs
+ pointer
+ comparison mode
+ expected value
+ tolerance
= canonical JSON
= SHA-256 label_fingerprint
```

The expert runner recomputes this fingerprint before evaluation. If an expected label changes after expert review, the old audit record becomes stale and execution fails closed.

This prevents a workflow where labels are professionally reviewed and then later modified without renewed expert review.

## Coverage rules

The protocol, dataset, Observation Set and label audit must agree on dataset ID/version.

Observation and label-audit case coverage must equal the complete BenchmarkDataset case set exactly:

```text
Dataset cases == Observation cases == Label-audit cases
```

Selective omission is rejected. This prevents removing hard or failed cases from a private run without changing the versioned dataset/protocol.

Each case must also preserve exact `case_version` alignment.

## Initial professional metric types

Stage 16.3 intentionally starts with metrics whose truth semantics are deterministic once professional labels exist.

### Binary classification

Examples include:

- whether a professionally labeled material finding should be surfaced;
- whether a high-risk Issue is present;
- other explicitly versioned yes/no expert labels.

The protocol declares the exact positive and negative classes. Both classes must be represented in usable expert truth; otherwise precision/recall/F1 would be degenerate and the metric is rejected.

Reported values:

```text
TP / FP / FN / TN
precision
recall
F1
```

### Exhaustive set extraction

Examples include professionally labeled complete sets of:

- relevant Contract Evidence identities;
- supplied-corpus Legal Evidence identities;
- other bounded expected identity sets.

The benchmark truth must use `SET_EQUALS`. Partial `SET_CONTAINS` truth is not accepted for precision/recall/F1 because an incomplete gold set would incorrectly count valid extra items as false positives.

Reported values:

```text
TP / FP / FN
precision
recall
F1
```

## Metric scoping

Every metric definition records:

- `metric_id`;
- metric type;
- assertion ID;
- task-type filter when applicable;
- required case tags when applicable;
- human-readable scope.

Metrics therefore stay tied to a named protocol and private dataset version. Stage 16.3 does not produce an invented cross-task global score.

High-risk recall, citation/evidence metrics or other professional claims must identify the exact metric definition and private dataset/protocol fingerprints that produced them.

## Sanitized aggregate report

`ExpertBenchmarkRunReport` contains only:

- evaluator identity;
- protocol ID/version;
- dataset ID/version;
- label-quality counts;
- scoped aggregate metric counts and precision/recall/F1;
- SHA-256 fingerprints for protocol, dataset, observations and label audit;
- explicit warnings/limitations.

It does not include:

- private case IDs;
- contract text;
- expected expert labels;
- per-case observed values;
- reviewer names;
- raw provider payloads;
- hidden model reasoning;
- credentials.

Detailed diagnostics stay inside the private benchmark boundary.

## CLI

From `backend/`:

```text
python -m app.expert_benchmark_cli \
  --repo-root .. \
  --protocol <external-or-benchmark_private/protocol.json>
```

Optional sanitized aggregate output:

```text
python -m app.expert_benchmark_cli \
  --repo-root .. \
  --protocol <private-protocol.json> \
  --output <sanitized-report.json>
```

The runner performs no DeepSeek/Kimi request. It consumes an existing Observation Set only.

## Synthetic repository tests

Public pytest fixtures may create synthetic files in a temporary private directory solely to verify protocol mechanics. They are not professional labels and must never be cited as Law-Rag legal accuracy.

The Stage 16.3 regression tests cover at least:

- valid aggregate binary/set metrics;
- visible `AMBIGUOUS` exclusion;
- tracked-repository path rejection;
- `PRIVATE_EXTERNAL` provenance enforcement;
- exact Observation/Audit case coverage;
- minimum reviewer count;
- stale label-fingerprint rejection;
- rejection of partial set truth;
- rejection of degenerate one-class binary truth.

## Release-gate boundary

Stage 16.3 defines **measurement semantics**, not arbitrary success thresholds.

No release threshold is invented before a real professionally labeled dataset has been reviewed for:

- case composition;
- reviewer agreement/adjudication quality;
- ambiguity rate;
- label definitions;
- domain/risk distribution;
- sample-size limitations.

A future release gate must explicitly version its dataset, protocol, metric definition and threshold rationale. Thresholds must not be lowered merely to make a model run pass.

## Non-goals

Stage 16.3 does not:

- commit private contracts or expert labels;
- claim a current professional accuracy number without real expert data;
- run paid/network DeepSeek or Kimi UAT;
- modify provider prompts to optimize benchmark scores;
- change legal-corpus identity/version semantics;
- redesign `ISSUE_V1`;
- begin Stage 17+.

Stage 16.4 will separately own explicit real-provider UAT observation capture.