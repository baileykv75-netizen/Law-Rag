# Stage 19 Final Acceptance Operator Runbook

## Scope

This is the execution handoff for the already-frozen Stage 19 Final Acceptance scaffold.

It does **not** authorize any external action. It separates provider-free/evidence-only steps from actions that require separate owner authorization.

Frozen engineering baseline:

```text
source SHA
8c05ddd91712d5d9cdbdafe90e77cc9de03b8593

source workflow run
32629468653

source artifact ID
9490770536

retained artifact ID
9491794952

unsigned portable SHA-256
9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796

unsigned installer SHA-256
cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8
```

The retained artifact is preserved through `2026-11-21T10:29:51Z`.

## 0. Generate a provider-free operator plan

This step performs no signing, provider call, private-expert evaluation or publication.

With owner inputs still undecided:

```powershell
./release/new-stage19-final-operator-plan.ps1
```

With structurally known owner inputs:

```powershell
./release/new-stage19-final-operator-plan.ps1 `
  -ExpectedSignerThumbprint '<PRODUCTION_SIGNER_THUMBPRINT>' `
  -ReleaseChannel '<RELEASE_CHANNEL>' `
  -PublicationUrl 'https://<HOST>/<PATH>/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -RequireOwnerInputs
```

`OWNER_INPUTS_STRUCTURALLY_VALID` is **not authorization**. The plan deliberately records `authorization_state=NOT_EVALUATED_BY_THIS_SCRIPT`.

---

## 1. SAFE / PRE-AUTH — recover and verify the exact engineering baseline

Use either the original Stage 19.4 artifact (`9490770536`) or the retained archival copy (`9491794952`). Do not rebuild the application.

Required candidate files include:

```text
Law-Rag-0.8.0-rc3-windows-x64.zip
RC-MANIFEST.json
SHA256SUMS.txt
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
STAGE19-1-INSTALLER-EVIDENCE.json
STAGE19-4-SIGNING-EVIDENCE.json
STAGE19-4-FINAL-PACKAGE-EVIDENCE.json
```

Before doing anything else, independently verify:

```powershell
(Get-FileHash -Algorithm SHA256 '<BASELINE_DIR>/Law-Rag-0.8.0-rc3-windows-x64.zip').Hash.ToLowerInvariant()
# must equal:
# 9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796

(Get-FileHash -Algorithm SHA256 '<BASELINE_DIR>/Law-Rag-0.8.0-rc3-windows-x64-setup.exe').Hash.ToLowerInvariant()
# must equal:
# cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8
```

Also verify that `STAGE19-4-FINAL-PACKAGE-EVIDENCE.json` records:

```text
source_sha        = 8c05ddd91712d5d9cdbdafe90e77cc9de03b8593
engineering_state = READY_FOR_FINAL_ACCEPTANCE
publication_state = FINAL_ACCEPTANCE_PENDING
```

Any mismatch means stop. Do not continue from a rebuilt or approximate candidate.

## 2. SAFE / PRE-AUTH — extract the exact unsigned portable

Extract:

```text
Law-Rag-0.8.0-rc3-windows-x64.zip
```

into a clean signing workspace, for example:

```text
<WORK>/unsigned/Law-Rag/
```

Copy that directory to:

```text
<WORK>/signed-onedir/Law-Rag/
```

Before signing, the copy must still be byte-identical to the extracted frozen portable.

---

## 3. AUTHORIZATION REQUIRED — Authenticode-sign `Law-Rag.exe`

This is the first production-signing boundary.

Only after separate authorization, use the approved production signing system to Authenticode-sign:

```text
<WORK>/signed-onedir/Law-Rag/Law-Rag.exe
```

Do not rebuild PyInstaller output and do not alter another portable file.

Immediately verify locally:

```powershell
Get-AuthenticodeSignature '<WORK>/signed-onedir/Law-Rag/Law-Rag.exe' | Format-List *
```

The signature must be `Valid` and the signer thumbprint must equal the explicitly authorized production signer.

---

## 4. SAFE AFTER SIGNING — repackage the signed onedir without rebuilding

Use the existing RC3 config, explicit signed bundle and the already-created release Python environment:

```powershell
./release/package-rc.ps1 `
  -Config ./release/stage19-4-rc-config.json `
  -BundleDir '<WORK>/signed-onedir/Law-Rag' `
  -PythonPath ./release/.build-venv/Scripts/python.exe `
  -Output '<WORK>/signed-rc'
```

Expected output:

```text
<WORK>/signed-rc/Law-Rag-0.8.0-rc3-windows-x64.zip
<WORK>/signed-rc/RC-MANIFEST.json
<WORK>/signed-rc/SHA256SUMS.txt
```

The new portable SHA-256 **must differ** from the unsigned Stage 19.4 portable hash because `Law-Rag.exe` now carries Authenticode data.

The embedded source SHA must remain:

```text
8c05ddd91712d5d9cdbdafe90e77cc9de03b8593
```

## 5. SAFE AFTER SIGNING — build installer from the exact same signed onedir

```powershell
./release/build-installer.ps1 `
  -BundleDir '<WORK>/signed-onedir/Law-Rag' `
  -OutputDir '<WORK>/signed-installer' `
  -ReleaseLabel '0.8.0-rc3' `
  -AppVersion '0.8.0' `
  -EvidenceSourceSha '8c05ddd91712d5d9cdbdafe90e77cc9de03b8593'
```

Expected unsigned-at-this-moment installer:

```text
<WORK>/signed-installer/Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

The installer is built from the same already-signed `Law-Rag.exe`; no application rebuild occurs.

---

## 6. AUTHORIZATION REQUIRED — Authenticode-sign the installer

Only after separate authorization, use the same approved production signer to sign:

```text
<WORK>/signed-installer/Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

Verify that the installer Authenticode status is `Valid` and the signer thumbprint is identical to the signed `Law-Rag.exe` signer.

## 7. SAFE AFTER SIGNING — produce production-signing evidence

```powershell
./release/verify-stage19-2-signing.ps1 `
  -BundleDir '<WORK>/signed-onedir/Law-Rag' `
  -InstallerPath '<WORK>/signed-installer/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -EvidencePath '<WORK>/evidence/STAGE19-FINAL-SIGNING-EVIDENCE.json' `
  -ExpectedSignerThumbprint '<PRODUCTION_SIGNER_THUMBPRINT>' `
  -EvidenceSourceSha '8c05ddd91712d5d9cdbdafe90e77cc9de03b8593' `
  -RequirePublishable
```

This verifier does not sign. It must report both executable and installer as `Valid` under the expected signer.

## 8. SAFE AFTER SIGNING — run the final Windows distribution smoke

```powershell
./release/smoke-stage19-final-windows.ps1 `
  -EngineeringPortablePath '<BASELINE_DIR>/Law-Rag-0.8.0-rc3-windows-x64.zip' `
  -SignedRcDir '<WORK>/signed-rc' `
  -InstallerPath '<WORK>/signed-installer/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -ExpectedSignerThumbprint '<PRODUCTION_SIGNER_THUMBPRINT>' `
  -OutputPath '<WORK>/evidence/STAGE19-FINAL-WINDOWS-SMOKE-EVIDENCE.json'
```

This must prove all of the following before continuing:

- exact unsigned portable input matches the frozen Stage 19.4 hash;
- signed and unsigned portable file lists are identical;
- the only changed portable path is `Law-Rag.exe`;
- signed executable and signed installer use the same expected signer;
- installer installs the exact same signed EXE SHA as the signed portable;
- provider keys are removed during packaged/runtime smoke;
- install/reinstall/uninstall runtime ownership rules still pass.

---

## 9. OWNER INPUT REQUIRED — choose release channel and exact HTTPS installer URL

The final URL must be absolute HTTPS, contain no credentials/query/fragment, and end exactly with:

```text
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

Example shape only:

```text
https://downloads.example.com/law-rag/Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

Choosing or recording a URL is not publication.

## 10. AUTHORIZATION REQUIRED — create the detached CMS update-manifest signature

**Important:** `new-stage19-3-update-manifest.ps1` performs a real private-key CMS signing operation. Do not run this in ordinary CI or before separate production-signing authorization.

After authorization and after the production signer certificate/private key is available in `Cert:\CurrentUser\My`:

```powershell
./release/new-stage19-3-update-manifest.ps1 `
  -InstallerPath '<WORK>/signed-installer/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -CandidateVersion '0.8.0-rc3' `
  -ArtifactUrl 'https://<HOST>/<PATH>/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -SignerThumbprint '<PRODUCTION_SIGNER_THUMBPRINT>' `
  -ManifestPath '<WORK>/channel/UPDATE-MANIFEST.json' `
  -SignaturePath '<WORK>/channel/UPDATE-MANIFEST.p7s' `
  -EvidenceSourceSha '8c05ddd91712d5d9cdbdafe90e77cc9de03b8593'
```

This creates local signed channel evidence; it does **not** itself publish the installer or manifest.

## 11. SAFE AFTER SIGNING — verify release-channel evidence without publishing

```powershell
./release/verify-stage19-final-release-channel.ps1 `
  -ManifestPath '<WORK>/channel/UPDATE-MANIFEST.json' `
  -ManifestSignaturePath '<WORK>/channel/UPDATE-MANIFEST.p7s' `
  -InstallerPath '<WORK>/signed-installer/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -SigningEvidencePath '<WORK>/evidence/STAGE19-FINAL-SIGNING-EVIDENCE.json' `
  -ReleaseChannel '<RELEASE_CHANNEL>' `
  -PublicationUrl 'https://<HOST>/<PATH>/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -CurrentVersion '<CURRENT_INSTALLED_VERSION>' `
  -OutputPath '<WORK>/evidence/STAGE19-FINAL-RELEASE-CHANNEL-EVIDENCE.json'
```

This verifies detached CMS with `CheckSignature`, real installer Authenticode, signer identity, source SHA, installer SHA/size, version eligibility and safe HTTPS URL. It does not publish.

---

## 12. AUTHORIZATION REQUIRED — private expert evidence

Use the existing Stage 16.3 professional benchmark protocol. Real sanitized expert evidence must remain external or under ignored `benchmark_private/`.

Do not substitute synthetic fixtures or public regression results for `PRIVATE_EXPERT=PRESENT`.

## 13. AUTHORIZATION REQUIRED — real paid/network `ISSUE_V1` UAT

Run the real production `ISSUE_V1` chain only after explicit authorization with the configured DeepSeek/Kimi provider credentials and existing approval/cancellation boundaries.

After the provider run has already persisted its artifacts, use the existing Stage 16.4 read-only capture/evaluation path. Capture/evaluation tooling itself must not initiate the paid calls.

Do not relabel synthetic CI or provider-free fixtures as real UAT.

## 14. SAFE AFTER EXTERNAL EVIDENCE — build the Stage 16 complete-evidence matrix

From `backend/`:

```powershell
python -m app.release_evidence_cli `
  --repo-root .. `
  --expert-report '<REAL_PRIVATE_EXPERT_REPORT>' `
  --uat-suite '<REAL_PROVIDER_UAT_SUITE>' `
  --output '<WORK>/evidence/STAGE16-RELEASE-EVIDENCE.json' `
  --require-complete-evidence
```

This command consumes existing evidence and never invokes DeepSeek, Kimi, OCR or another paid/network provider.

It must produce:

```text
PUBLIC_REGRESSION PASS
PRIVATE_EXPERT    PRESENT
REAL_PROVIDER_UAT PASS
stage16_evidence_complete = true
pending_evidence_classes  = []
```

Every supplied Stage 16 source fingerprint must satisfy the pinned lowercase SHA-256 schema.

## 15. SAFE / EVIDENCE ONLY — run Final Acceptance verifier

```powershell
./release/verify-stage19-final-acceptance.ps1 `
  -EngineeringEvidencePath '<BASELINE_DIR>/STAGE19-4-FINAL-PACKAGE-EVIDENCE.json' `
  -SigningEvidencePath '<WORK>/evidence/STAGE19-FINAL-SIGNING-EVIDENCE.json' `
  -ReleaseChannelEvidencePath '<WORK>/evidence/STAGE19-FINAL-RELEASE-CHANNEL-EVIDENCE.json' `
  -Stage16EvidencePath '<WORK>/evidence/STAGE16-RELEASE-EVIDENCE.json' `
  -WindowsSmokeEvidencePath '<WORK>/evidence/STAGE19-FINAL-WINDOWS-SMOKE-EVIDENCE.json' `
  -ReleaseChannel '<RELEASE_CHANNEL>' `
  -PublicationUrl 'https://<HOST>/<PATH>/Law-Rag-0.8.0-rc3-windows-x64-setup.exe' `
  -OutputPath '<WORK>/evidence/STAGE19-FINAL-ACCEPTANCE.json' `
  -RequireComplete
```

The only acceptable all-pass pre-publication result is:

```text
FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED
```

Any `PENDING` means evidence is still missing. Any `FAILED` means supplied evidence is contradictory, malformed or failed. Do not override either state manually.

## 16. AUTHORIZATION REQUIRED — publication

Publication remains a separate explicit action **after** Final Acceptance is complete.

The Final Acceptance verifier never:

- creates a GitHub Release;
- uploads a public release asset;
- changes an update channel;
- publishes the installer/manifest;
- merges PR #31/#32/#35 or this handoff PR.

Do not infer publication authorization from `FINAL_ACCEPTANCE_COMPLETE_NOT_PUBLISHED`.

## Stop conditions

Stop immediately if any of these occur:

- baseline source SHA or frozen unsigned hashes do not match;
- a fresh application/PyInstaller build was introduced;
- more than `Law-Rag.exe` changed inside the signed portable;
- executable and installer signer thumbprints differ;
- installer-installed EXE differs from signed portable EXE;
- CMS signer differs from Authenticode production signer;
- release URL is not exact safe HTTPS;
- Stage 16 evidence is synthetic, malformed, incomplete or has invalid fingerprints;
- any verifier reports `FAIL`;
- authorization for the next external action is absent.
