# CURRENT_TASK.md

# Stage 12 — User-facing Workflow Simplification

## Status

```text
Stage 11A  COMPLETE — versioned benchmark schema + public synthetic evaluator
Stage 11B  COMPLETE — layered metrics + failure diagnostics + deterministic CI quality gates
Stage 11C  COMPLETE — runtime/startup/data-integrity hardening
Stage 11D  COMPLETE — reproducible Windows onedir bundle + clean-runner validation
Stage 11E  RC1 VALIDATED — portable Windows RC runs successfully; installer remains deferred
Stage 12A  COMPLETE — minimal intake home + real multi-file upload queue shell
Stage 12B  COMPLETE — persisted background audit pipeline + real progress/retry semantics
Stage 12C  COMPLETE — guarded 500 MiB streaming intake + bounded resource-aware batch scheduling
Stage 12D  COMPLETE — guided provider onboarding + Windows Credential Manager protected secrets
Stage 12E  COMPLETE — persisted batch result landing + risk-priority navigation/recovery
Stage 12F  ACTIVE — Windows RC2 clean-runner user-flow validation
```

The first portable RC validated packaging/runtime on CI and a real Windows desktop. Stage 12 then simplified the product path around first-run provider setup, drag/drop batch intake, automatic background processing, persistent progress/results, and a compact result landing page.

## Product goal

The normal user should see only four concepts:

```text
first-run API configuration
  -> drag one or more contracts into a simple queue
  -> wait while Law-Rag runs the required audit pipeline in the background
  -> review the batch summary, then open detailed evidence/workstation only where needed
```

Internal stages, debug buttons, provider implementation details and development panels must not dominate the normal workflow.

## Hard boundaries

1. Keep the existing Stage 10 evidence/review workstation as the detailed result surface, not the home page.
2. Preserve `/developer` for manual troubleshooting without making it a primary user path.
3. Progress must come from real upload/pipeline state; no fake 99% animation.
4. One failed file must not cancel or corrupt unrelated batch Jobs.
5. Large uploads remain streamed to disk; never read a 500 MiB contract into application memory merely to upload/validate it.
6. OCR/provider execution remains bounded; no unbounded fan-out.
7. API keys are never committed, bundled, echoed in diagnostics, returned to the browser, or stored as plaintext project/runtime secrets.
8. Users may intentionally skip provider setup and retain local-only functions.
9. DeepSeek/Kimi transmission remains disclosed; no hidden external model calls.
10. Batch/result persistence stores IDs/state references only and does not duplicate contract text into a second result store.
11. Result priority is not a correctness/legal-validity score.
12. Stage 1–11 regressions, public quality gates and Windows release safety boundaries remain green.

## 12A — Minimal intake home + batch queue shell

**Status: complete.**

- `/` is a minimal drag/drop intake instead of the legacy developer dashboard.
- Multi-file picker/drop queue with independent rows, real XHR upload progress, retry/removal, duplicate guard.
- `/developer` preserves manual Stage controls.
- `/workspace` remains the detailed evidence/review route.

## 12B — Application-owned background pipeline orchestrator

**Status: complete.**

```text
ingest
 -> OCR only where required
 -> canonical structure
 -> deterministic rules
 -> Stage 7 legal retrieval/context inside Stage 8
 -> DeepSeek primary audit
 -> Kimi secondary review
 -> deterministic comparison
 -> bounded Agent follow-up
 -> review report ready
```

- Every Job has versioned local `pipeline.json` state.
- POST starts/queues; GET polls read-only/provider-free; retry resumes with original settings.
- Valid persisted artifacts are reused rather than blindly rerun.
- Missing OCR/provider configuration stops in explicit waiting states.
- Normal intake automatically starts the pipeline and shows real persisted stage progress.

## 12C — 500 MiB streaming upload + bounded batch scheduling

**Status: complete.**

Large-file intake:

- exact per-file limit 500 MiB front/back;
- fixed 1 MiB streamed writes;
- expected size + 512 MiB disk reserve preflight;
- HTTP 507 on insufficient space;
- partial-file cleanup for oversize/write exhaustion;
- content signature and empty-file checks remain fail-closed.

Resource-aware execution:

```text
pipeline worker pool                  4 Jobs
local structure/rules/report work    2 concurrent
OCR                                  1 concurrent
DeepSeek + Kimi combined             2 concurrent
```

The browser still uploads files sequentially by design; already-uploaded Jobs can process concurrently under the fixed backend limits.

## 12D — First-run DeepSeek/Kimi configuration guide

**Status: complete.**

- Focused first-run modal with password inputs for DeepSeek and Kimi/Moonshot.
- Saved keys are never returned/repopulated; normal UI shows configured/not configured only.
- Windows desktop uses Generic Credentials in Windows Credential Manager.
- Environment variables remain a development/CI override and take precedence.
- Runtime stores only non-secret setup-completion state.
- Explicit test-connection sends one fixed tiny non-contract message and never echoes key/provider body.
- Users may skip and reopen API settings later.
- Packaged Windows synthetic `write -> read -> resolve -> delete` Credential Manager smoke is green.
- Development CORS now explicitly allows the PUT/DELETE methods required by the configuration UI.

## 12E — Batch result landing page

**Status: complete.**

Implemented:

- every intake session gets a local `batch_id` and a versioned runtime batch manifest;
- the manifest stores only Job IDs and timestamps, never duplicate contract text;
- each successfully uploaded Job is registered independently, so one failure cannot remove siblings;
- GET `/api/batches/{batch_id}` rebuilds its summary from current `pipeline.json` and `review-report.json` rather than persisting a second truth;
- GET `/api/batches/recent` restores the latest batch entry after browser/application restart;
- `/results?batch=<id>` is a dedicated compact result landing page;
- cards are deterministically sorted by human-review requirement, material disagreement, serious/high/medium risk and possible omissions;
- critical/high/medium/low counts and possible omission/material-disagreement flags remain explicit;
- failed, invalid, waiting and still-processing Jobs stay visible instead of being omitted;
- no aggregate correctness/legal-validity score is generated;
- complete Jobs link into the existing `/workspace?job=<id>` detailed evidence/review UI;
- all-success batches automatically open the result page; partial failure/waiting batches keep an explicit result-page button rather than silently navigating away;
- the intake home exposes a small `recent batch` recovery link when no new queue is active;
- backend regressions, public deterministic quality gates and locked frontend production build are green.

## 12F — Windows RC2 validation

**Status: active.**

RC2 config:

```text
0.8.0-rc2
portable Windows x64 onedir ZIP
publication_state = NOT_PUBLISHED
```

The final extracted RC must pass all earlier Stage 11D/11E checks plus a new packaged user-flow smoke:

- fresh first-run provider setup state;
- protected synthetic DeepSeek/Kimi credential save through the packaged HTTP API;
- no secret value in returned configuration JSON;
- protected credential deletion;
- explicit local-only skip state;
- one normal PDF plus one 64 MiB synthetic padded PDF, proving packaged intake exceeds the old 50 MiB limit;
- two Jobs registered into one persistent batch;
- `/results?batch=...` route served by the packaged SPA;
- application process stopped and restarted against the same runtime;
- provider onboarding completion survives restart;
- deleted synthetic keys remain absent;
- latest batch and both Job IDs survive restart;
- existing diagnostics, private-data scan, PDFium render, RC hash/manifest and extracted-ZIP smoke remain green.

Default CI remains provider-free and does not use paid model keys. Full real-provider desktop UAT remains a manual step.

Installer work remains deferred unless RC2 testing demonstrates a concrete need.

## Current implementation boundary

Proceed with **12F validation only**. If the Windows RC2 clean-runner fails, fix only the release/user-flow regression that caused the failure. After RC2 is green, close Stage 12 and perform an end-to-end product-gap review before adding any new feature stage.
