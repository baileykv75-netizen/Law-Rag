# Law-Rag 0.8.0-rc3 — Final Engineering Candidate Notes

## Purpose

RC3 is the final provider-free engineering candidate before external acceptance. It consolidates the product work completed after RC2 into one Windows candidate identity while keeping production signing, publication, private expert evidence, and paid DeepSeek/Kimi UAT explicitly pending.

RC3 is **not** a claim of production legal accuracy and is **not yet a published/signed public release**.

## Major changes since RC2

### Desktop lifecycle and local history

- Windows tray lifecycle with explicit Open/Quit behavior and graceful backend shutdown;
- persistent local Job history reconstructed from authoritative runtime artifacts;
- storage visibility and explicit UUID-confirmed cleanup for terminal Jobs;
- crash-recoverable cleanup transactions that protect shared `runtime/legal` data.

### Local data protection and export

- truthful Windows EFS policy for Job-private runtime roots: `OFF`, `AUTO`, `REQUIRED`;
- `AUTO` reports unsupported/degraded states instead of claiming encryption that is not present;
- `REQUIRED` fails closed before serving when protection cannot be verified;
- authoritative local DOCX/PDF report export from validated `ISSUE_V1` artifacts;
- report export never invokes OCR, retrieval, DeepSeek, Kimi, or another provider.

### Provider controls

- per-Job provider call/token/estimated-cost controls with a durable logical-call ledger;
- costs are local estimates from user-entered prices, not provider invoices;
- advanced non-secret provider runtime settings with bounded endpoint/timeout/retry validation;
- API keys remain outside ordinary runtime JSON and use environment/Windows Credential Manager boundaries;
- explicit outbound approval/cancellation semantics remain authoritative.

### Windows release lock

- exact Windows CPython 3.12.10 release lock and packaged dependency closure;
- packaged OCR/PDFium/report-renderer/runtime diagnostics;
- frozen three-domain corpus baseline and offline retrieval behavior;
- portable RC reproducibility metadata and third-party notice collection.

### Installer and update trust

- per-user Inno Setup installer under `%LOCALAPPDATA%\Programs\Law-Rag`;
- installed runtime under `%LOCALAPPDATA%\Law-Rag\runtime`;
- reinstall/uninstall preserves user runtime;
- truthful Authenticode publication gate: unsigned/untrusted candidates are refused;
- fail-closed safe-update candidate verification for version, HTTPS, exact bytes, SHA-256/size, detached CMS, Authenticode validity, and trusted signer agreement;
- no silent auto-update, background polling, or unsigned fallback.

## Legal/evaluation boundary

The authoritative production architecture remains `ISSUE_V1`. The frozen public legal baseline remains:

```text
Corpus Release  three-domain-core@1.0.0
READY Packs     3
Authorities     14
Versions        15
Unique Articles 1274
```

Public deterministic evaluation is engineering evidence only. It is not professional legal truth. Stage 16 external evidence intentionally remains incomplete until final acceptance provides both private expert evidence and an explicitly authorized real-provider UAT observation.

## RC3 engineering distribution

Stage 19.4 validates these exact candidate names:

```text
Law-Rag-0.8.0-rc3-windows-x64.zip
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

The portable manifest remains `NOT_PUBLISHED`, and the installer remains an unsigned validation candidate in normal CI. A production signer is never fabricated by Stage 19.4.

## Still pending before public release

- production release certificate/signing acceptance;
- final public release channel and update URL;
- private expert evidence;
- explicit paid/network DeepSeek + Kimi `ISSUE_V1` UAT;
- Stage 16 complete-evidence gate;
- final packaged Windows acceptance on the intended signed candidate;
- any owner decision on broader project-level licensing/public distribution.

These are release gates, not documentation footnotes, and must remain visible until completed.
