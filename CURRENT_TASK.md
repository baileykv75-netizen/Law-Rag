# CURRENT_TASK.md

# Stage 11E — Release Candidate Validation and Installer Decision

## Status

```text
Stage 11A  COMPLETE — versioned benchmark schema + public synthetic evaluator
Stage 11B  COMPLETE — layered metrics + failure diagnostics + deterministic CI quality gates
Stage 11C  COMPLETE — runtime/startup/data-integrity hardening
Stage 11D  COMPLETE — reproducible Windows onedir bundle + clean-runner validation
Stage 11E  ACTIVE   — release-candidate validation / distribution and installer decision
```

Stage 11D selected PyInstaller `onedir`, locked the release toolchain/dependencies, removed Node/Vite from the end-user runtime, generated public legal/retrieval assets, collected exact Python/PDFium and frontend license evidence, generated safe release metadata, and validated the packaged executable on a clean Windows runner. The final Stage 11D smoke also checks bundle privacy, native PDF upload, packaged PDFium rendering, React/API serving and artifact upload.

See:

- `docs/WINDOWS_PACKAGING.md`
- `release/README-WINDOWS.md`
- `release/dependency-inventory.json`

## Goal

Turn the verified Stage 11D portable folder into a **reviewable Release Candidate (RC)** and decide whether Law-Rag actually needs an installer.

Priority:

```text
freeze RC identity
  -> create portable distribution artifact + hashes/manifest
  -> independently validate artifact contents
  -> define/manual-run user acceptance checklist
  -> review third-party notices and distribution boundary
  -> decide portable ZIP vs installer
  -> only then publish/tag a release if explicitly intended
```

The default 11E bias is **portable first**. An installer must solve a demonstrated user problem; it is not a maturity badge.

## Hard boundaries

1. Do not add an installer merely because Stage 11D can build an `.exe`.
2. Do not add auto-update, registry mutation, file associations, PATH changes, services or startup tasks without a concrete need.
3. Do not publish a GitHub Release/tag automatically as part of ordinary CI; publication is an explicit release action.
4. Do not add a repository open-source license without the owner's explicit decision.
5. Do not represent generated notice files as automatic legal/licensing sign-off; actual release review remains explicit.
6. No API keys, `.env` with real values, private contracts, user jobs/reviews, logs, model caches or private benchmarks may enter an RC artifact.
7. OCR/Paddle and semantic/BGE remain outside the first base RC unless a separate verified bundle variant is intentionally approved.
8. DeepSeek/Kimi credentials remain user-supplied at runtime.
9. `CURATED_EXCERPT` legal coverage warning must remain visible and unchanged.
10. Stage 1–10 regressions, Stage 11B quality gates, Stage 11C diagnostics and Stage 11D Windows bundle smoke must remain green.

## 11E-1 — RC identity and portable artifact

Define a clear RC identity without pretending it is a final production release.

Target first candidate:

```text
Law-Rag 0.8.0-rc1
Windows x64
portable onedir ZIP
```

Generate alongside the ZIP:

```text
SHA256SUMS.txt
RC-MANIFEST.json
```

The manifest should contain only safe reproducibility/distribution metadata, including source commit, application version, artifact filename/hash/size, target, toolchain summary, bundled public legal/retrieval fingerprints and notice/report fingerprints.

Do not put absolute local paths, usernames, secrets or private data in the manifest.

## 11E-2 — Independent RC artifact verification

Validation must operate on the **final zipped/unzipped RC artifact**, not only on the pre-archive build directory.

Verify at minimum:

- ZIP extraction succeeds on Windows;
- expected top-level executable/README/config template exist;
- release metadata and SHA match the source/build record;
- no banned private/runtime files are present;
- `Law-Rag.exe --diagnose --json` succeeds after extraction;
- backend/API/frontend start from the extracted RC;
- native PDF upload and packaged PDFium page rendering still pass;
- public `legal.db` + lexical `retrieval.db` are readable and fingerprint-matched;
- no provider key is required for base startup;
- OCR/BGE absence remains an explicit nonfatal optional state.

## 11E-3 — Manual Windows user-acceptance checklist

Create a short human checklist for testing the actual RC on a normal Windows 10/11 desktop outside GitHub Actions.

It should cover the user-visible path, not developer internals:

```text
extract ZIP
launch Law-Rag.exe
browser opens
upload native-text PDF
open workspace/source page
run deterministic structure/rules
inspect legal evidence/retrieval
verify missing OCR/BGE is explained rather than crashing
configure provider keys only if intentionally testing AI stages
close/reopen and confirm local job persistence
run --diagnose for a controlled failure/missing optional component
```

Do not require real private contracts for acceptance. Use fictional/public documents first.

## 11E-4 — Distribution/licence review packet

Prepare a release-review packet that points to the actual generated notice evidence rather than restating headline licenses.

Review items include:

- CPython licensing material;
- PyInstaller bundling exception/bootloader boundary;
- exact Python distribution notices;
- pypdfium2/PDFium dependency license material;
- Vite generated frontend dependency licenses;
- public legal-source provenance;
- explicit statement that PaddleOCR/PaddlePaddle, PyTorch/BGE weights are not bundled in the base RC;
- repository itself still has no general reuse/open-source license selected.

If an obligation is uncertain, mark it `REVIEW_REQUIRED` instead of inventing a compliance conclusion.

## 11E-5 — Installer decision

After portable RC validation, record one explicit decision:

```text
PORTABLE_ZIP_SUFFICIENT
or
INSTALLER_JUSTIFIED
```

Installer is justified only if manual RC testing shows concrete friction such as:

- users cannot reliably choose a writable install/runtime location;
- shortcuts/uninstall handling materially improve usability;
- optional components need a controlled installation path;
- distribution/update requirements genuinely need an installer.

If the portable ZIP works reliably, prefer it for the first personal-use release and defer MSI/Inno/NSIS.

## 11E-6 — Publication boundary

Stage 11E may prepare release files and a release-note draft, but must not silently publish/tag a public release.

A publication-ready set should include:

```text
Law-Rag-0.8.0-rc1-windows-x64.zip
SHA256SUMS.txt
RC-MANIFEST.json
release notes / known limitations
```

Known limitations must explicitly mention at least:

- base RC excludes OCR and semantic ML stacks;
- DeepSeek/Kimi require user-supplied keys and external transmission;
- bundled legal corpus is a curated excerpt, not complete law;
- the software is an audit/review aid, not a replacement for professional legal judgment.

## Validation before 11E completion

1. a named RC portable ZIP is produced by a committed deterministic path;
2. final ZIP hash and manifest are generated and internally consistent;
3. the extracted RC passes independent Windows smoke, including native PDF/PDFium;
4. the final RC is scanned for private/runtime/secret files;
5. a normal-user Windows acceptance checklist exists;
6. release/notice review packet exists with unresolved items explicit;
7. installer decision is recorded with evidence rather than aesthetics;
8. no automatic public publication occurs;
9. backend regressions and Stage 11B quality gates remain green;
10. frontend locked production build remains green;
11. Stage 11D bundle path remains reproducible and green;
12. release notes accurately state optional-stack/legal-corpus/provider limitations.

## Out of scope unless 11E explicitly concludes `INSTALLER_JUSTIFIED`

- MSI/Inno/NSIS implementation;
- code-signing purchase/setup;
- Windows SmartScreen reputation work;
- auto-updater;
- system-wide service/background daemon;
- file associations;
- automatic registry/PATH mutation;
- bundled OCR/BGE heavyweight variants;
- automatic public GitHub Release publication;
- cloud deployment/authentication.
