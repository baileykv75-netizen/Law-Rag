# Stage 16.3 Synthetic Expert-Benchmark Example

This file illustrates the **shape** of a private expert benchmark without containing real contracts, professional labels or production accuracy evidence.

Real Stage 16.3 inputs must remain external or under ignored `benchmark_private/`.

## Example protocol skeleton

```json
{
  "schema_version": "1.0.0",
  "protocol_id": "example-private-protocol",
  "protocol_version": "1.0.0",
  "title": "Example only",
  "scope": "Synthetic structure example; not professional evidence.",
  "dataset_id": "example-private-dataset",
  "dataset_version": "1.0.0",
  "dataset_path": "dataset.json",
  "observations_path": "observations.json",
  "label_audit_path": "label-audit.json",
  "minimum_reviewer_count": 2,
  "metrics": [
    {
      "metric_id": "example-risk-recall",
      "label": "Example binary professional metric",
      "metric_type": "BINARY_CLASSIFICATION",
      "assertion_id": "risk_class",
      "scope": "Example only.",
      "task_types": ["PRIMARY_AUDIT_FINDING"],
      "include_tags_all": ["finding"],
      "positive_values": ["RISK"],
      "negative_values": ["NO_RISK"]
    }
  ]
}
```

## Label audit principle

Each real private case must carry an audit record bound to the current expected labels by SHA-256:

```json
{
  "case_id": "private-case-id",
  "case_version": "1.0.0",
  "status": "AGREED",
  "reviewer_count": 2,
  "adjudicator_count": 0,
  "label_fingerprint": "<64 lowercase hex characters>"
}
```

The fingerprint is not a privacy substitute; the underlying case and labels still remain private. Its purpose is to make later label mutation detectable.

## Interpretation

A resulting aggregate like `recall = 0.82` would mean only:

> Under the exact named private dataset/protocol versions and their audited labels, the specified binary metric produced recall 0.82.

It would **not** mean:

- Law-Rag is 82% legally correct;
- Chinese-law coverage is 82%;
- every contract type has 82% recall;
- DeepSeek or Kimi alone has 82% accuracy;
- the value is a release threshold.

The real protocol, dataset composition, label quality, ambiguity rate and sample size must be reviewed before any professional metric is used for release decisions.