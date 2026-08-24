# Stage 19 — Limited Tester License

## Purpose

The `0.8.0-rc3-tester1` Windows build is for a small invited tester group. It adds an **offline signed tester license** to reduce casual redistribution and to preserve tester traceability without requiring a production Windows publisher certificate.

This mechanism is deliberately separate from Authenticode/code signing. Production signing remains deferred until a later public trusted release.

## What the license binds

Each license contains and cryptographically binds:

- `tester_id` — a unique tester alias such as `T001`;
- `release_label` — currently `0.8.0-rc3-tester1`;
- `not_before_utc` — earliest valid time;
- `expires_at_utc` — expiry time;
- a unique `license_id`;
- the fixed limited-test audience and schema version.

The payload is signed with Ed25519. The application contains only the public verification key:

```text
JYVGx5sCRLFW8PGLWiVZMwxM3QZx9bshcep0rH6uTKQ
```

The private issuing key must never be committed to GitHub or distributed to testers.

## First launch behavior

The packaged tester build forces the tester-license requirement itself. A tester cannot disable the gate merely by starting the EXE with an environment variable.

Before activation:

- the production SPA can load so the activation screen is visible;
- `/api/health` remains available for local diagnostics;
- `/api/tester-license/status` and `/api/tester-license/activate` remain available;
- every other `/api/*` endpoint is rejected with HTTP `423 Locked`.

The tester may select a `.license.txt` file or paste its `LR1...` token. Verification is local and checks the signature, release label and UTC validity window. No network request is needed to activate a license.

After successful activation, the token is stored under the existing user runtime root:

```text
%LOCALAPPDATA%\Law-Rag\runtime\tester-license\license.txt
```

Because runtime data is separate from application binaries, normal reinstall does not silently erase the activated license.

## Tester traceability

When a valid license is active:

- the workstation shows a persistent Tester ID watermark;
- exported DOCX reports receive the Tester ID in the document footer;
- exported PDF reports receive the Tester ID on every page;
- report-file SHA-256 evidence is recomputed after the watermark is written.

Example watermark:

```text
Law-Rag 0.8.0-rc3-tester1 · Tester T001 · Limited Test Build
```

## Owner: issue a tester license

Use the owner-only private key with the repository issuer. The private key path is an operator input and is never embedded into the output token.

Seven-day license:

```powershell
python .\release\new-tester-license.py `
  --private-key D:\private\law-rag-tester-license-private-key.pem `
  --tester-id T001 `
  --days 7 `
  --output .\T001.license.txt `
  --receipt .\T001.license.receipt.json
```

Different tester durations are independent parameters. For example `--days 3`, `--days 30`, or an explicit UTC expiry:

```powershell
python .\release\new-tester-license.py `
  --private-key D:\private\law-rag-tester-license-private-key.pem `
  --tester-id T002 `
  --expires-at 2026-09-15T12:00:00Z `
  --output .\T002.license.txt
```

Tester IDs may use letters, digits, `.`, `_` and `-`, up to 64 characters.

## What to send to a tester

Send only:

1. the `0.8.0-rc3-tester1` installer;
2. that tester's individual `.license.txt` file;
3. the normal tester instructions / feedback template.

Never send the private issuing key.

## Expiry and version mismatch

A license fails closed when:

- its Ed25519 signature is invalid;
- the signed payload was modified;
- the license is not valid yet;
- the license has expired;
- it was issued for another release label;
- required fields are malformed.

To extend a tester, issue a new license. Rebuilding the application is not necessary as long as the release label stays the same.

## Security boundary and limitation

This is an offline **limited-test access and traceability control**, not anti-piracy DRM.

A tester can still forward both their installer and their still-valid license file to another person. The forwarded copy will retain that tester's identity and expiry, so UI/report watermarks make the source attributable and the time window limits usefulness, but the current design does not bind a license to one physical machine.

That tradeoff is intentional for this small tester phase because machine binding would add hardware-change/reinstall support burden. A later distribution can add machine enrollment or an online license service if the threat model changes.

Offline time validation also relies on the local system clock. The signed expiry cannot be edited without invalidating the signature, but a determined user with control of the machine may manipulate local time. This tester mechanism should therefore be described as deterrence and traceability rather than tamper-proof DRM.

## Release truth

`0.8.0-rc3-tester1` is a new tester build with new binary hashes. It must not reuse the frozen Stage 19.4 RC3 installer/portable SHA values.

The Stage 19.4 exact unsigned candidate remains the engineering provenance baseline. The tester-license build is a later source transformation for invited testing only:

```text
distribution_scope = INVITED_TESTERS_ONLY
production_signer = DEFERRED
public_release = NOT_PUBLISHED
Final Acceptance = FINAL_ACCEPTANCE_PENDING
```
