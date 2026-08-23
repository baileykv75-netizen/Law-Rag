# Law-Rag 0.8.0-rc3 — Unsigned Tester Distribution

## Scope

This package is for a small group of invited testers only.

It is **not** a public trusted release, not a production update-channel publication, and not evidence that Stage 19 Final Acceptance is complete.

The application binaries in this handoff are the exact frozen Stage 19.4 RC3 engineering candidate. The tester-distribution process does not rebuild, patch, sign, or otherwise modify the installer or portable ZIP.

Frozen identities:

```text
Stage 19.4 source SHA
8c05ddd91712d5d9cdbdafe90e77cc9de03b8593

Installer
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
SHA-256: cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8

Portable
Law-Rag-0.8.0-rc3-windows-x64.zip
SHA-256: 9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796
```

## Before running anything

Verify the SHA-256 of the file you received.

Installer:

```powershell
(Get-FileHash -Algorithm SHA256 '.\Law-Rag-0.8.0-rc3-windows-x64-setup.exe').Hash.ToLowerInvariant()
```

Expected:

```text
cc94adf002984c7bfd7d2c0b7c7fc30e4bf19a95add655c448ace8a5deeb1ef8
```

Portable ZIP:

```powershell
(Get-FileHash -Algorithm SHA256 '.\Law-Rag-0.8.0-rc3-windows-x64.zip').Hash.ToLowerInvariant()
```

Expected:

```text
9ba6c15cab5aa97820311ee97589ed338d88b9fad81ab6b96d06ff6162b6e796
```

**If the hash does not match exactly, stop and do not run the file.**

## Expected Windows warning

This tester build is intentionally unsigned. Windows may therefore show `Unknown publisher`, Microsoft Defender SmartScreen / `Windows protected your PC`, or another warning stating that the publisher cannot be verified.

This is expected for this limited tester build and does not mean the SHA check can be skipped. Only after the SHA-256 matches exactly may an invited tester use the Windows `More info` / `Run anyway` path if SmartScreen offers it.

Do not disable SmartScreen globally and do not lower Windows security settings for this test.

## Recommended path: installer

Use:

```text
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

Required tester sequence for this round:

1. Verify SHA-256.
2. Install normally for the current Windows user.
3. Launch Law-Rag from the installed shortcut/application entry.
4. Exercise the normal local workflow with non-sensitive test material.
5. Perform the **Offline OCR** test below.
6. Perform the **Report export** test below.
7. Close the application and run the installer again to test reinstall behavior.
8. Confirm existing Law-Rag runtime/user data is still present where expected.
9. Uninstall Law-Rag.
10. Confirm uninstall removes the application while preserving the runtime/user-data boundary already defined by the RC3 installer.
11. Record results in `TESTER-FEEDBACK.md`.

## Required test — Offline OCR

This round must prove that packaged OCR works without any runtime model download.

Use a **non-sensitive scanned PDF or image that actually requires OCR**.

Test procedure:

1. Start Law-Rag once while online and confirm the application launches normally.
2. Fully disconnect the test PC from the network: disable Wi-Fi and unplug/disable Ethernet as applicable.
3. Confirm there is no active Internet connection.
4. Keep DeepSeek/Kimi provider calls disabled; this test is local OCR only.
5. Import the scanned PDF/JPG/JPEG/PNG.
6. Let Law-Rag perform ingest and OCR.
7. Confirm OCR completes without asking to download Paddle/PaddleOCR/model files and without failing because the Internet is unavailable.
8. Inspect the extracted/OCR text and record whether it is usable.
9. Record any unexpected outbound-network requirement, missing-model error, crash, hang or very long stall in `TESTER-FEEDBACK.md`.

Expected result:

```text
OFFLINE_OCR = PASS
- packaged OCR runtime starts offline
- packaged PP-OCRv6 detector/recognizer are found locally
- no model/runtime download is required
- a scanned document produces usable OCR text
```

A provider-dependent AI audit is **not** part of this offline test. Reconnect the network only after the local OCR observation is complete.

## Required test — Report export

This round must also prove that a tester can generate and open a local report from an available Law-Rag result/review state.

Use non-sensitive test material. A provider-backed result may be used only if the tester intentionally configured their own provider credentials; otherwise use a result/state that can be completed with the available local/test path.

Test procedure:

1. Open a completed or otherwise export-eligible result in Results/Workspace.
2. Trigger the normal report-export action.
3. Export **DOCX**.
4. Confirm the DOCX file is created, has non-zero size, and opens successfully in Word or another compatible viewer.
5. Inspect the report for obvious corruption: blank document, broken characters, missing major sections, visibly broken tables/layout, or a file that Word reports as damaged.
6. If the UI offers **PDF export** in this RC3 path, export PDF as well and confirm it opens successfully. Record `Not offered` rather than treating absence of the UI action as a failure if PDF is not exposed for that state.
7. Record file type, success/failure and any formatting/content problem in `TESTER-FEEDBACK.md`.

Expected result:

```text
DOCX_REPORT_EXPORT = PASS
PDF_REPORT_EXPORT  = PASS / NOT_OFFERED
```

This is a functional export test, not a claim that the report's legal conclusions have professional expert validation.

## Portable alternative

Use:

```text
Law-Rag-0.8.0-rc3-windows-x64.zip
```

After verifying its SHA-256, extract it to a normal writable folder and run `Law-Rag.exe` from the extracted `Law-Rag` directory.

The portable build is useful for checking whether a problem belongs to the installer lifecycle or to the application itself. If the portable build is used as the primary test package, the same Offline OCR and Report export tests above still apply.

## Test data and provider credentials

Use non-sensitive sample contracts/documents during this limited test unless you explicitly understand the provider boundary.

Law-Rag performs local extraction/OCR/structure/rules before cloud-model phases, but an authorized DeepSeek/Kimi provider step can transmit bounded contract evidence to the configured provider.

Do **not** distribute the project owner's DeepSeek/Kimi API keys inside the tester package, in screenshots, in chat, or in configuration files.

A tester without provider credentials can still test installation, launch, local ingest/OCR, UI behavior and the provider-approval boundary. If a tester independently uses their own provider credentials, they should treat that as a separate network/provider test and avoid sensitive source material.

## What to report

Please report at least:

- Windows version/build;
- installer or portable path used;
- SHA-256 verification result;
- whether SmartScreen/Unknown Publisher appeared;
- install success/failure;
- first-launch success/failure;
- **Offline OCR result, including confirmation that no model/runtime download was required**;
- **DOCX report export result and PDF export result if offered**;
- reinstall behavior;
- uninstall behavior;
- whether previous runtime/user data was preserved as expected;
- any crash, hang, blank page, permission problem or antivirus interference;
- exact reproduction steps for every failure.

Use the included `TESTER-FEEDBACK.md` template.

## Current release status

```text
distribution_state = READY_FOR_LIMITED_UNSIGNED_TESTING
production_signer  = DEFERRED
public_release     = NOT_PUBLISHED
Final Acceptance   = FINAL_ACCEPTANCE_PENDING
```

A future public trusted release will require a real production signing identity and the remaining Final Acceptance gates. That requirement is deliberately deferred for this small invited-tester phase.
