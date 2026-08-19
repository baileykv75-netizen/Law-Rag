# Law-Rag Windows Portable Bundle

This bundle is an inspectable **one-folder** Windows x64 application distributed inside the Law-Rag portable ZIP. It is not an installer and not a single-file executable.

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
  -> drag one or more currently exposed PDF/JPG/PNG contracts onto the intake page
  -> streamed local upload + bounded local processing
  -> explicit provider boundary when required
  -> batch result landing page
  -> detailed evidence/review workstation only where needed
```

DOCX backend ingestion and Workspace source navigation exist in Stage 14, but Home/Pipeline product exposure remains Stage 14.6. Normal users do not need internal Stage controls. Manual troubleshooting controls remain under `/developer`.

### File intake

- multiple files may be queued in one intake batch;
- exact per-file limit: **500 MiB**;
- uploads are copied to local runtime in fixed chunks rather than loaded wholesale into memory;
- disk-space preflight and partial-file cleanup fail closed;
- browser uploads are sequential, while already-uploaded Jobs may process concurrently under bounded backend limits.

## Cloud/provider boundary controls

The application controls provider transmission rather than treating it as an automatic side effect of upload. The intake screen exposes three policies:

```text
发送前确认（推荐）
本地完成后自动继续
仅本地处理
```

The default normal-user policy is **发送前确认（推荐）**. Local document/OCR handling, canonical structure, deterministic rules and legal-evidence preparation may complete before the Job stops at the outbound provider boundary. No DeepSeek/Kimi generation call starts until the user explicitly approves where approval is required.

If an audit is waiting at a safe boundary or has stopped with a retryable failure, use the workstation's **继续 / 重试审计** action after reviewing the displayed state. A provider request that has already started cannot be recalled or made unsent. Persistent pause/cancel state is rechecked before later provider calls, and completed artifacts remain available for safe reuse after restart.

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
Law-Rag.exe --diagnose-ocr-runtime
Law-Rag.exe --diagnose-ocr-models
```

`--diagnose` is the general non-mutating local runtime check.

`--diagnose-ocr-runtime` verifies the **bundled** PaddlePaddle/PaddleOCR Python/native runtime and executes Paddle's local native self-check. It deliberately does not construct the OCR pipeline, call DeepSeek/Kimi or mutate contract data.

`--diagnose-ocr-models` verifies the packaged PP-OCRv6 medium detector/recognizer file set against the checked release manifest and SHA-256 values without running inference or making a network request.

## Included runtime capabilities

- CPython runtime collected by PyInstaller;
- PaddlePaddle CPU `3.3.0` runtime;
- PaddleOCR `3.7.0` + PaddleX `3.7.2` pinned runtime dependency closure;
- verified local `PP-OCRv6_medium_det` and `PP-OCRv6_medium_rec` model assets;
- fixed Law-Rag OCR pipeline configuration with document preprocessing/orientation helper models disabled;
- PDF/JPG/PNG intake currently exposed by Home;
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

### Offline OCR in Stage 14.5

Stage 14.5 packages the two approved PP-OCRv6 medium inference models directly in the portable onedir/ZIP. The detector and recognizer are fetched only during the controlled release build from locked official URLs, verified against the checked archive/file SHA-256 values, and then addressed by explicit local directories at runtime. Normal OCR inference does not use PaddleOCR/PaddleX model-download fallback.

Law-Rag also supplies its fixed PaddleX OCR pipeline YAML explicitly rather than relying on package-relative default configuration discovery. The frozen bundle preserves the distribution metadata PaddleX needs to validate its `ocr-core` dependency group.

For the pinned PaddlePaddle `3.3.0` Windows CPU runtime, Law-Rag disables the oneDNN/MKLDNN execution path for OCR inference and keeps the `paddle_static` CPU engine. This avoids the known Paddle 3.3 CPU oneDNN/PIR `ArrayAttribute<Double>` conversion regression while retaining the pinned Paddle/PaddleOCR/model versions.

The Stage 14.5 release smoke deliberately points HTTP/HTTPS/ALL proxy variables at an unusable local endpoint before running a synthetic image through the **frozen executable**. The OCR path must recognize the fixed smoke text from packaged local assets without downloading another model.

## Not bundled

```text
Paddle/PaddleOCR downloaded model caches beyond the two approved packaged models
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
user runtime/jobs
API keys
private benchmark data
```

## Local data

Private Jobs are written below the extracted bundle directory under:

```text
runtime/
```

This contains uploaded source files, Job artifacts, batch manifests, pipeline/control state and human-review history. API secret values are not stored there.

Do not delete `runtime/` as a first troubleshooting step. Full history/storage management and application-level at-rest contract encryption remain future work.

## Release metadata and third-party notices

The bundle includes reproducibility metadata, exact Python dependency records, Vite frontend license data and collected Python/PDFium/Paddle notices under `_internal/`. Release metadata fingerprints the base Windows dependency lock, the OCR runtime lock, the exact OCR model manifest and public legal/retrieval assets.

These files support release review; they are not an automatic declaration that every redistribution obligation has been legally satisfied.

The portable RC files remain:

```text
Law-Rag-0.8.0-rc2-windows-x64.zip
RC-MANIFEST.json
SHA256SUMS.txt
```

Stage 14.5 clean Windows validation builds the exact onedir, verifies Paddle/PaddleX dependency metadata, native files, model hashes and PDFium, rejects private/cache/unapproved-model payloads, runs frozen diagnostics and real OCR with external network proxies deliberately unusable, exercises native PDF/PDFium HTTP behavior, builds the deterministic RC ZIP, extracts that final ZIP into a fresh directory and reruns the packaged user-flow/provider-boundary smoke.

Public GitHub Release/tag publication remains a separate explicit owner decision.
