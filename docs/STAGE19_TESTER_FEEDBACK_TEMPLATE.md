# Law-Rag 0.8.0-rc3 Tester Feedback

Please fill in what you actually observed. Leave unknown items blank rather than guessing.

## Environment

- Tester name or alias:
- Test date:
- Windows edition/version:
- Windows OS build:
- CPU architecture:
- Antivirus/security software other than Microsoft Defender, if any:

## Package identity

- Package used: Installer / Portable
- File name:
- SHA-256 calculated:
- SHA-256 matched the expected value exactly: Yes / No
- SmartScreen or Unknown Publisher warning appeared: Yes / No
- If a warning appeared, exact wording or screenshot reference:

## Install / launch

- Installer completed successfully: Yes / No / Not tested
- First launch completed successfully: Yes / No
- Approximate first-launch time:
- Main UI loaded correctly: Yes / No
- Any blank page, crash, freeze, missing asset or permission prompt:

## Local workflow

Use non-sensitive test material.

- Input type tested: PDF / scanned PDF / JPG / JPEG / PNG / DOCX
- Local ingest completed: Yes / No
- Results/workspace opened correctly: Yes / No
- Provider approval boundary behaved as expected: Yes / No / Not tested
- DeepSeek/Kimi provider calls performed with tester-owned credentials: Yes / No

## Required — Offline OCR

Use a scanned PDF or image that genuinely requires OCR. Disconnect the PC from the Internet before importing it and keep provider calls disabled.

- Test file type: scanned PDF / JPG / JPEG / PNG
- Internet disconnected before import: Yes / No
- Confirmed no active Internet connection: Yes / No
- OCR started while offline: Yes / No
- OCR completed while offline: Yes / No
- Any Paddle/PaddleOCR/model/runtime download prompt or attempt observed: Yes / No
- Any missing-model or network-required error: Yes / No
- OCR text produced: Yes / No
- OCR result usable: Yes / No
- Approximate OCR time:
- Offline OCR overall result: PASS / FAIL
- Notes or screenshot/log reference:

## Required — Report export

Use an export-eligible result/review state with non-sensitive test material.

### DOCX

- DOCX export action available: Yes / No
- DOCX export completed: Yes / No
- Exported file had non-zero size: Yes / No / Not tested
- Exported DOCX opened successfully: Yes / No / Not tested
- Major sections/content present: Yes / No / Not tested
- Obvious broken characters/layout/tables: Yes / No / Not tested
- Word/viewer reported file corruption: Yes / No / Not tested
- DOCX report export overall result: PASS / FAIL / NOT TESTED

### PDF

- PDF export action offered for this result/state: Yes / No
- If offered, PDF export completed: Yes / No / Not applicable
- If exported, PDF opened successfully: Yes / No / Not applicable
- Obvious broken characters/layout: Yes / No / Not applicable
- PDF report export overall result: PASS / FAIL / NOT OFFERED

- Report export notes or screenshot reference:

## Reinstall / uninstall

- Reinstall tested: Yes / No
- Reinstall completed successfully: Yes / No / Not tested
- Existing runtime/user data remained available after reinstall: Yes / No / Not tested
- Uninstall tested: Yes / No
- Uninstall completed successfully: Yes / No / Not tested
- Runtime/user data preservation after uninstall matched expectation: Yes / No / Not tested

## Problems

For each problem, include exact reproduction steps.

### Problem 1

- Summary:
- Severity: Blocker / Major / Minor / Cosmetic
- Reproduction steps:
  1.
  2.
  3.
- Expected behavior:
- Actual behavior:
- Reproducible every time: Yes / No
- Screenshot/log reference:

### Problem 2

- Summary:
- Severity: Blocker / Major / Minor / Cosmetic
- Reproduction steps:
  1.
  2.
  3.
- Expected behavior:
- Actual behavior:
- Reproducible every time: Yes / No
- Screenshot/log reference:

## Overall result

- Would you consider this build usable for another testing round: Yes / No
- Biggest issue encountered:
- Anything confusing or unexpectedly difficult:
- Other notes:
