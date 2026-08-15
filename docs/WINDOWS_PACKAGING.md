# Windows Packaging Decision

Stage 11D converts the stable local development application into a reproducible, inspectable Windows release bundle. The packaging choice was re-verified against current primary documentation on 2026-08-15 before adding a packaging dependency.

## Decision

The first Law-Rag release bundle uses:

```text
Windows x64
CPython 3.12.10 exactly
Node.js 22.23.2 + npm 10.9.8 for build only
PyInstaller 6.22.0
one-folder / onedir mode
isolated exact Python release lock
npm package-lock v3 + npm ci
FastAPI serves production frontend assets
OCR and semantic ML stacks excluded from the base bundle
```

The first distributable target is an inspectable folder, not an installer and not a one-file executable.

## Why PyInstaller onedir

PyInstaller's current stable documentation says it supports modern Python/Windows, bundles the active Python interpreter with imported modules, and produces a self-contained folder or optional single executable. Its default one-folder mode is easier to diagnose because collected files remain visible.

That matches Law-Rag's priorities:

- no Python installation on the end-user machine;
- no Node/Vite development server at runtime;
- inspectable PDFium, legal assets, frontend assets and notices;
- easier debugging than a self-extracting one-file build;
- Windows-specific bundle creation on clean GitHub Actions Windows runners;
- no architecture rewrite merely for packaging.

PyInstaller's current license documentation uses GPL-2.0 with a bundling exception, with selected Apache-2.0 files, and permits generated bundles to use the application's chosen terms subject to licenses of bundled dependencies. Law-Rag still has no repository-level open-source license; Stage 11D does not change that owner decision.

Primary references checked:

- https://pyinstaller.org/en/stable/
- https://pyinstaller.org/en/stable/operating-mode.html
- https://pyinstaller.org/en/stable/license.html

## Why not onefile for the first release

PyInstaller one-file mode extracts support files to a temporary directory before execution, starts more slowly, and is harder to inspect/debug. The official guidance favors proving one-folder behavior first.

Law-Rag also has runtime-sensitive assets:

```text
PDFium binary data
frontend static files
public legal.db / retrieval.db
runtime diagnostics
third-party notices
```

One-file remains a later optional experiment, not a Stage 11D requirement.

## Alternatives rejected for the first bundle

### CPython embeddable distribution

The official Python Windows documentation describes the embeddable distribution as a minimal isolated Python environment. It does not include normal pip package-management support; third-party packages are expected to be vendored by the application installer/integration layer.

It is viable but makes Law-Rag own more path, DLL, vendoring, launcher and update logic than necessary for the first release.

Primary reference:

- https://docs.python.org/3/using/windows.html#the-embeddable-package

### Nuitka standalone

Nuitka supports Windows standalone/one-file deployment and recommends validating standalone before one-file. It also introduces a C/C++ compilation toolchain and more build complexity than Law-Rag currently needs.

Nuitka remains a future option if compilation/performance/IP-related needs justify that cost.

Primary references:

- https://nuitka.net/doc/download.html
- https://nuitka.net/user-documentation/use-cases.html
- https://nuitka.net/user-documentation/tutorial-setup-and-build.html

## Reproducible build boundary

The Windows release build no longer installs into the GitHub runner/global Python environment.

`release/build-windows.ps1` requires exactly:

```text
CPython 3.12.10
Node.js 22.23.2
npm 10.9.8
```

It then creates a fresh ignored `release/.build-venv/` and installs:

```text
backend/requirements-release-lock-windows.txt
```

with `--no-deps`, followed by `pip check`.

This prevents runner-preinstalled tools such as pipx/argcomplete/filelock from silently becoming part of the release dependency set.

The release bundle records:

```text
python-resolved.txt
python-runtime.json
public-assets-metadata.json
```

for review/reproduction evidence.

## Frontend release policy

Development may continue to use Vite on port 5173, but the end-user release does not.

`frontend/package-lock.json` is now committed with lockfile version 3. CI and release builds use `npm ci`. Current locked direct tool/runtime versions include:

```text
react 19.2.8
react-dom 19.2.8
typescript 5.9.3
vite 8.2.1
```

The production build is collected into the PyInstaller onedir bundle. FastAPI serves the compiled SPA from the same loopback origin as `/api/*`.

Release behavior:

```text
Law-Rag.exe
  -> configures local runtime/public asset paths
  -> runs non-mutating Stage 11C diagnostics
  -> refuses non-loopback binding / duplicate port
  -> starts FastAPI on 127.0.0.1
  -> serves /api/*
  -> serves compiled React assets and SPA routes
  -> opens the local workstation URL unless --no-browser
```

Unknown `/api/*` routes remain JSON 404s and are never hidden behind the SPA fallback.

Node.js, npm, TypeScript and Vite are build-time tools only.

## Public legal/retrieval assets

The release build deterministically creates public release assets from the checked-in Stage 6 seed:

```text
legal_data/seed/manifest.json
  -> public-assets/legal/legal.db
  -> public-assets/legal/retrieval.db
```

The retrieval asset is Exact + FTS5/BM25 lexical only. Semantic vectors are not included.

`public-assets-metadata.json` records legal/retrieval hashes, schema/index metadata, article counts and legal-source fingerprint.

The bundled legal corpus remains a `CURATED_EXCERPT`. No-hit is never represented as proof that no relevant legal rule exists.

## Base bundle scope

Included:

- CPython collected by PyInstaller;
- FastAPI/Uvicorn;
- native PDF extraction;
- PDFium rendering;
- Pillow image support;
- deterministic contract/rule layers;
- generated public legal/retrieval databases;
- production frontend static assets;
- runtime/job integrity diagnostics;
- release metadata and third-party notice evidence;
- DeepSeek/Kimi adapters, but no credentials.

Excluded from the first base bundle:

```text
PaddlePaddle / PaddleOCR
OCR model weights
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
user runtime/jobs
API keys
private benchmark data
```

## OCR policy

PaddlePaddle CPU + PaddleOCR remain an external optional installation for the first release bundle. Native-text PDF workflows work without them.

This keeps the first bundle materially smaller and separates heavy OCR binaries/model downloads from the validated base application.

PaddleOCR's current project license is Apache-2.0, but exact PaddlePaddle/transitive/native redistribution obligations must be checked before any future bundled OCR variant.

## Semantic policy

The first bundle supports:

```text
Exact + lexical/BM25: bundled
semantic/BGE: external optional path
model weights: never committed; explicit local download only
```

Sentence Transformers is Apache-2.0; PyTorch distributions also contain third-party license material. They remain outside the first bundle.

## Provider policy

DeepSeek and Kimi remain external opt-in network providers.

The bundle never contains:

- API key values;
- Authorization headers;
- private provider responses;
- hidden reasoning.

Users provide `DEEPSEEK_API_KEY` and `MOONSHOT_API_KEY` locally if they intentionally invoke those stages.

## License/notices policy

Stage 11D does not claim license compliance merely from headline project licenses.

Vite 8's production `build.license` output is enabled and emits:

```text
frontend/dist/third-party-frontend-licenses.json
```

For Python/binary distributions, `app.release_notices_cli` reads the exact installed release lock environment, records package/version/license metadata, copies license/COPYING/NOTICE material into:

```text
THIRD-PARTY-NOTICES/python/
```

and emits:

```text
THIRD-PARTY-NOTICES/python-third-party-notices.json
```

pypdfium2 is treated specially: the build fails if its exact installed wheel does not expose PDFium/dependency license material. pypdfium2 explicitly states that PDFium and relevant dependency licenses must accompany binary distributions.

Generated notice files are evidence for human/release review; their existence alone is not represented as an automatic legal-compliance conclusion.

No Law-Rag repository license is added by Stage 11D.

## Clean Windows validation

A clean GitHub Actions Windows Server 2025 runner has already validated the exact locked base toolchain through:

```text
build PyInstaller onedir
Law-Rag.exe --diagnose --json
start Law-Rag.exe on loopback
GET /api/health -> 200
GET / -> compiled React shell
unknown /api/* -> explicit 404
upload inspectable onedir artifact
```

This validates the base packaging/runtime architecture. Stage 11D remains open until the newly automated notice extraction is included in the same clean-runner build and final release metadata/docs are reconciled.
