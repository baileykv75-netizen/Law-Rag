# CURRENT_TASK.md

# Stage 13 — Safety and Desktop Control

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel control validated
Stage 13B       NEXT — Windows tray + graceful quit
Stage 13C       PENDING — batch history + local storage management
```

Stage 13 addresses the operational-control gaps identified after RC2. It does not expand the legal corpus, OCR distribution or model reasoning scope.

## Stage 13A — Provider boundary + pause/cancel

**Status: complete.**

A successfully uploaded contract remains under explicit application/user control before external model transmission. Provider/cancel intent is persisted independently from ordinary pipeline progress and survives browser/application restart.

### Provider modes

```text
REQUIRE_APPROVAL  default normal UI; local work first, then explicit approval
AUTO_CONTINUE     deliberate opt-in to automatic provider continuation
LOCAL_ONLY        stop before external model generation until explicitly approved
```

### Persisted pipeline states

```text
PAUSED_BEFORE_PROVIDER
CANCEL_REQUESTED
CANCELLED
```

`runtime/jobs/<job-id>/pipeline-control.json` stores only operational control metadata; it contains no contract text or API secret.

### Validated outbound semantics

```text
ingest
 -> OCR if required/available
 -> canonical structure
 -> deterministic rules
 -> build local Stage 8 legal retrieval / bounded Evidence context
 -> provider policy gate
 -> provider configuration check
 -> bounded provider slot
 -> atomic cancel/policy recheck + active-provider record
 -> DeepSeek generate
 -> cancellation checkpoint
 -> rebuild/validate local Kimi secondary context
 -> provider policy gate
 -> atomic cancel/policy recheck + active-provider record
 -> Kimi generate
 -> cancellation checkpoint
 -> local comparison / bounded Agent / review report
```

No DeepSeek/Kimi `generate()` call starts before the final atomic control check. Local legal retrieval/context preparation may complete before the outbound pause, so user approval controls transmission rather than preventing useful local preparation.

### Cancellation semantics

1. Cancellation before the provider boundary prevents provider generation.
2. Cancellation during local work is cooperative and stops at a safe checkpoint; completed artifacts are preserved.
3. A provider request that has already started cannot be recalled or made unsent. The UI states this explicitly.
4. If cancellation is requested while a provider request is in flight, Law-Rag records the active provider and blocks every subsequent provider/stage after the current request returns.
5. `CANCELLED` Jobs cannot restart through ordinary retry; they require explicit resume.
6. Explicit resume keeps the Job's existing provider policy. A cancelled `REQUIRE_APPROVAL` Job therefore pauses again before cloud transmission until explicitly approved.
7. If the application exits after cancellation was requested, startup recovery resolves the Job to `CANCELLED`; no provider work silently resumes.
8. Legacy Jobs without `pipeline-control.json` are synthesized as `AUTO_CONTINUE` for compatibility, and read-only control inspection does not create a file.

### Normal UI

The intake page defaults to:

```text
发送前确认（推荐）
```

Users may deliberately select before adding files:

```text
本地完成后自动继续
仅本地处理
```

Per-Job controls are available on intake/result surfaces:

- `批准云端审计`;
- `发送前暂停` for future not-yet-started provider calls;
- `取消` / `取消审计`;
- explicit `重新开始` for cancelled Jobs.

Paused and cancelled Jobs remain visible in batch summaries and are never converted into a legal-risk/correctness score.

### Validation completed

Backend regressions cover:

- local OCR/structure/rules plus local Stage 8 Evidence/legal-context preparation before approval pause;
- `REQUIRE_APPROVAL` and `LOCAL_ONLY` preventing outbound generation;
- explicit approval/resume;
- cancellation terminal state and generic-retry rejection;
- in-flight DeepSeek cancellation blocking Kimi/subsequent stages;
- restart reconciliation from cancel-requested to cancelled;
- legacy control reads remaining non-mutating.

Frontend TypeScript/production build validates the provider-policy selector and intake/result actions.

The clean Windows final-ZIP smoke passed, without provider keys or paid model calls:

```text
REQUIRE_APPROVAL
 -> local stages/context
 -> PAUSED_BEFORE_PROVIDER / PROVIDER_APPROVAL_REQUIRED
 -> no active provider
 -> cancel
 -> CANCELLED
 -> explicit resume
 -> PAUSED_BEFORE_PROVIDER again
```

The same run also passed the existing Credential Manager, base packaged runtime, PDFium, Stage 12 user-flow, deterministic RC archive and final extracted-ZIP checks.

See [`docs/PROVIDER_BOUNDARY.md`](docs/PROVIDER_BOUNDARY.md) for the security model.

## Hard boundaries retained

- no private contract/API secret in Git or release bundles;
- no hidden provider call;
- no arbitrary thread kill as cancellation semantics;
- no claim that an already-started provider request can be revoked;
- no destructive cleanup of prior valid artifacts;
- no OCR/legal-corpus expansion in Stage 13A;
- public/default CI remains provider-free;
- Stage 11 quality gate and Stage 12 product regressions remain green.

## Stage 13B — Windows tray + graceful quit

**Status: next; not started in the Stage 13A iteration.**

Goal for the next iteration:

```text
hidden-console Law-Rag.exe
 -> Windows tray icon
 -> Open Law-Rag
 -> show useful running/waiting task state
 -> Exit Law-Rag
 -> stop accepting/starting new work
 -> persist fail-closed pipeline state
 -> gracefully stop local FastAPI process
```

Quit must not delete runtime data, silently continue provider work, or pretend an in-flight provider transmission can be revoked.

## Stage 13C — Batch history + local storage management

Pending until 13B is independently complete and validated.

## Current implementation boundary

**Stage 13A is closed.**

The next explicit implementation task is **Stage 13B Windows tray + graceful quit**. Do not start Stage 13C or later roadmap work in the same iteration.