# Law-Rag 0.8.0-rc3-tester2 — Licensed Tester Distribution

## Scope

This Windows build is for invited testers only. It is a new unsigned tester binary produced after real tester1 Windows findings. It does **not** replace the frozen Stage 19.4 engineering baseline, is not a public trusted release, and does not complete Stage 19 Final Acceptance.

Each tester receives only:

1. `Law-Rag-0.8.0-rc3-tester2-windows-x64-setup.exe`;
2. one tester-specific `*.license.txt` issued for `0.8.0-rc3-tester2`;
3. this guide and `TESTER-FEEDBACK.md`.

Never distribute the owner private signing key. A tester1 license is intentionally rejected by tester2.

## Verify and install

Verify the installer against `SHA256SUMS-TESTER2.txt` before running it:

```powershell
(Get-FileHash -Algorithm SHA256 '.\Law-Rag-0.8.0-rc3-tester2-windows-x64-setup.exe').Hash.ToLowerInvariant()
```

The value must match exactly. The build is intentionally not Authenticode-signed, so Windows may show Unknown Publisher / SmartScreen. Do not disable SmartScreen globally.

The application installs for the current Windows user under:

```text
%LOCALAPPDATA%\Programs\Law-Rag
```

Runtime/test data is stored separately under:

```text
%LOCALAPPDATA%\Law-Rag\runtime
```

## First launch and tester license

Before activation, only health and tester-license APIs are available; protected `/api/*` endpoints remain locked with HTTP 423. Load the tester-specific `.license.txt` file or paste the `LR1...` token.

Validation is offline and checks:

- Ed25519 signature;
- Tester ID;
- exact `0.8.0-rc3-tester2` release binding;
- not-before time;
- expiry time.

A valid activation shows the Tester ID watermark in the application and exported reports. The access mechanism is traceability/deterrence, not machine-bound DRM.

## Tester2 regression focus

Tester2 specifically targets defects observed during tester1 manual use. Verify these behaviors rather than only checking that the application launches.

### A. Batch stability

Import a mixed batch when possible (PDF/DOCX/scanned PDF/image). During processing:

- one transient status read must not permanently turn a contract red;
- local state writes must not fail with `AtomicWriteError` under normal batch use;
- a recoverable external-model outage must appear as a waiting/retry state, not a legal/audit failure;
- retry must reuse completed OCR/structure/rules/model checkpoints where valid;
- corrupt historical Jobs must not inflate the valid-contract count.

For the main tester2 stress pass, use ten non-sensitive synthetic/test contracts in one batch if the machine has enough resources. Record the final counts and any task that does not reach a stable terminal/waiting state.

### B. Results navigation

Opening the global Results page without a `batch` query parameter must resolve the most recent useful batch or show a friendly empty state. It must not expose `缺少批次编号` as a normal user error.

### C. Offline OCR

1. Disconnect network access.
2. Keep provider calls disabled/not approved.
3. Import a scanned PDF or JPG/PNG that genuinely requires OCR.
4. Confirm no model download is requested.
5. Confirm page-level progress changes while OCR runs instead of remaining indefinitely at one percentage.
6. Confirm OCR completes with packaged Paddle/PaddleOCR/PP-OCRv6 assets and the text can continue into local processing.

The OCR runtime is process-shared in tester2 so later scanned documents should not pay full model initialization cost again during the same application session.

### D. Provider recovery

With tester-owned provider credentials only, verify normal cloud review. If a transient provider/network problem occurs naturally, record it. Tester2 should preserve completed checkpoints and move the task to a recoverable waiting state. Do not deliberately attack or overload provider services.

### E. Report export

DOCX export is mandatory once a Job is export-ready:

- output is non-empty and opens normally;
- no obvious corruption/garbling/major layout breakage;
- footer shows the correct Tester ID.

If PDF export is offered, verify it also opens and every checked page carries the Tester ID watermark.

## Security / product truth

System failures, provider outages, old corrupt Jobs, and OCR/runtime errors are **not legal findings**. Only completed contract review results belong in legal-risk statistics.

Current truth state:

```text
release_label       = 0.8.0-rc3-tester2
distribution_scope  = INVITED_TESTERS_ONLY
tester_license      = REQUIRED_OFFLINE_SIGNED
production_signer   = DEFERRED
public_release      = NOT_PUBLISHED
Final Acceptance    = FINAL_ACCEPTANCE_PENDING
```

Tester2 has new source and binary hashes. Do not compare its installer hash to tester1 or the frozen Stage 19.4 candidate as if the files were byte-identical.
