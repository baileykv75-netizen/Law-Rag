# Real-provider ISSUE_V1 UAT

Stage 16.4 separates **running the production provider chain** from **capturing UAT evidence**.

The UAT capture reader is deliberately read-only. It never invokes Audit Planner, DeepSeek, Kimi, OCR, or another network/provider boundary. A real-provider observation can exist only after an operator has explicitly run the normal production `ISSUE_V1` pipeline with configured providers.

## Evidence boundary

Stage 16 keeps three different evidence classes separate:

```text
PUBLIC_REGRESSION
  deterministic checked-in regression evidence

PRIVATE_EXPERT
  professionally labeled private truth

REAL_PROVIDER_UAT
  explicit provider/model-specific ISSUE_V1 behavior/provenance observations
```

`REAL_PROVIDER_UAT` is **not** expert truth. DeepSeek/Kimi agreement does not establish legal correctness, and a successful provider-chain run does not create a professional `legal_accuracy` score.

## Production path being observed

The capture path observes the existing production topology without creating another model pipeline:

```text
Canonical Contract
 -> Audit Planner
 -> Issue Legal Context
 -> DeepSeek issue primary audit
 -> Kimi issue finding + coverage review
 -> deterministic Issue comparison
```

The capture reader validates the persisted authoritative artifacts produced by this path:

```text
pipeline.json
audit-plan.json
issue-legal-context.json
issue-primary-audit.json
issue-secondary-review.json          when present
issue-review-report.json             when present
```

It verifies job identity, run parameters, Issue coverage, provider/model identity, embedded artifact fingerprints, cross-artifact fingerprint links, pipeline stage states, and complete/interrupted checkpoint semantics.

## Private observation location

Detailed UAT observations may be written only:

- outside the repository; or
- under ignored `benchmark_private/`.

Tracked repository paths fail closed. Existing observation files are never overwritten; UAT observations are append-only evidence.

A detailed observation may contain:

- local job ID;
- AuditPlan Issue IDs;
- provider request IDs;
- provider raw-response SHA-256 hashes;
- per-Issue provider-call/coverage presence;
- authoritative artifact file hashes/fingerprints.

Therefore the detailed observation is private even though it does not persist raw hidden reasoning or unrestricted provider payloads.

## Public/sanitized summary boundary

The capture API also returns a sanitized report containing only:

- `ISSUE_V1` architecture identity;
- capture mode and chain state;
- provider/model summaries and aggregate usage where available;
- Issue completion counts;
- authoritative artifact SHA-256/fingerprints;
- observation fingerprint;
- warnings about evidence scope.

It omits job IDs, Issue IDs, provider request IDs, raw-response hashes, contract text, Legal Evidence text, credentials, and hidden reasoning.

## Capture modes

```text
TEST_DOUBLE
REAL_PROVIDER
```

`TEST_DOUBLE` exists for provider-free CI and local regression only.

`REAL_PROVIDER` requires explicit confirmation. Fake/test/stub/mock/double/dummy provider or model identities are rejected, and the current production identity mapping is:

```text
Planner    -> deepseek
Primary    -> deepseek
Secondary  -> kimi
```

## Capturing an already-executed job

From `backend/`:

```text
python -m app.uat_capture_cli \
  --repo-root .. \
  --job-id <existing-issue-v1-job-uuid> \
  --output <external-or-benchmark_private/observation.json> \
  --mode REAL_PROVIDER \
  --confirm-real-provider-uat
```

The confirmation flag labels persisted provider artifacts as an explicit real-provider UAT observation. It does **not** itself trigger a network request.

If the provider chain was cancelled after checkpoint persistence, capture may produce:

```text
PRIMARY_INTERRUPTED
SECONDARY_INTERRUPTED
```

A fully completed chain produces:

```text
COMPLETE
```

Contradictory artifact/pipeline states fail closed instead of being normalized.

## Evaluation-suite integration

Stage 16.4 adds a dedicated `UAT_CAPTURE` entry kind for private `REAL_PROVIDER_UAT` suites. This consumes the private `IssueV1UATObservation` directly and does not require fabricating benchmark truth labels.

Example private suite manifest:

```json
{
  "schema_version": "1.0.0",
  "suite_id": "local-real-provider-uat",
  "suite_version": "1.0.0",
  "title": "Local real-provider ISSUE_V1 UAT",
  "description": "Provider-chain behavior/provenance only.",
  "suite_class": "REAL_PROVIDER_UAT",
  "entries": [
    {
      "entry_id": "issue-v1-run-001",
      "kind": "UAT_CAPTURE",
      "scope": "Provider-chain completion and provenance only; not legal correctness.",
      "uat_observation_path": "observation.json"
    }
  ]
}
```

Run it from `backend/`:

```text
python -m app.evaluation_suite_cli \
  --repo-root .. \
  --suite <external-or-benchmark_private/uat-suite.json>
```

Suite semantics for `UAT_CAPTURE` are intentionally narrow:

- `COMPLETE` -> entry `passed=true` because the observed production provider chain completed with internally consistent provenance;
- `PRIMARY_INTERRUPTED` / `SECONDARY_INTERRUPTED` -> evidence is preserved but entry `passed=false`;
- `passed=true` does **not** mean the legal conclusions are professionally correct.

The evaluation-suite summary exposes only sanitized provider/model and artifact provenance. Detailed job/Issue/request/raw-response provenance remains in the private observation.

## Actual paid/network UAT procedure

Real-provider execution is an explicit operator action and must never occur in ordinary CI.

Before a real UAT run:

1. choose a bounded private/public test contract suitable for provider transmission;
2. verify DeepSeek and Kimi configuration through the existing product provider boundary;
3. choose and record the exact `as_of` date and semantic-retrieval setting;
4. run the normal production `ISSUE_V1` pipeline with the existing approval/cancellation controls;
5. do not edit persisted artifacts after the run;
6. capture the completed or interrupted job with `uat_capture_cli` into a private path;
7. optionally assemble a private `REAL_PROVIDER_UAT` suite using `UAT_CAPTURE`;
8. retain only sanitized summary data for Stage 16 release-quality evidence assembly.

The real run must not be triggered merely by pytest, Stage 16 CI, the capture CLI, or the evaluation-suite CLI.

## Current Stage 16.4 status

The provider-free capture mechanics, privacy guards, COMPLETE/interruption semantics, CLI opt-in boundary, pipeline/artifact consistency checks, and evaluation-suite adapter can be validated in public CI without contacting paid providers.

Until an operator explicitly authorizes and executes at least one real DeepSeek/Kimi production `ISSUE_V1` run and captures it, Stage 16.4 remains **READY_FOR_REAL_UAT**, not evidence-complete.
