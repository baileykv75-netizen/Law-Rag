# Windows Packaging Decision

Stage 11D converts the stable local development application into a reproducible, inspectable Windows release bundle. This decision was re-verified against current primary documentation on 2026-08-15 before adding a packaging dependency.

## Decision

The first Law-Rag release bundle will use:

```text
Windows x64
CPython 3.12
PyInstaller 6.22.x
one-folder / onedir mode
FastAPI serves the production frontend assets
Node.js is build-time only
OCR and semantic ML stacks are not part of the first base bundle
```

The first distributable target is an inspectable folder, not an installer and not a one-file executable.

## Why PyInstaller onedir

PyInstaller's current stable documentation says it supports Python 3.8+ and Windows, bundles the active Python interpreter with imported modules, and produces a self-contained folder or optional single executable. Its default one-folder mode is explicitly easier to diagnose because collected files remain visible.

That matches Law-Rag's current priorities:

- no Python installation on the end-user machine;
- no Node/Vite development server at runtime;
- inspectable files for PDFium, legal assets, frontend assets and notices;
- easier clean-runner debugging than a self-extracting one-file build;
- Windows-specific bundle creation can run on GitHub Actions Windows runners;
- no need to change the FastAPI/Python architecture merely for packaging.

The current PyInstaller license documentation states that PyInstaller itself uses GPL-2.0 with an exception (plus Apache-2.0 for a small subset), and that generated bundles may be distributed under the application's chosen terms as long as bundled dependency licenses are respected. Law-Rag still has no repository-level open-source license; this packaging choice does not change that decision.

Primary references checked:

- https://pyinstaller.org/en/stable/
- https://pyinstaller.org/en/stable/operating-mode.html
- https://pyinstaller.org/en/stable/license.html

## Why not onefile for the first release

PyInstaller one-file mode extracts support files into a temporary directory before execution, starts more slowly, and is harder to inspect/debug. The official documentation recommends proving one-folder behavior first.

Law-Rag also has several runtime-sensitive assets:

```text
PDFium binary data
frontend static files
public legal.db / retrieval.db
runtime diagnostics
third-party notices
```

Keeping these visible in the first bundle makes failures and license-notice handling easier to verify. One-file remains a later optional experiment, not a Stage 11D goal.

## Alternative 1 — CPython embeddable distribution

The official Python Windows documentation describes the embeddable distribution as a minimal, isolated Python environment intended to be part of another application. It does not include pip, and using pip as normal package management is not supported; third-party packages are expected to be vendored by the application installer. A simple batch/shortcut launcher is possible, but a polished launcher requires additional native integration/path work.

This is technically viable, but it shifts more responsibility to Law-Rag for:

- Python path construction;
- third-party package vendoring;
- DLL/package layout;
- launcher behavior;
- update compatibility.

That is more packaging code than necessary for the first release bundle.

Primary reference:

- https://docs.python.org/3/using/windows.html#the-embeddable-package

## Alternative 2 — Nuitka standalone

Nuitka's current documentation supports standalone Windows distributions and recommends proving standalone mode before one-file. The current stable release page reports Nuitka 4.1.3. Its Windows build path may require or automatically obtain a C compiler toolchain.

Nuitka is a reasonable future option when compilation/performance/IP-related needs justify the additional build complexity. Law-Rag currently needs reliable redistribution and transparent debugging more than Python-to-C compilation, so Nuitka is not selected for Stage 11D.

The standard edition is AGPLv3 with an exception for generated binaries, according to the project's current download/license page.

Primary references:

- https://nuitka.net/doc/download.html
- https://nuitka.net/user-documentation/use-cases.html
- https://nuitka.net/user-documentation/tutorial-setup-and-build.html

## Frontend release policy

Current development uses Vite on port 5173. That is not acceptable as the end-user release path.

Stage 11D will build `frontend/dist/` using Node during the bundle build, then include those static files in the packaged application. FastAPI will serve the production assets on the same local origin as the API.

Target release behavior:

```text
Law-Rag.exe
  -> starts local FastAPI on 127.0.0.1
  -> serves /api/*
  -> serves built frontend assets
  -> opens the local workstation URL
```

Node.js, npm, TypeScript and Vite are therefore **build-time tools**, not runtime prerequisites for the end user.

Important current blocker: the repository has no `frontend/package-lock.json`. `npm install` currently resolves from semver ranges, so the frontend build is not yet release-reproducible. Stage 11D must add and use a lockfile before completion.

## Base bundle scope

The first bundle includes only the reliable base/native-PDF path:

- CPython runtime collected by PyInstaller;
- FastAPI/Uvicorn backend;
- native PDF extraction and PDFium rendering dependency;
- image/Pillow support already used by the base backend;
- deterministic contract/rule layers;
- checked-in public legal seed transformed into generated `legal.db`;
- lexical/exact `retrieval.db` generated from the public legal store;
- production frontend static assets;
- diagnostics and integrity APIs/commands;
- config template and third-party notices/inventory.

It does not include real user runtime data.

## OCR policy for the first bundle

PaddlePaddle CPU + PaddleOCR remain an external optional installation for the first release bundle.

Reasons:

- heavyweight dependency tree and binary runtime;
- OCR models are downloaded separately and should remain explicit local user data/cache;
- native-text PDFs remain fully supported without OCR;
- forcing OCR into the base bundle would make the first release materially larger and harder to validate.

PaddleOCR's current repository license is Apache-2.0, but optional redistribution would also require checking the exact PaddlePaddle wheel and transitive/native notices before changing this policy.

## Semantic retrieval policy for the first bundle

`sentence-transformers` / BGE / PyTorch are not bundled in the first base release.

Policy:

```text
Exact + lexical/BM25: bundled base path
semantic/BGE: external optional install / later bundle experiment
model weights: never committed; explicit local download only
```

Sentence Transformers is Apache-2.0; PyTorch's installed distribution includes multiple third-party license obligations. These are manageable, but they add substantial bundle size and notice complexity without being required for the base retrieval path.

## Legal/retrieval asset policy

The release build will deterministically create public release assets from the checked-in seed:

```text
legal_data/seed/manifest.json
  -> legal.db
  -> lexical retrieval.db
```

The build may include those generated public databases in the release folder so first launch works offline. Their source fingerprint/schema/version must be recorded in release metadata.

Semantic vectors are not included in the first base asset set.

## Provider policy

DeepSeek and Kimi remain external, opt-in network providers.

The bundle contains only configuration names/default endpoints already used by the application. It never contains:

- API key values;
- Authorization headers;
- private provider responses;
- hidden reasoning.

Users provide `DEEPSEEK_API_KEY` and `MOONSHOT_API_KEY` locally when they intentionally use those stages.

## License/notices policy

Stage 11D does **not** claim full redistribution compliance merely because individual projects are permissively licensed.

Before a release artifact is called distributable, the build must collect/review notices for the actual resolved binaries. In particular, pypdfium2 states that binary PDFium distributions must ship PDFium and relevant third-party dependency licenses. The bundle therefore needs a generated third-party notice set derived from the exact installed wheels, not a hand-written statement alone.

No Law-Rag repository license is added by this stage.
