# Law-Rag 0.8.0-rc1 — Windows Portable Release Candidate

Status: **Release Candidate / NOT PUBLISHED**

This candidate packages the validated Law-Rag base workflow into an inspectable Windows x64 portable ZIP. It is intended for release validation and personal-use testing before any installer/public-release decision.

## What is included

- one-folder `Law-Rag.exe` local launcher;
- FastAPI backend and production React workstation served on loopback;
- PDF/JPG/PNG local upload;
- native PDF extraction;
- packaged PDFium page rendering;
- deterministic canonical contract structure and rule engine;
- bundled public curated legal seed;
- Exact + lexical/BM25 legal retrieval;
- Stage 8/9 DeepSeek/Kimi adapters with no embedded credentials;
- Stage 10 review workstation and human-review persistence;
- Stage 11 runtime/job integrity diagnostics;
- release/dependency/public-asset metadata;
- generated Python/PDFium and frontend third-party notice evidence.

## Portable distribution files

The RC build produces:

```text
Law-Rag-0.8.0-rc1-windows-x64.zip
RC-MANIFEST.json
SHA256SUMS.txt
```

The RC remains `NOT_PUBLISHED` until an explicit release action is chosen.

## Known limitations

### OCR is not bundled

The base RC does not include PaddlePaddle, PaddleOCR or OCR model weights. Native-text PDF workflows remain available. Scanned/image-only documents require the separately supported OCR stack and should surface an explicit optional-component limitation rather than silently degrade.

### Semantic/BGE retrieval is not bundled

The base RC includes Exact + FTS5/BM25 lexical legal retrieval. `sentence-transformers`, PyTorch and `BAAI/bge-small-zh-v1.5` weights are not redistributed in this candidate.

### External AI providers require user-supplied credentials

DeepSeek and Kimi calls require locally configured `DEEPSEEK_API_KEY` / `MOONSHOT_API_KEY`. These stages send bounded audit/review context to external providers when the user intentionally runs them. No API key is embedded in the ZIP.

### Bundled legal corpus is incomplete by design

The current public legal store is a verified `CURATED_EXCERPT`, not a complete corpus of Chinese law. A retrieval no-hit must not be interpreted as proof that no relevant legal rule exists.

### Audit/review aid, not legal judgment replacement

Rule failures, retrieval scores, model findings and two-model agreement are review evidence. They are not automatic conclusions that a contract is legal/illegal, valid/invalid or enforceable/unenforceable. Material uncertainty remains reviewable by a human.

### Portable runtime lives beside the extracted application

User job data is created under the extracted application's local `runtime/` path. The ZIP should therefore be extracted into a normal writable user folder. Moving/deleting that folder affects the local portable data location.

### No installer / auto-update / code signing in RC1

RC1 is deliberately portable. It does not create registry entries, file associations, services, PATH changes, shortcuts or an auto-updater. The installer decision is deferred until normal-user acceptance testing demonstrates a concrete need.

## Validation already required by CI

The RC path is expected to pass on a clean Windows runner:

- exact locked Windows build toolchain;
- deterministic public legal/retrieval generation;
- exact Python/PDFium notice collection;
- Vite bundled-license metadata;
- release/RC manifest generation;
- banned private/runtime file scan;
- `Law-Rag.exe --diagnose --json`;
- local API + React production shell;
- synthetic native PDF upload;
- packaged PDFium page rendering;
- final ZIP hash verification;
- extraction into a fresh directory and repeat runtime smoke;
- ordinary backend regressions, Stage 11B quality gates and locked frontend build.

## Before broader public distribution

Still required as explicit human/owner decisions:

- complete the normal-user Windows acceptance checklist;
- review generated third-party notice evidence, especially PDFium;
- confirm public legal-source provenance/republication boundary;
- decide whether the project itself needs a general reuse/open-source license;
- decide `PORTABLE_ZIP_SUFFICIENT` vs `INSTALLER_JUSTIFIED`;
- explicitly choose whether to publish/tag a GitHub Release.
