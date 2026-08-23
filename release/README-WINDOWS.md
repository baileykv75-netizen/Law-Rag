# Law-Rag for Windows

Law-Rag is a local-first Windows x64 contract-audit workstation. The browser UI communicates only with the local Law-Rag backend bound to loopback by default.

Stage 19.4 validates two RC3 engineering distribution forms:

```text
portable:  Law-Rag-0.8.0-rc3-windows-x64.zip
installer: Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

The RC3 engineering candidate is not yet production-signed or publicly published. Final signing/publication remains a separate acceptance gate.

## Start and quit

Portable mode:

1. extract the ZIP into a normal writable folder;
2. double-click `Law-Rag.exe`.

Installed mode:

1. run the per-user installer;
2. start Law-Rag from the Start Menu or optional desktop shortcut.

Law-Rag opens the workstation in the default browser at:

```text
http://127.0.0.1:8000/
```

The Windows tray provides **Open Law-Rag** and **Quit Law-Rag**. Quit requests graceful backend shutdown. Closing a browser tab alone does not terminate the local application.

Node.js, npm, Vite, or a separately installed Python runtime are not required by the packaged application.

## Normal workflow

```text
configure DeepSeek / Kimi once, or choose local-only
 -> choose the outbound provider policy
 -> add PDF / JPG / JPEG / PNG / DOCX contracts
 -> local source evidence + OCR when required
 -> canonical structure + deterministic rules
 -> issue planning + legal retrieval
 -> explicit provider boundary
 -> DeepSeek primary + Kimi secondary when authorized
 -> deterministic comparison
 -> append-only human review
 -> local DOCX/PDF report export
```

The application remains usable for supported local work without provider keys. Navigation, history, workspace reading, source viewing, human review, storage management, and report export do not implicitly call DeepSeek or Kimi.

## Provider and privacy boundary

Saved desktop API keys use Windows Credential Manager. Development/CI environment variables remain supported:

```text
DEEPSEEK_API_KEY
MOONSHOT_API_KEY
```

Secret values are not returned to the browser, written to ordinary provider runtime JSON, or included in release metadata.

Non-secret provider settings may configure the supported model identity, endpoint root, bounded timeouts, bounded transient retry attempts, and retry backoff. Endpoints require HTTPS except loopback-only local development. Embedded credentials, query strings, fragments, and direct `/chat/completions` paths are rejected.

The default product policy requires an explicit outbound approval where configured. A request already sent to an external provider cannot be recalled. Provider navigation/read operations never silently create a request.

## Provider resource controls

A Job may optionally define limits for provider logical calls, reported token usage, and locally estimated cost. No limit means historical unlimited behavior.

Token and cost limits are truthful continuation limits based on provider-reported usage. Unknown usage is never treated as zero. Cost values use only user-entered prices and are not represented as DeepSeek/Kimi invoices.

## Local evidence, corpus, and reports

The bundled legal baseline is a versioned three-domain corpus release, not complete Chinese law. A no-hit result must never be interpreted as proof that no relevant rule exists.

Legal reasoning retains Authority -> Version -> Article / Legal Evidence identity. The `ISSUE_V1` pipeline keeps Contract Evidence and Legal Evidence traceability through primary review, secondary review, deterministic comparison, human review, and exported DOCX/PDF reports.

Semantic BGE retrieval remains optional. Exact citation and lexical/BM25 retrieval remain available without it.

## OCR

The packaged Windows release includes the approved local PP-OCRv6 medium detector and recognizer together with the pinned Paddle runtime. OCR inference uses packaged local assets rather than normal model-download fallback.

Diagnostics include:

```text
Law-Rag.exe --diagnose
Law-Rag.exe --diagnose --json
Law-Rag.exe --diagnose-ocr-runtime
Law-Rag.exe --diagnose-ocr-models
Law-Rag.exe --diagnose-corpus --json
Law-Rag.exe --diagnose-report-export-runtime
Law-Rag.exe --diagnose-desktop-lifecycle --json
Law-Rag.exe --diagnose-installation-layout
```

Diagnostics must not expose API keys or Authorization headers.

## Local data locations

Portable mode keeps the historical adjacent runtime default:

```text
<extracted Law-Rag folder>\runtime
```

Installed mode separates application binaries from user data:

```text
application: %LOCALAPPDATA%\Programs\Law-Rag
runtime:     %LOCALAPPDATA%\Law-Rag\runtime
```

`LAW_RAG_RUNTIME_DIR` remains an explicit operator/test override.

Reinstall and uninstall preserve the installed user runtime. Removing the application does not mean deleting local audit history/contracts. Use Law-Rag's History/Storage controls for explicit terminal-Job cleanup.

## At-rest protection

Job-private Windows runtime roots support the EFS policy:

```text
OFF
AUTO
REQUIRED
```

`AUTO` is truthful: it encrypts where Windows/filesystem EFS is genuinely available and reports `UNSUPPORTED` or `DEGRADED` otherwise. `REQUIRED` fails closed before exposing the local server when protection cannot be verified.

Shared public legal assets under `runtime/legal` are outside the Job-private EFS management boundary. API keys remain separately protected by the provider-secret mechanism.

## Safe updates

Stage 19.3 defines a fail-closed candidate verification boundary. An update candidate is eligible only when version, HTTPS URL, exact filename/size/SHA-256, detached CMS signature, Authenticode validity, and trusted signer identity all agree.

There is no unsigned fallback, signer substitution, HTTP fallback, same/older-version acceptance, background polling, unattended download, or silent installer execution in Stage 19.3/19.4.

The final public update channel and publication URL are owner/final-acceptance decisions.

## Release metadata and notices

Packaged artifacts include reproducibility metadata, dependency inventories, OCR model manifests, frontend license metadata, and collected Python/PDFium/Paddle notice material where exposed by the pinned distributions.

These records support release review; they are not an automatic legal conclusion that every redistribution obligation is satisfied. Project-level licensing/public-distribution decisions remain explicit owner review items.

## RC3 acceptance status

Stage 19.4 may conclude only:

```text
engineering: READY_FOR_FINAL_ACCEPTANCE
publication: FINAL_ACCEPTANCE_PENDING
```

Before a broader public release, final acceptance still requires the real production signing/publication decision, private expert evidence, explicit paid/network DeepSeek + Kimi UAT, Stage 16 complete-evidence closure, and a final packaged Windows acceptance run on the intended distribution candidate.
