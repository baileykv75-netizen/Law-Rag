# Law-Rag Windows Portable Bundle

This bundle is an inspectable **one-folder** Windows x64 application distributed inside the Law-Rag `0.8.0-rc2` portable ZIP. It is not an installer and not a single-file executable.

## Start

Double-click:

```text
Law-Rag.exe
```

The normal double-click path hides Law-Rag's own console window. The local FastAPI process continues running in the background and the default browser opens Law-Rag.

Closing the browser tab does **not** stop the local process. A dedicated tray/quit control is still pending, so use Task Manager if you need to stop Law-Rag completely. When launched from an existing PowerShell/CMD window, that console remains available for diagnostics.

The launcher binds only to:

```text
http://127.0.0.1:8000/
```

The browser UI and FastAPI backend are served from the same local process. Node.js, npm, Vite and a separately installed Python runtime are not required on the end-user machine.

## Normal workflow

```text
first-run DeepSeek / Kimi setup (or explicit local-only skip)
  -> choose cloud policy
  -> drag one or more PDF/JPG/PNG contracts onto the intake page
  -> streamed local upload + bounded local processing
  -> explicit provider boundary when required
  -> batch result landing page
  -> detailed evidence/review workstation only where needed
```

Normal users do not need internal Stage controls. Manual troubleshooting controls remain under `/developer`.

### File intake

- multiple files may be queued in one intake batch;
- exact per-file limit: **500 MiB**;
- uploads are copied to local runtime in fixed chunks rather than loaded wholesale into memory;
- disk-space preflight and partial-file cleanup fail closed;
- browser uploads are sequential, while already-uploaded Jobs may process concurrently under bounded backend limits.

## Cloud/provider boundary controls

Stage 13A makes provider transmission application-controlled rather than an automatic side effect of upload. The intake screen exposes three policies:

```text
发送前确认（推荐）
本地完成后自动继续
仅本地处理
```

The default normal-user policy is **发送前确认（推荐）**.

With that policy, Law-Rag first runs available local work, including document/OCR handling, canonical structure, deterministic rules and construction of the local legal-retrieval/evidence context. The Job then stops at:

```text
PAUSED_BEFORE_PROVIDER
PROVIDER_APPROVAL_REQUIRED
```

No DeepSeek/Kimi generation call starts until the user explicitly approves cloud auditing for that Job.

`仅本地处理` stops at the same outbound boundary with `LOCAL_ONLY_PROVIDER_DISABLED`. The user can later explicitly approve the Job if cloud review is desired.

`本地完成后自动继续` preserves the older automatic-provider behavior for users who deliberately choose it.

### Pause and cancel semantics

Every DeepSeek/Kimi generation call rechecks persistent provider/cancel state immediately before the outbound request. The application records which provider has actually crossed that boundary.

Users can:

- change not-yet-started provider work to `发送前暂停`;
- approve a paused Job;
- cancel a queued/local/paused Job;
- request cancellation while a provider call is already in flight;
- explicitly restart a cancelled Job.

A crucial limitation is shown explicitly in the UI: **a provider request that has already started cannot be recalled or made unsent**. If cancellation occurs after that boundary, Law-Rag records the request as in flight, waits for the current call to return, and prevents subsequent provider/stage execution. A cancelled Job never resumes merely because the application restarts.

Cancelled state and cloud policy are persisted separately from ordinary progress so a worker cannot overwrite user intent with stale progress writes.

## Background processing and restart behavior

Progress comes from real upload bytes and persisted pipeline milestones. If OCR/provider configuration is missing, provider approval is pending, a Job is cancelled, or a stage fails, that Job remains visible independently of its siblings.

Closing/restarting Law-Rag never silently continues a process-local provider task. Prior transient `QUEUED/RUNNING/WAITING_WORKER` work becomes explicit retry-required state. A persisted cancellation request becomes `CANCELLED`. Already completed local/model artifacts remain available for safe reuse.

If a Job is interrupted rather than cancelled, reopen its results and use `继续 / 重试审计`. Cancelled Jobs use the separate explicit restart action and retain their original cloud policy.

## Batch results

Each intake session has a local batch ID. Its manifest stores Job IDs/timestamps only; it does not duplicate contract text into another result database.

The result page keeps complete, processing, waiting-for-provider/configuration, cancelled, failed and invalid Jobs visible. Ordering prioritizes human-review requirements, material disagreement/more-evidence states, serious risks and possible omissions. This is **not** a correctness or legal-validity score.

Complete Jobs open the existing evidence-level workstation with contract Evidence, Legal Evidence, separate DeepSeek/Kimi opinions, deterministic comparison, Agent trace and append-only human-review history.

## First-run DeepSeek / Kimi configuration

The normal Windows UI provides password-style fields for:

```text
DeepSeek API Key
Kimi / Moonshot API Key
```

Saved desktop secrets are stored as **Generic Credentials in Windows Credential Manager**, not plaintext `.env` or ordinary runtime JSON. Law-Rag never returns saved secret values to the browser or repopulates them into input fields.

Development/CI environment variables remain supported and take precedence:

```text
DEEPSEEK_API_KEY
MOONSHOT_API_KEY
```

Explicit connection testing sends only a fixed tiny non-contract message. Users may skip provider setup and continue local-only work. No API key is embedded in the bundle.

## Diagnose without starting

Run from PowerShell/CMD:

```text
Law-Rag.exe --diagnose
Law-Rag.exe --diagnose --json
```

Diagnostics are local and non-mutating. They do not call DeepSeek/Kimi, download OCR/BGE models, rebuild databases, or print API key values.

## Included base capabilities

- PDF/JPG/PNG intake;
- **500 MiB** guarded streamed upload path;
- native PDF extraction and PDFium rendering;
- deterministic contract structure and rules;
- curated versioned legal seed compiled into `legal.db`;
- exact + lexical/BM25 legal retrieval;
- DeepSeek primary / Kimi secondary adapters;
- Windows Credential Manager provider-secret onboarding;
- persistent background pipeline and bounded batch scheduler;
- persistent provider-boundary/pause/cancel state;
- batch result landing and restart recovery;
- professional evidence workstation;
- runtime/integrity diagnostics.

The bundled legal seed remains `CURATED_EXCERPT`, not a complete statement of Chinese law. A no-hit result cannot be interpreted as absence of a legal rule.

## Not included in the base bundle

```text
PaddleOCR / PaddlePaddle
OCR model weights
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
```

Therefore scanned/image-only contracts are not yet zero-setup. OCR-required Jobs stop at the explicit optional-component boundary rather than silently producing a low-quality audit.

## Local data

Private Jobs are written below the extracted bundle directory under:

```text
runtime/
```

This contains uploaded source files, Job artifacts, batch manifests, pipeline/control state and human-review history. API secret values are not stored there.

Do not delete `runtime/` as a first troubleshooting step. Full history/storage management and application-level at-rest contract encryption remain future work.

## Release metadata and third-party notices

The bundle includes reproducibility metadata, exact Python dependency records, Vite frontend license data and collected Python/PDFium notices under `_internal/`. These support release review; they are not an automatic declaration that every redistribution obligation has been legally satisfied.

The current portable RC files remain:

```text
Law-Rag-0.8.0-rc2-windows-x64.zip
RC-MANIFEST.json
SHA256SUMS.txt
```

Clean Windows validation extracts the final ZIP and runs base runtime/PDFium checks, the Stage 12 user-flow smoke, and the Stage 13A provider-boundary pause/cancel/resume smoke without real provider keys or paid calls.

Public GitHub Release/tag publication remains a separate explicit owner decision.