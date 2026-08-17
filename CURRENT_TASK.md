# CURRENT_TASK.md

# Stage 12 — User-facing Workflow Simplification

## Status

```text
Stage 11A  COMPLETE — versioned benchmark schema + public synthetic evaluator
Stage 11B  COMPLETE — layered metrics + failure diagnostics + deterministic CI quality gates
Stage 11C  COMPLETE — runtime/startup/data-integrity hardening
Stage 11D  COMPLETE — reproducible Windows onedir bundle + clean-runner validation
Stage 11E  RC1 VALIDATED — portable Windows RC runs successfully; installer remains deferred
Stage 12   ACTIVE — user-facing intake, queue, guided configuration and automated pipeline
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

Replace the legacy developer-heavy root page with a minimal intake surface:

- large drag/drop target;
- multi-file selection;
- one queue row per file;
- filename, size, state and real upload progress;
- independent failure/retry/removal semantics;
- current supported formats remain explicit;
- old developer controls move to `/developer`;
- `/workspace` remains the detailed review route.

12A may use the existing one-file upload API repeatedly; it must not fake downstream audit completion before the orchestrator exists.

## 12B — Application-owned background pipeline orchestrator

Create one server-owned pipeline state machine per Job. The normal path should automatically execute the required stages in order:

```text
ingest
 -> OCR only where required
 -> canonical structure
 -> deterministic rules
 -> legal retrieval/context
 -> DeepSeek primary audit
 -> Kimi secondary review
 -> deterministic comparison
 -> bounded Agent follow-up
 -> review report ready
```

Requirements:

- persisted pipeline state/progress;
- retryable stage failures without rerunning already valid immutable work unnecessarily;
- explicit optional/unavailable states for OCR/provider configuration;
- no open-ended Agent loop;
- API/UI polling must be read-only and provider-free;
- a completed Job exposes the existing professional workstation.

## 12C — 500 MiB streaming upload + bounded batch scheduling

Raise the per-file limit from 50 MiB to 500 MiB while preserving chunked streaming and cleanup-on-failure.

Batch policy:

- one Job per file;
- frontend/client queue may contain many files;
- bounded concurrent local parsing;
- OCR default concurrency 1 unless measured otherwise;
- external model calls default to a small bounded concurrency;
- disk-space and oversize failures are explicit per file;
- one failed Job does not abort the batch.

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

Start with **12A only**. Do not combine the UI rewrite, background orchestrator, protected secret storage and large-file scheduling into one unreviewable patch.
