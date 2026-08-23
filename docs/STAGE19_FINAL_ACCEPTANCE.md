# Stage 19 Final Acceptance

## Purpose

Stage 19 Final Acceptance is the explicit evidence-closure phase after the Stage 19.4 RC3 engineering candidate.

The frozen engineering baseline is:

```text
source SHA
8c05ddd91712d5d9cdbdafe90e77cc9de03b8593

unsigned portable SHA-256
9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796

unsigned installer SHA-256
cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8
```

Stage 19.4 has already reached:

```text
engineering_state = READY_FOR_FINAL_ACCEPTANCE
publication_state = FINAL_ACCEPTANCE_PENDING
```

Final Acceptance must not reinterpret that state as permission to merge, sign, call providers, consume private evidence, or publish.

## Required gates

Final Acceptance is complete only when all of these independently pass:

1. `ENGINEERING_BASELINE`
2. `PRODUCTION_SIGNING`
3. `RELEASE_CHANNEL`
4. `PRIVATE_EXPERT`
5. `REAL_PROVIDER_UAT`
6. `STAGE16_COMPLETE_EVIDENCE`
7. `FINAL_WINDOWS_SMOKE`

The verifier reports `FINAL_ACCEPTANCE_PENDING` while any required evidence is absent, `FINAL_ACCEPTANCE_FAILED` when supplied evidence is invalid/failed, and `FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED` only when every gate passes.

Even `FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED` is not a publication action.

## Signed-distribution transformation

Authenticode signing changes PE bytes. Therefore the Stage 19.4 hashes identify the **unsigned engineering baseline**, not the later signed distribution bytes.

The intended final transformation is deliberately narrow:

```text
exact retained Stage 19.4 portable
 -> extract exact onedir
 -> externally sign Law-Rag.exe with the authorized production signer
 -> repackage that signed onedir using the existing deterministic/privacy-scanning RC packager
 -> build the installer from that same signed onedir
 -> externally sign the installer with the same production signer
 -> run final Windows smoke
```

Do not rebuild the application between the engineering baseline and production signing. A fresh PyInstaller build would be a different engineering candidate.

`smoke-stage19-final-windows.ps1` requires both the exact unsigned Stage 19.4 portable and the signed portable. It proves:

- the unsigned input matches the frozen Stage 19.4 portable SHA-256;
- signed and unsigned portable file lists are identical;
- every file except `Law-Rag.exe` is byte-for-byte identical;
- `Law-Rag.exe` is the only changed portable path;
- signed `Law-Rag.exe` has valid Authenticode under the explicitly expected signer;
- signed installer has valid Authenticode under that same signer;
- installer installation produces the exact same signed `Law-Rag.exe` SHA-256 as the signed portable;
- install/reinstall/uninstall preserves the established runtime ownership rules;
- packaged runtime/user-flow/provider-boundary smoke passes with provider API keys removed.

This prevents a different application build from being substituted merely because it has a valid certificate.

## Packaging the already-signed onedir

`package-rc.ps1` retains its historical defaults but now accepts explicit `-BundleDir` and `-PythonPath` inputs. Final signing work can therefore package the extracted/signed Stage 19.4 onedir instead of rebuilding the application.

`build-installer.ps1` already accepts an explicit `-BundleDir` and now also accepts `-EvidenceSourceSha`, allowing installer-build evidence to stay bound to `8c05ddd91712d5d9cdbdafe90e77cc9de03b8593` even when the acceptance tooling itself lives on a later scaffold commit.

`verify-stage19-2-signing.ps1` likewise accepts `-EvidenceSourceSha`. It remains verification-only: it never performs the signing operation.

## Production signing boundary

The repository does not fabricate or import a production certificate. The scripts in this scaffold do not sign files.

After an authorized external signing operation has produced the signed onedir and signed installer, run the existing Authenticode verifier with:

```text
EvidenceSourceSha = 8c05ddd91712d5d9cdbdafe90e77cc9de03b8593
RequirePublishable = true
```

A publishable signing result requires both `Law-Rag.exe` and the installer to be `Valid` and to match the explicitly configured production-signer thumbprint.

## Stage 16 evidence boundary

Stage 16 remains the authority for external evaluation evidence.

A complete Stage 16 matrix must preserve:

```text
schema_version    1.0.0
evaluator_version stage16e-1.0.0

PUBLIC_REGRESSION PASS
PRIVATE_EXPERT    PRESENT
REAL_PROVIDER_UAT PASS
```

and `stage16_evidence_complete=true` with no pending evidence classes.

Private expert evidence must remain external or under ignored `benchmark_private/` paths and must come from the existing Stage 16.3 professional benchmark protocol.

Real-provider UAT must come from an explicitly authorized production `ISSUE_V1` DeepSeek/Kimi run followed by the existing read-only Stage 16.4 capture path. The Final Acceptance verifier never invokes DeepSeek, Kimi, OCR, or another paid/network provider.

No combination of model agreement, public regression, or synthetic CI is converted into a global `legal_accuracy` score.

## Release channel boundary

The final release channel and publication URL are explicit owner inputs. The verifier requires an absolute HTTPS publication URL before the channel gate can pass.

Recording the URL is not publication. No script in this scaffold creates a GitHub Release, uploads a public release asset, changes an update channel, or performs unattended publication.

## Final verifier

`verify-stage19-final-acceptance.ps1` is evidence-only and fail-closed.

Without external evidence it should report:

```text
FINAL_ACCEPTANCE_PENDING
```

With `-RequireComplete`, the same incomplete state exits non-zero.

Supplied invalid or contradictory evidence produces:

```text
FINAL_ACCEPTANCE_FAILED
```

Only all-pass evidence produces:

```text
FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED
```

The output explicitly records that the verifier itself executed zero signing actions, zero provider calls, zero private-expert evaluation actions, and zero publication actions.

## Current status

The engineering baseline and Final Acceptance tooling can be validated in ordinary CI.

The following remain intentionally outside ordinary CI and are still pending until separately authorized/performed:

- production Authenticode signing;
- final release channel/publication URL decision;
- real private expert evidence;
- real paid/network DeepSeek + Kimi `ISSUE_V1` UAT;
- Stage 16 complete-evidence closure;
- final signed-distribution Windows smoke.

No missing gate may be inferred from synthetic fixtures or relabeled as complete.
