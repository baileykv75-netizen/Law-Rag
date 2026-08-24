# Law-Rag 0.8.0-rc3-tester1 — Licensed Tester Distribution

## Scope

This Windows build is for invited testers only. It is an unsigned Windows installer with a separate **offline signed Law-Rag tester license**.

It is not a public trusted release and does not complete Stage 19 Final Acceptance.

Each tester receives:

1. `Law-Rag-0.8.0-rc3-tester1-windows-x64-setup.exe`;
2. one tester-specific `.license.txt` file;
3. this guide and the tester feedback template.

Do not send your license file to another person. The application and exported reports display the Tester ID embedded in that license.

## 1. Verify the installer

Use the `SHA256SUMS-TESTER1.txt` supplied beside the installer:

```powershell
(Get-FileHash -Algorithm SHA256 '.\Law-Rag-0.8.0-rc3-tester1-windows-x64-setup.exe').Hash.ToLowerInvariant()
```

The value must exactly match the tester-package SHA file. If it does not, stop.

Because this limited build is intentionally unsigned, Windows may show `Unknown publisher` or Microsoft Defender SmartScreen. Only continue after the SHA matches. Do not disable SmartScreen globally.

## 2. Install

Run the installer for the current Windows user. The installed application is stored under:

```text
%LOCALAPPDATA%\Programs\Law-Rag
```

User/runtime data is stored separately under:

```text
%LOCALAPPDATA%\Law-Rag\runtime
```

## 3. First launch and license activation

Start Law-Rag from the Start Menu or desktop shortcut.

Before activation, the workstation shows the **Law-Rag tester license** screen instead of the normal navigation. Load the `.license.txt` file you received, or paste the `LR1...` token, then choose **激活测试许可**.

Validation is local and checks:

- Ed25519 signature;
- Tester ID;
- `0.8.0-rc3-tester1` release binding;
- not-before time;
- expiry time.

No network access is required to activate the tester license.

After activation, the normal workstation opens and a persistent lower-right watermark displays your Tester ID. The license is stored with user runtime data, so ordinary reinstall does not require re-entering the same still-valid license.

If the license is expired, not yet valid, modified or issued for another tester build, Law-Rag remains locked.

## 4. Normal local workflow

Use non-sensitive test material.

Test at least the normal document workflow that is relevant to you. Provider calls are separate from the tester-license mechanism. Never share the project owner's DeepSeek/Kimi API keys.

## 5. Mandatory offline OCR test

This tester round explicitly requires one real offline OCR check.

1. Complete installation and tester-license activation while online if needed for receiving files.
2. Disconnect Windows from the network (Wi-Fi/Ethernet/VPN as applicable).
3. Keep DeepSeek/Kimi provider use disabled.
4. Import a scanned PDF or image that genuinely requires OCR.
5. Run OCR.
6. Confirm Law-Rag uses the packaged Paddle/PaddleOCR/PP-OCRv6 assets and does not request a model download.
7. Confirm OCR completes and the extracted text is usable enough to continue the local workflow.
8. Record PASS/FAIL, approximate duration and any missing-model/network error in `TESTER-FEEDBACK.md`.

A normal tester build must not require internet access merely to obtain OCR models after installation.

## 6. Mandatory report-export test

After a test Job reaches a state where report export is enabled:

1. Export DOCX. This is mandatory.
2. Open the DOCX in a normal office application.
3. Confirm the file is non-empty, opens normally and has no obvious corruption/garbling or major layout breakage.
4. Confirm the footer contains your `Tester <ID>` limited-test watermark.
5. If the UI offers PDF export, export and open the PDF as well.
6. Confirm every PDF page shows the same Tester ID watermark.
7. Record results in `TESTER-FEEDBACK.md`.

Report export itself is local and must not trigger a model call.

## 7. What the access control does and does not do

The tester license is intended to deter casual forwarding and make leaks attributable. It is not machine-bound DRM.

If someone forwards both the installer and their still-valid license, another computer may use that license until it expires; however the forwarded copy remains identified as that Tester ID and exported reports carry the same traceable watermark.

The expiry check is offline and therefore relies on the Windows system clock. Do not describe this mechanism as impossible to bypass by a determined local administrator.

## 8. Feedback

Return `TESTER-FEEDBACK.md` with at least:

- Windows version/build;
- installer SHA verification result;
- SmartScreen/Unknown Publisher behavior;
- Tester ID and license activation state;
- install and first-launch result;
- offline OCR result;
- DOCX report-export result;
- PDF report-export result if offered;
- crashes, hangs, blank pages, antivirus interference or exact reproduction steps for failures.

## Current truth state

```text
release_label       = 0.8.0-rc3-tester1
distribution_scope  = INVITED_TESTERS_ONLY
tester_license      = REQUIRED_OFFLINE_SIGNED
production_signer   = DEFERRED
public_release      = NOT_PUBLISHED
Final Acceptance    = FINAL_ACCEPTANCE_PENDING
```

This tester1 build has new binary hashes. Do not compare it to the frozen Stage 19.4 RC3 installer/portable hashes as if the binaries were unchanged.
