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
Stage 12C  NEXT — 500 MiB streaming upload + bounded batch scheduling
Stage 12D  PENDING — guided DeepSeek/Kimi configuration + protected local secrets
Stage 12E  PENDING — batch result landing page
Stage 12F  PENDING — Windows RC2 validation
```

The first portable RC validated the packaging/runtime path on CI and on a real Windows desktop. User feedback showed the next highest-value work is not an installer: simplify intake, automate the pipeline, support large/batch files, and guide API configuration.

## Product goal

The normal user should see only three concepts:

```text
first-run configuration
  -> drag one or more contracts into a simple queue
  -> wait while Law-Rag runs the required audit pipeline in the background
  -> open the finished result/workstation
```

Internal stages, debug buttons, provider implementation details and development panels must not dominate the normal workflow.

## Hard boundaries

1. Keep the existing Stage 10 evidence/review workstation; it becomes the detailed result surface rather than the home page.
2. Preserve a developer/debug route for manual stage execution and troubleshooting, but do not expose it as the primary user experience.
3. Progress must come from real pipeline/upload state; do not animate fake percentages toward 99%.
4. A failed file in a batch must not cancel or corrupt unrelated jobs.
5. Large uploads must remain streamed to disk; never read a 500 MiB file into application memory merely to validate/upload it.
6. Batch execution must use bounded concurrency. OCR and provider calls must not fan out without limits.
7. API keys must never be committed, bundled in RC artifacts, echoed in diagnostics, or stored as ordinary plaintext project files.
8. First-run configuration must allow local-only use when provider keys are intentionally skipped.
9. No hidden provider calls: DeepSeek/Kimi external transmission remains explicit in the user-facing audit flow/configuration.
10. Stage 1–11 regressions, public quality gates and Windows release safety boundaries remain green.

## 12A — Minimal intake home + batch queue shell

**Status: complete.**

Implemented and validated:

- `/` is now a minimal drag/drop intake instead of the legacy developer dashboard;
- multi-file picker/drop queue;
- one independent queue row per file;
- sequential use of the existing single-file upload API so one failure does not cancel the batch;
- real XHR upload progress, followed by explicit server-side document-reading state;
- independent retry/removal semantics;
- duplicate selection guard;
- legacy Stage controls preserved under `/developer`;
- `/workspace` remains the detailed evidence/review route;
- frontend locked production build, backend regressions and public quality gates green.

## 12B — Application-owned background pipeline orchestrator

**Status: complete.**

Implemented and validated:

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

Behavior:

- every Job has versioned local `pipeline.json` state;
- POST `/api/documents/{job}/pipeline` queues work and returns immediately;
- GET `/api/documents/{job}/pipeline` is read-only/provider-free polling;
- POST `/api/documents/{job}/pipeline/retry` resumes using the original `as_of`/semantic settings;
- successful persisted OCR/structure/rules/primary/secondary/review artifacts are reused when valid rather than blindly rerun;
- native-text documents explicitly skip OCR;
- missing PaddleOCR stops at `WAITING_OPTIONAL_COMPONENT` rather than crashing the whole queue;
- missing DeepSeek/Kimi configuration stops at `WAITING_CONFIGURATION` with the completed local stages preserved;
- unexpected failures fail closed with persisted stage/error state;
- duplicate start/retry while a Job thread is already alive returns the current state rather than resetting it;
- normal intake automatically starts the pipeline after upload and polls real state;
- user-visible progress is derived from upload bytes + persisted stage milestones only;
- completed rows expose the existing `/workspace?job=<id>` result surface;
- external DeepSeek/Kimi transmission is disclosed on the intake page before processing;
- Stage 12B deliberately serializes complete pipelines with concurrency = 1 so multi-file intake cannot fan out OCR/provider calls before 12C introduces measured per-resource limits;
- pipeline concurrency, retry/configuration, read-only polling and artifact-reuse regressions are covered;
- backend regressions, public quality gates and locked frontend production build are green.

## 12C — 500 MiB streaming upload + bounded batch scheduling

**Status: next.**

Raise the per-file limit from 50 MiB to 500 MiB while preserving chunked streaming and cleanup-on-failure.

Batch policy:

- one Job per file;
- frontend/client queue may contain many files;
- add explicit disk-space preflight/failure states for large local uploads;
- keep upload streaming/chunked and never buffer a 500 MiB file in memory;
- split the conservative Stage 12B global concurrency=1 into bounded resource-specific scheduling only where measured/safe;
- OCR default concurrency remains 1 unless measured otherwise;
- external model calls default to a small bounded concurrency;
- one failed Job does not abort the batch;
- queue status must distinguish waiting-for-worker from actively processing.

## 12D — First-run DeepSeek/Kimi configuration guide

On first normal launch, show a simple provider setup flow for:

```text
DeepSeek API Key
Kimi / Moonshot API Key
```

Requirements:

- password-style inputs; never re-display full saved keys;
- test-connection actions must be explicit and must not send contract data;
- user may skip and continue local-only;
- normal UI shows only configured/not configured;
- Windows release should use an OS-appropriate protected local secret store rather than writing keys into a plaintext `.env` file;
- development environment-variable support may remain for contributors/CI.

Provider defaults remain the currently accepted DeepSeek primary and Kimi secondary adapters unless a later decision supersedes them.

## 12E — Batch result landing page

After processing:

- show one compact summary row/card per contract;
- distinguish completed, failed and human-review-required Jobs;
- summarize high/medium/low findings and material disagreement without inventing a correctness score;
- click a contract to open the existing `/workspace?job=<id>` detailed evidence/review UI;
- preserve visible `CURATED_EXCERPT`, evidence and human-review boundaries.

## 12F — Windows RC2 validation

Build a new portable RC only after 12A–12E are stable.

Validate on clean Windows and real desktop:

- first-run setup/skip flow;
- single and multi-file intake;
- large-file streaming behavior with safe synthetic fixtures;
- queue recovery after one failure;
- background pipeline progress;
- result navigation;
- restart/persistence;
- no keys/private data in bundle/diagnostics;
- developer route remains available but not primary.

Installer work remains deferred unless RC2 testing demonstrates a concrete need.

## Current implementation boundary

Proceed with **12C only** next. Do not combine 500 MiB upload/scheduling, protected secret storage and result-summary redesign into one patch.
