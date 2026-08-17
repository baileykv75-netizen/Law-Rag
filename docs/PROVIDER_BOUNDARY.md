# Provider Boundary and Cancellation Model

## Purpose

Stage 13A adds an application-owned control plane between local contract processing and external DeepSeek/Kimi generation. The goal is operational control over sensitive contract transmission, not a claim that an HTTP request can be recalled after it has started.

## Provider policies

```text
REQUIRE_APPROVAL
  local processing/context first
  -> pause before provider generation
  -> explicit user approval

AUTO_CONTINUE
  local processing/context first
  -> continue when provider configuration is ready

LOCAL_ONLY
  local processing/context first
  -> never start provider generation unless the user later explicitly approves
```

The normal intake UI defaults to `REQUIRE_APPROVAL`.

## Why control is separate from progress

`pipeline.json` describes execution progress. User intent is stored independently in:

```text
runtime/jobs/<job-id>/pipeline-control.json
```

The control record contains no contract text or API secret. It stores only the Job identity and operational state such as:

- provider mode;
- whether the provider phase has been explicitly approved;
- cancellation intent/time;
- which provider request, if any, has crossed the outbound boundary.

This separation prevents a stale worker progress write from silently erasing a user's cancel/pause intent.

## Exact outbound order

For the DeepSeek primary path:

```text
canonical contract + deterministic rules
 -> build local legal retrieval / bounded AuditContextPackage
 -> read provider policy / cancellation state
 -> provider configuration check
 -> wait for bounded external-provider slot
 -> atomic cancellation/policy recheck
 -> persist active_provider=deepseek
 -> provider.generate(context)
 -> clear active_provider
 -> cancellation checkpoint before the next stage
```

Kimi follows the same pattern after rebuilding/validating the secondary context against the persisted primary audit.

The final `begin_provider_call()` check and user control mutations share a per-Job lock. Therefore one of two facts is recorded deterministically:

1. cancel/pause wins before the boundary and generation does not start; or
2. generation wins the boundary first and `active_provider` records that the request has started.

There is no state that claims an already-started request was made unsent.

## Pipeline states

Stage 13A adds:

```text
PAUSED_BEFORE_PROVIDER
CANCEL_REQUESTED
CANCELLED
```

Representative reasons:

```text
PROVIDER_APPROVAL_REQUIRED
LOCAL_ONLY_PROVIDER_DISABLED
PIPELINE_CANCEL_REQUESTED
PIPELINE_CANCELLED
```

## Cancellation semantics

### Before any provider request

Cancellation is persisted immediately. The current cooperative local stage may finish its current safe unit of work, but no later provider generation can cross the final atomic boundary.

### While a provider request is in flight

Law-Rag reports that the current provider request has already started and cannot be recalled. The cancellation record remains set. When the request returns, the next cancellation checkpoint stops the pipeline before Kimi or later stages can begin.

### Cancelled Jobs

Ordinary `/pipeline/retry` deliberately rejects `CANCELLED`/`CANCEL_REQUESTED`. Restarting a cancelled Job requires the explicit `/pipeline/resume` action. Resume clears the cancel request but retains provider policy. A `REQUIRE_APPROVAL` Job therefore pauses again before provider generation unless the user explicitly approves it.

## Restart semantics

Process-local workers and HTTP requests cannot survive application exit. Startup recovery therefore:

- clears stale `active_provider` markers;
- resolves persisted cancel intent to `CANCELLED`;
- keeps ordinary interrupted transient work under the existing `APPLICATION_RESTARTED_RETRY_REQUIRED` behavior;
- never resumes an external provider automatically.

## API surface

```text
GET  /api/documents/<job>/pipeline/control
PUT  /api/documents/<job>/pipeline/control
POST /api/documents/<job>/pipeline/pause-provider
POST /api/documents/<job>/pipeline/approve-provider
POST /api/documents/<job>/pipeline/cancel
POST /api/documents/<job>/pipeline/resume
```

GET control is read-only. For a legacy Job without a control file, it synthesizes `AUTO_CONTINUE` for compatibility without creating a file.

## Privacy boundaries

Stage 13A does not change the Stage 8/9 evidence-bounded provider payload rules. It adds control over *when* those existing bounded payloads may leave the machine.

It does not:

- encrypt runtime contract files at rest;
- bundle OCR;
- expand the legal corpus;
- add arbitrary network/web tools;
- allow the Agent to control provider authorization;
- expose API keys to the browser;
- claim cancellation can revoke data already received by a provider.

Those remain separate product/security concerns.

## Validation

Default CI remains provider-free. Regression coverage verifies local context preparation before approval, cancellation persistence, explicit resume, in-flight provider semantics and restart recovery.

The Windows release smoke additionally runs the extracted packaged executable with `REQUIRE_APPROVAL`, verifies `PAUSED_BEFORE_PROVIDER` before any provider is active, cancels it, verifies `CANCELLED`, explicitly resumes it, and verifies it pauses again. No real provider key or paid provider call is used.