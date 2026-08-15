# Stage 11E Release Review Packet

This packet summarizes the **actual Stage 11D/11E base RC distribution boundary**. It is a checklist for release review, not a declaration that license/compliance questions are automatically resolved.

## RC scope

```text
Law-Rag 0.8.0-rc1
Windows x64
portable PyInstaller onedir ZIP
base/native-PDF + deterministic/legal/retrieval/workstation path
```

Not bundled:

```text
PaddlePaddle / PaddleOCR
OCR model weights
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
API keys
private contracts/jobs/reviews/logs
private benchmark data
```

## Review states

Use only:

```text
AUTOMATED_EVIDENCE_PRESENT
MANUAL_REVIEW_REQUIRED
NOT_BUNDLED
NOT_APPLICABLE
```

Do not replace an unresolved item with a guessed `COMPLIANT` label.

## 1. CPython runtime

State: `MANUAL_REVIEW_REQUIRED`

Evidence:

- exact release runtime: CPython 3.12.10;
- runtime/toolchain recorded in bundled release metadata;
- Python distribution is collected by PyInstaller into the Windows bundle.

Release reviewer action:

- confirm applicable Python/PSF license/copyright material is present in the final notice set or otherwise included as required for redistribution.

## 2. PyInstaller

State: `MANUAL_REVIEW_REQUIRED`

Evidence:

- exact build version: PyInstaller 6.22.0;
- packaging decision and current bundling-exception source review documented in `docs/WINDOWS_PACKAGING.md`;
- exact installed distribution metadata/notice files are collected where exposed by the installed package.

Release reviewer action:

- confirm the PyInstaller bootloader/bundling-exception notice boundary for the final artifact.

## 3. Exact Python distributions

State: `AUTOMATED_EVIDENCE_PRESENT`

Generated evidence inside the final bundle:

```text
_internal/THIRD-PARTY-NOTICES/python-third-party-notices.json
_internal/THIRD-PARTY-NOTICES/python/<distribution>/...
```

The generator reads the exact isolated Windows lock environment and copies LICENSE/COPYING/NOTICE/copyright-like files exposed by installed distributions.

Release reviewer action:

- inspect the generated report for distributions with no usable notice material or ambiguous metadata;
- do not assume absence of a copied file means no obligation exists.

## 4. pypdfium2 / PDFium

State: `AUTOMATED_EVIDENCE_PRESENT` + `MANUAL_REVIEW_REQUIRED`

Special build gate:

- the release build fails if the exact installed `pypdfium2` wheel does not expose PDFium/dependency license material through the wheel contents;
- clean Windows bundle CI has validated this collector against the Windows release environment;
- packaged `pdfium.dll` is verified by bundle smoke and then exercised through actual source-page rendering.

Release reviewer action:

- inspect the copied PDFium/build-licenses material in the final RC;
- confirm the collected set is appropriate for redistribution of the exact wheel/DLL.

## 5. Frontend production dependencies

State: `AUTOMATED_EVIDENCE_PRESENT`

Evidence:

```text
frontend/package-lock.json
_internal/frontend-dist/third-party-frontend-licenses.json
```

Vite `build.license` generates the frontend bundled-dependency license metadata from the locked production build.

Release reviewer action:

- inspect generated frontend license metadata before public distribution.

## 6. Public legal/retrieval assets

State: `AUTOMATED_EVIDENCE_PRESENT`

Evidence:

- `legal_data/seed/manifest.json` and checked-in verified public source snapshots;
- deterministic `legal.db` build;
- deterministic lexical `retrieval.db` build;
- `public-assets-metadata.json` with hashes, counts and legal-source fingerprint;
- RC/release manifests fingerprint the generated public assets.

Boundary:

- public legal-source provenance is not treated as a software package license;
- bundled corpus is a `CURATED_EXCERPT`, not complete law.

Release reviewer action:

- confirm public-source provenance and any source-specific republication considerations remain accurately documented.

## 7. Optional OCR stack

State: `NOT_BUNDLED`

The base RC does not redistribute:

```text
PaddlePaddle
PaddleOCR
OCR model weights
```

If a future OCR-inclusive variant is proposed, its exact Windows wheels, native components, model licenses/notices and size/update behavior require a separate release review.

## 8. Optional semantic stack

State: `NOT_BUNDLED`

The base RC does not redistribute:

```text
sentence-transformers
PyTorch
BAAI/bge-small-zh-v1.5 weights
```

If a future semantic-inclusive variant is proposed, exact wheel/transitive/model licenses and redistribution notices require a separate review.

## 9. DeepSeek / Kimi

State: `NOT_BUNDLED`

The RC includes provider adapter code but no credentials or provider-hosted model artifacts.

Release boundary:

- `DEEPSEEK_API_KEY` and `MOONSHOT_API_KEY` are user-supplied runtime configuration;
- provider calls are external network operations initiated by explicit audit/review stages;
- keys/Authorization headers are prohibited from diagnostics and RC metadata.

## 10. Law-Rag repository licensing

State: `MANUAL_REVIEW_REQUIRED`

The repository intentionally still has **no general open-source/reuse license** selected. Public repository visibility does not grant a reuse license by itself.

Release reviewer/owner action before any broader public distribution:

- decide whether a project-level license is needed and, if so, select it explicitly;
- Stage 11E must not silently add MIT/Apache/GPL or another license.

## 11. Private-data scan

State: `AUTOMATED_EVIDENCE_PRESENT`

The Windows bundle/RC pipeline rejects or scans for representative forbidden content, including:

```text
runtime/
uploads/
jobs/
logs/
data_private/
benchmark_private/
model_cache/
.env
source.pdf/jpg/jpeg/png
human-review.json
ai-audit.json
secondary-review.json
review-report.json
```

The packaged smoke uses an external temporary runtime so test-generated job data cannot be uploaded inside the RC artifact.

## Release reviewer sign-off record

```text
RC version:
Source commit:
Artifact SHA-256:
Python notice review: PASS / REVIEW_REQUIRED
PDFium notice review: PASS / REVIEW_REQUIRED
Frontend notice review: PASS / REVIEW_REQUIRED
Public legal-source review: PASS / REVIEW_REQUIRED
Project-level license decision: UNCHANGED / DECIDED
Private-data scan: PASS / FAIL
Reviewer:
Date:
Notes:
```

A public release should not be described as distribution-ready while a material required review remains unresolved.
