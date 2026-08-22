# Stage 18.3 — Provider Resource and Cost Controls

## Scope

Stage 18.3 adds **per-Job** visibility and continuation limits around the existing bounded DeepSeek/Kimi provider boundary.

It does **not**:

- change the AuditPlan or Issue V1 audit semantics;
- add a third model or provider vote;
- bypass provider approval, cancellation, or `LOCAL_ONLY` behavior;
- fetch live vendor pricing;
- claim that an estimated cost is an invoice;
- run paid/network DeepSeek or Kimi calls during CI.

The default policy is intentionally unlimited. Existing jobs keep their historical behavior until a user explicitly saves a resource policy.

## Boundary model

The existing local provider boundary remains authoritative:

```text
local deterministic work
 -> provider approval / LOCAL_ONLY / cancellation check
 -> Stage 18.3 budget reservation
 -> persisted active-provider state
 -> outbound provider request
 -> provider return
 -> Stage 13E/F validation + checkpoint
 -> Stage 18.3 checkpoint reconciliation
```

The provider approval/cancellation model still decides whether data may cross the external boundary. Stage 18.3 adds a second independent gate: whether the current Job is still allowed to spend another provider request under the saved resource policy.

## Exact versus continuation limits

### Provider-call count

`max_provider_calls` is a **hard pre-request limit**.

Every request that is permitted to cross the external boundary consumes one durable ledger slot before `provider.generate(...)` is invoked. A subsequent request cannot start when the configured count has been exhausted.

A request blocked by:

- `LOCAL_ONLY`;
- missing provider approval;
- cancellation;
- an already-exhausted resource budget;

never consumes a provider-call slot.

### Token limit

`max_total_tokens` is deliberately a **continuation limit based on provider-reported usage**.

The final token count of one request is not known exactly before the provider returns. Therefore one in-flight request may report usage above the remaining token threshold. Law-Rag then blocks every subsequent provider call.

If an already-started/returned request has no trustworthy token usage, the ledger does **not** count the unknown value as zero. With a token limit enabled, the next provider call fails closed with an explicit unknown-usage state.

### Estimated-cost limit

`max_estimated_cost` is also a continuation limit.

Cost is computed only from:

```text
provider-reported prompt_tokens
provider-reported completion_tokens
user-configured prompt price per 1M tokens
user-configured completion price per 1M tokens
user-configured currency label
```

No DeepSeek/Kimi price is hardcoded and Stage 18.3 does not fetch live vendor pricing. The displayed value is a local estimate, not a provider invoice or guaranteed charge.

When an estimated-cost limit is enabled:

- the current provider must have a user-configured price entry;
- prompt/completion token usage must be known for prior calls being priced;
- missing pricing or missing usage blocks subsequent calls rather than silently assuming zero cost.

## Durable per-Job ledger

The ledger is stored at:

```text
runtime/jobs/<job_id>/resource-budget.json
```

The artifact is fingerprinted and written atomically. A symlinked `resource-budget.json` or symlinked Job directory is rejected.

Ledger states:

```text
STARTED
RETURNED_PENDING_RECONCILIATION
COMPLETED
FAILED
```

`STARTED` means a provider request was allowed to cross the external boundary and must be accounted for conservatively even if the process later crashes.

`RETURNED_PENDING_RECONCILIATION` means the provider request returned but Stage 13E/F has not yet produced the authoritative validated provider-call checkpoint that supplies usage/hash accounting.

`COMPLETED` means the call has reconciled usage information.

`FAILED` is reserved for an explicitly terminal failed ledger call where accounting information remains available.

## Existing checkpoint reconciliation

Stage 13E Primary and Stage 13F Secondary artifacts remain the authoritative provider-result checkpoints. Stage 18.3 reads their `provider_calls` and attaches usage to the matching live ledger row instead of counting the same network call twice.

Historical completed jobs created before Stage 18.3 are imported into the ledger on read without changing their audit artifacts.

Older test/legacy checkpoints may contain opaque `raw_response_hash` identifiers rather than a canonical 64-character SHA-256 string. Only when such an already-validated historical checkpoint is imported, Stage 18.3 derives:

```text
sha256(raw_response_hash UTF-8 bytes)
```

and stores that derived value as the ledger checkpoint fingerprint. The source Stage 13 artifact is not rewritten. New/live ledger checkpoint fingerprints remain strict lowercase 64-character SHA-256 values.

## API

Read current local accounting state:

```http
GET /api/documents/{job_id}/resource-budget
```

Save a per-Job policy without starting provider work:

```http
PUT /api/documents/{job_id}/resource-budget
Content-Type: application/json

{
  "policy": {
    "max_provider_calls": 20,
    "max_total_tokens": 200000,
    "max_estimated_cost": 10.0,
    "currency": "CNY",
    "provider_prices": {
      "deepseek": {
        "prompt_per_million": 0.0,
        "completion_per_million": 0.0
      },
      "kimi": {
        "prompt_per_million": 0.0,
        "completion_per_million": 0.0
      }
    }
  }
}
```

The numeric price values above are only schema examples. They are **not** vendor pricing recommendations.

## Workspace UX

The Issue V1 Workspace shows:

- provider calls used and configured remaining count;
- known total tokens and configured remaining continuation allowance;
- locally estimated cost and remaining estimated allowance when configured;
- unknown usage count plus in-flight / returned-pending counts;
- the current budget state;
- explicit warnings explaining continuation-limit semantics.

The edit panel defaults to blank/unlimited values. Saving it only writes the local per-Job budget artifact and never starts a model request.

## Fail-closed states

```text
EXHAUSTED
USAGE_UNKNOWN_BLOCKED
COST_UNKNOWN_BLOCKED
```

The provider boundary converts Stage 18.3 blocking conditions into the same persisted `ProviderBoundaryPaused` control family already used by `LOCAL_ONLY` and explicit provider approval. That preserves checkpoint/retry behavior instead of creating a second execution pipeline.

## CI and provider boundary

Stage 18.3 tests are provider-free. They cover:

- unlimited default behavior;
- exact call-count boundary;
- `LOCAL_ONLY` and unapproved calls consuming zero budget;
- token-usage unknown fail-closed behavior;
- checkpoint reconciliation without double counting;
- historical checkpoint import idempotence;
- legacy opaque checkpoint-reference normalization;
- strict live SHA-256 checkpoint fingerprints;
- user-configured estimated cost math;
- missing-provider pricing rejection;
- crash-surviving `STARTED` accounting;
- local API round trip;
- symlink rejection.

Validated implementation evidence:

```text
head 72e3819be3bfab3796e7242d4fcf68a0979cdd4f
Law-Rag Stage 18 CI #50
run 32549130409
SUCCESS
backend 519 passed, 5 skipped, 1 third-party warning
frontend PASS
Stage 16 public gates/regression/suite PASS
release evidence matrix PASS
runtime encryption truthfulness PASS
```

The later closeout commits only record this evidence/status; the final closeout head must also pass the same Stage 18 CI before Stage 18.3 is frozen as the base for Stage 18.4.

Real DeepSeek/Kimi paid/network UAT remains deferred to the final acceptance boundary after Stage 19 engineering.
