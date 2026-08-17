# Law-Rag Windows Portable Bundle

This bundle is an inspectable **one-folder** Windows x64 application distributed inside the Law-Rag `0.8.0-rc2` portable ZIP. It is not an installer and not a single-file executable.

## Start

Double-click:

```text
Law-Rag.exe
```

The normal double-click path intentionally hides Law-Rag's own console window. The local FastAPI process continues running in the background and the default browser opens Law-Rag.

Closing the browser tab does **not** stop the local process. RC2 still has no dedicated tray/quit control, so use Task Manager if you need to stop Law-Rag completely. This is a known desktop-lifecycle limitation rather than an installer requirement.

When `Law-Rag.exe` is launched from an existing PowerShell/CMD window, that existing console remains available for diagnostics and command-line output.

The launcher binds only to:

```text
http://127.0.0.1:8000/
```

The browser UI and FastAPI backend are served from the same local process. Node.js, npm, Vite and a separately installed Python runtime are not required on the end-user machine.

## Normal RC2 workflow

The intended user path is:

```text
first-run DeepSeek / Kimi setup (or explicit local-only skip)
  -> drag one or more PDF/JPG/PNG contracts onto the simple intake page
  -> streamed local upload + bounded background processing
  -> batch result landing page
  -> open the detailed evidence/review workstation only where needed
```

Normal users do not need to operate the internal Stage buttons. The legacy manual controls remain available at `/developer` for troubleshooting.

### File intake

- multiple files may be queued in one intake batch;
- the exact per-file limit is **500 MiB**;
- uploads are copied to the local runtime in fixed chunks rather than loaded wholesale into application memory;
- disk-space preflight and partial-file cleanup remain fail-closed;
- browser uploads are sequential by design, while already-uploaded Jobs can process concurrently under bounded backend resource limits.

### Background processing

For a supported contract, the application-owned pipeline performs the required local stages and then the configured provider stages automatically. Progress shown in the UI comes from real upload bytes and persisted pipeline milestones.

If OCR or provider configuration is missing, or a stage fails, that Job remains visible and can be retried independently. Closing/restarting Law-Rag never silently continues a process-local provider task: any transient `QUEUED/RUNNING/WAITING_WORKER` state left by the prior process is converted to an explicit retry-required state. Already completed artifacts remain available for reuse.

### Batch results

Each intake session gets a local batch ID. The batch manifest stores Job IDs/timestamps only; it does not copy contract text into a second result database.

The result page prioritizes:

- human-review-required contracts;
- material model disagreement / more-evidence states;
- critical/high/medium risk findings;
- possible primary-review omissions.

This priority order is **not** a correctness score or legal-validity score. Open a contract's detailed workstation to inspect its contract Evidence, Legal Evidence, DeepSeek/Kimi opinions, deterministic comparison, Agent trace and human-review history.

The latest useful batch remains discoverable after restarting the application. Empty intake batches do not replace the latest useful batch pointer.

## First-run DeepSeek / Kimi configuration

The normal Windows UI provides password-style fields for:

```text
DeepSeek API Key
Kimi / Moonshot API Key
```

Saved desktop secrets are stored as **Generic Credentials in Windows Credential Manager**, not as plaintext `.env` files or ordinary runtime JSON. Law-Rag never returns the saved secret value to the browser and does not repopulate it into the input box.

Development/CI environment variables remain supported and take precedence:

```text
DEEPSEEK_API_KEY
MOONSHOT_API_KEY
```

Connection testing is explicit and sends only a fixed tiny non-contract test message. It does not send a contract, filename, Evidence package or audit context. A connection test can still consume a very small amount of provider API usage.

Users may choose `暂时跳过，仅使用本地功能`. Local upload/extraction/rules/legal inspection remain available, while the automatic full pipeline will stop at the provider boundary until the missing provider is configured.

No API key is embedded in the bundle.

## Diagnose without starting

Run these from PowerShell or CMD so diagnostic output remains visible:

```text
Law-Rag.exe --diagnose
Law-Rag.exe --diagnose --json
```

Diagnostics are local and non-mutating. They do not call DeepSeek/Kimi, download OCR/BGE models, rebuild databases, or print API key values.

## Included base capabilities

RC2 includes the stable native-PDF/base workflow:

- PDF/JPG/PNG intake;
- 500 MiB guarded streamed upload path;
- native PDF extraction and PDFium page rendering;
- deterministic contract structure and rules;
- checked-in public curated legal seed compiled into `legal.db`;
- exact + lexical/BM25 legal retrieval;
- DeepSeek primary / Kimi secondary provider adapters;
- protected Windows provider-secret onboarding;
- persistent background pipeline and bounded batch scheduler;
- persistent batch result landing and restart/retry recovery;
- professional workstation and Evidence navigation;
- local runtime/integrity diagnostics.

The bundled legal seed remains a `CURATED_EXCERPT`, not a complete statement of Chinese law. A no-hit result cannot be interpreted as absence of a legal rule.

## Not included in the base RC

These remain optional external/local extensions:

```text
PaddleOCR / PaddlePaddle
OCR model weights
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
```

Therefore **scanned/image-only contracts are not yet a zero-setup RC2 workflow**. They can be accepted by intake, but OCR-required Jobs will wait for the optional OCR runtime instead of silently producing a low-quality audit. Native-text PDF workflows remain available without those components.

## Local data

Private jobs are written below the extracted bundle directory at:

```text
runtime/
```

This includes uploaded source files, per-Job audit artifacts, human-review history, provider-setup completion state and batch manifests. API secret values are not stored there.

Extract the RC into a normal writable user folder. The packaged public `legal.db` and lexical `retrieval.db` live separately inside the application data collected by PyInstaller; they are not user job data.

RC2 does not yet provide a graphical batch-history cleanup/storage-management screen. Do not delete `runtime/` as a first troubleshooting step because it contains the user's local contracts and audit history.

## Troubleshooting

If the application does not start, open PowerShell/CMD in the extracted folder and run:

```text
Law-Rag.exe --diagnose
```

Runtime diagnostics surface missing/stale/corrupt components without destructive auto-repair.

If the application was closed while a Job was actively processing, reopen its batch results and use `继续 / 重试审计`. The application intentionally does not auto-resume external model work after restart.

## Release metadata and third-party notices

The bundle includes:

```text
python-runtime.json
python-resolved.txt
_internal/release/release-metadata.json
_internal/release/public-assets-metadata.json
_internal/release/dependency-inventory.json
_internal/frontend-dist/third-party-frontend-licenses.json
_internal/THIRD-PARTY-NOTICES/python-third-party-notices.json
_internal/THIRD-PARTY-NOTICES/python/<package>/...
```

`release-metadata.json` records the source commit, application/toolchain versions, lock/inventory fingerprints and bundled public legal/retrieval fingerprints without a wall-clock build timestamp or private local path.

The Python notice set is generated from the exact isolated Windows release environment. The build fails if the installed pypdfium2 wheel does not expose PDFium/dependency license material for collection.

The frontend license JSON is generated by Vite from the actual locked production dependencies.

These files support reproducibility and dependency/license review. Their presence is evidence for release review, not an automatic legal conclusion that every redistribution obligation has been satisfied.

## RC files outside this folder

Stage 12F packages this folder into:

```text
Law-Rag-0.8.0-rc2-windows-x64.zip
RC-MANIFEST.json
SHA256SUMS.txt
```

The final ZIP is independently extracted and smoke-tested in a clean Windows runner before it is retained as an RC artifact. The Stage 12F smoke covers protected provider setup, a provider-free background pipeline, >50 MiB packaged upload, persistent batch/results, simulated interrupted-work recovery, explicit retry, PDFium rendering, private-data scanning and restart recovery.

Public GitHub Release/tag publication remains a separate explicit owner decision.
