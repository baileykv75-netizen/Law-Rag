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

This tester build is intentionally unsigned. Windows may therefore show:

- `Unknown publisher`;
- Microsoft Defender SmartScreen / `Windows protected your PC`;
- another warning stating that the publisher cannot be verified.

This is expected for this limited tester build and does not mean the SHA check can be skipped.

Only after the SHA-256 matches the value above, a tester who intentionally received this build may use the Windows `More info` / `Run anyway` path if SmartScreen offers it.

Do not disable SmartScreen globally and do not lower Windows security settings for this test.

## Recommended path: installer

Use:

```text
Law-Rag-0.8.0-rc3-windows-x64-setup.exe
```

Suggested test sequence:

1. Verify SHA-256.
2. Install normally for the current Windows user.
3. Launch Law-Rag from the installed shortcut/application entry.
4. Exercise the basic workflow with non-sensitive test material.
5. Close the application and run the installer again to test reinstall/upgrade behavior.
6. Confirm existing Law-Rag runtime/user data is still present where expected.
7. Uninstall Law-Rag.
8. Confirm uninstall removes the application while preserving the runtime/user-data boundary already defined by the RC3 installer.
9. Record results in `TESTER-FEEDBACK.md`.

## Portable alternative

Use:

```text
Law-Rag-0.8.0-rc3-windows-x64.zip
```

After verifying its SHA-256, extract it to a normal writable folder and run `Law-Rag.exe` from the extracted `Law-Rag` directory.

The portable build is useful for checking whether a problem belongs to the installer lifecycle or to the application itself.

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
- reinstall behavior;
- uninstall behavior;
- whether previous runtime/user data was preserved as expected;
- one or two representative local ingest/OCR tests;
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
