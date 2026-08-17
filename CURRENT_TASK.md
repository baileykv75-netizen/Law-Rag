# CURRENT_TASK.md

# Stage 13 — Safety and Desktop Control

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       VALIDATION — provider boundary + pause/cancel control
Stage 13B       PENDING — Windows tray + graceful quit
Stage 13C       PENDING — batch history + local storage management
```

Stage 13 addresses the operational-control gaps identified after RC2. It does not expand the legal corpus, OCR distribution or model reasoning scope.

## Stage 13A — Provider boundary + pause/cancel

### Goal

A successfully uploaded contract must remain under explicit application/user control before external model transmission. The control plane must survive refresh/restart and must not rely on killing worker threads.

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

Provider/cancel intent is persisted separately in `pipeline-control.json` so worker progress writes cannot silently overwrite user intent.

### Outbound boundary semantics

The primary path is now:

```text
ingest
 -> OCR if required/available
 -> canonical structure
 -> deterministic rules
 -> build local Stage 8 legal retrieval / bounded Evidence context
 -> provider policy gate
 -> provider slot
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

No DeepSeek/Kimi `generate()` call may start before the final atomic control check.

### Cancellation rules

1. Cancellation before the provider boundary prevents provider generation.
2. Cancellation during local work is cooperative and stops at the next safe checkpoint; completed artifacts are preserved.
3. A provider request that has already started cannot be recalled. The UI must say so explicitly.
4. If cancellation is requested while a provider request is in flight, Law-Rag records the provider as active and blocks every subsequent provider/stage after the current request returns.
5. `CANCELLED` Jobs do not restart through ordinary retry; they require an explicit resume action.
6. Explicit resume keeps the Job's existing provider policy. A cancelled `REQUIRE_APPROVAL` Job therefore pauses again before cloud transmission until approved.
7. If the application exits after cancellation was requested, startup recovery resolves the Job to `CANCELLED`; it never becomes an automatic provider resume.
8. Legacy Jobs without `pipeline-control.json` are read as `AUTO_CONTINUE` for compatibility, and read-only control inspection does not create a new file.

### Normal UI

The intake page defaults to:

```text
发送前确认（推荐）
```

Before a batch has files, users may instead select:

```text
本地完成后自动继续
仅本地处理
```

Per-Job controls support:

- `批准云端审计` at a paused provider boundary;
- `发送前暂停` for not-yet-started future provider calls;
- `取消` / `取消审计`;
- explicit `重新开始` for cancelled Jobs.

The batch result page keeps cancelled/paused work visible and never converts these states into a legal-risk score.

### Regression coverage

Backend tests cover:

- local OCR/structure/rules plus local primary Evidence-context preparation before approval pause;
- `REQUIRE_APPROVAL` preventing outbound provider start;
- `LOCAL_ONLY` preventing outbound provider start;
- explicit approval/resume;
- cancel terminal state and generic-retry rejection;
- provider in-flight cancellation blocking the next provider;
- restart reconciliation from cancel-requested to cancelled;
- legacy control reads remaining non-mutating.

Frontend production build covers the new provider-policy selector and intake/result actions.

Clean Windows final-ZIP validation must additionally prove, without real provider keys or paid calls:

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

## Hard boundaries retained

- no private contract/API secret in Git or release bundles;
- no hidden provider call;
- no arbitrary thread kill as cancellation semantics;
- no claim that an already-started provider request can be unsent;
- no destructive cleanup of prior valid artifacts;
- no OCR/legal-corpus expansion in Stage 13A;
- public/default CI remains provider-free;
- Stage 11 quality gate and Stage 12 product regressions remain green.

## Current implementation boundary

Finish **Stage 13A Windows validation only**. If the clean-runner passes, mark 13A complete and proceed next to **13B Windows tray + graceful quit** as a separate iteration.