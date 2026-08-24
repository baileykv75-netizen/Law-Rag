# Law-Rag 0.8.0-rc3-tester2 Feedback

Record what you actually observed. Leave unknown items blank rather than guessing.

## Environment

- Tester ID:
- Test date:
- Windows edition/version:
- Windows OS build:
- CPU architecture:
- RAM:
- Antivirus/security software other than Microsoft Defender, if any:

## Package identity

- Installer file name:
- Installer SHA-256 calculated:
- SHA-256 matched `SHA256SUMS-TESTER2.txt` exactly: Yes / No
- SmartScreen or Unknown Publisher warning appeared: Yes / No
- Exact warning or screenshot reference:

## Tester2 license

- License file name:
- First launch showed tester-license activation screen: Yes / No
- Tester1 license was rejected if tried: Yes / No / Not tested
- Tester2 license activation completed: Yes / No
- Tester ID shown in lower-right watermark:
- Expiry shown by the license, if observed:
- Any activation error or confusing behavior:

## Install / first launch

- Installer completed successfully: Yes / No
- Main UI loaded correctly after activation: Yes / No
- Approximate first-launch time:
- Any blank page, crash, freeze, missing asset or permission prompt:

## Batch robustness

Use non-sensitive synthetic/test documents.

- Number of files submitted together:
- Formats included: PDF / DOCX / scanned PDF / JPG / PNG
- Ten-file stress batch performed: Yes / No
- Any `AtomicWriteError`: Yes / No
- Any single 422/503/status-read blip permanently marked a task failed: Yes / No
- Results page showed correct valid-contract count: Yes / No
- Old/corrupt Job polluted valid-contract count: Yes / No
- Global Results navigation opened latest useful batch without “缺少批次编号”: Yes / No
- Batch robustness overall: PASS / FAIL
- Notes / screenshot / log reference:

## Checkpoint/retry behavior

- A task was retried/resumed: Yes / No
- Completed OCR was reused when appropriate: Yes / No / Not applicable
- Completed structure/rule stages were reused: Yes / No / Not observed
- Completed model Issue checkpoints were reused: Yes / No / Not observed
- Retry unexpectedly restarted everything from zero: Yes / No
- Notes:

## Recoverable provider behavior

Do not deliberately overload provider services. Record naturally occurring transient failures only.

- Provider calls used tester-owned credentials: Yes / No
- Transient DeepSeek/Kimi/network interruption observed: Yes / No
- If observed, task moved to “waiting for external service” rather than legal/audit failure: Yes / No / Not applicable
- Existing progress/checkpoints remained available: Yes / No / Not applicable
- Service recovery + continue succeeded: Yes / No / Not applicable
- Notes / exact error:

## Mandatory offline OCR

- Network disconnected before OCR: Yes / No
- Provider use disabled/not approved during OCR: Yes / No
- Input type: scanned PDF / JPG / JPEG / PNG
- OCR began without model download: Yes / No
- Page-level OCR progress changed while processing: Yes / No
- Any network-required or missing-model error: Yes / No
- OCR completed: Yes / No
- Approximate first scanned-document OCR duration:
- Approximate later scanned-document OCR duration in same app session:
- Later document avoided a full model reinitialization delay: Yes / No / Unsure
- OCR text usable: Yes / No
- Able to continue local workflow after OCR: Yes / No
- Offline OCR overall: PASS / FAIL
- Notes / screenshot / log reference:

## Mandatory report export

### DOCX

- A Job reached report-export-ready state: Yes / No
- DOCX export completed: Yes / No
- Exported DOCX was non-empty: Yes / No
- DOCX opened normally: Yes / No
- Obvious corruption/garbling/major layout breakage: Yes / No
- Footer showed the correct Tester ID watermark: Yes / No
- DOCX report export overall: PASS / FAIL

### PDF

- PDF export offered by current UI: Yes / No
- If offered, PDF export completed: Yes / No / Not tested
- PDF opened normally: Yes / No / Not tested
- Every checked page showed correct Tester ID watermark: Yes / No / Not tested
- PDF report export overall: PASS / FAIL / NOT OFFERED

## Problems

For each problem include exact reproduction steps, expected behavior, actual behavior, and screenshot/log reference.

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

## Overall

- Usable for another limited testing round: Yes / No
- Biggest issue encountered:
- Anything confusing or unexpectedly difficult:
- Other notes:
