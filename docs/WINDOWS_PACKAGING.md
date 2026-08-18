# Windows Packaging Decision

Law-Rag uses an inspectable Windows **PyInstaller onedir** distribution. Stage 11D established the base packaging architecture; Stage 14.4 extends that same architecture with a pinned local Paddle OCR runtime while keeping OCR model weights separate for Stage 14.5.

## Decision

Current Windows runtime baseline:

```text
Windows x64
CPython 3.12.10 exactly
Node.js 22.23.2 + npm 10.9.8 for build only
PyInstaller 6.22.0
one-folder / onedir mode
isolated exact base Python release lock
isolated exact OCR runtime lock
npm package-lock v3 + npm ci
FastAPI serves production frontend assets
PaddlePaddle/PaddleOCR runtime bundled
PP-OCR model weights excluded until Stage 14.5
semantic ML stack excluded from the base bundle
```

The distributable target remains an inspectable folder inside a portable ZIP, not an installer and not a one-file executable.

## Why PyInstaller onedir

The packaging architecture is optimized for:

- no Python installation on the end-user machine;
- no Node/Vite development server at runtime;
- inspectable PDFium/Paddle native binaries, legal assets, frontend assets and notices;
- easier debugging than a self-extracting one-file build;
- clean Windows-specific CI builds;
- no audit-architecture rewrite merely for packaging.

Primary PyInstaller references previously checked:

- https://pyinstaller.org/en/stable/
- https://pyinstaller.org/en/stable/operating-mode.html
- https://pyinstaller.org/en/stable/license.html

One-file remains a later optional experiment. The current product has runtime-sensitive assets and benefits from an inspectable onedir.

## Exact reproducible build boundary

`release/build-windows.ps1` requires exactly:

```text
CPython 3.12.10
Node.js 22.23.2
npm 10.9.8
```

It creates a fresh ignored `release/.build-venv/` and installs the base lock:

```text
backend/requirements-release-lock-windows.txt
```

with `--no-deps`.

Stage 14.4 then installs:

```text
paddlepaddle==3.3.0
```

from the official PaddlePaddle CPU wheel index, followed by:

```text
backend/requirements-release-ocr-lock-windows.txt
```

with `--no-deps`, then runs `pip check`.

The base release lock remains authoritative for overlapping packages such as:

```text
pypdfium2==5.12.1
Pillow==12.3.0
```

This avoids allowing PaddleOCR's unconstrained dependency resolver to silently drift the already validated PDF/image stack.

Before PyInstaller runs, the isolated environment performs a real local import/native validation through `app.ocr_runtime.probe_ocr_runtime(import_modules=True, run_native_check=True)`.

The release bundle records:

```text
python-resolved.txt
python-runtime.json
release-metadata.json
public-assets-metadata.json
```

`release-metadata.json` fingerprints both the base and OCR exact locks.

## OCR runtime packaging — Stage 14.4

The Windows onedir deliberately contains the **runtime layer**:

```text
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
exact transitive OCR Python/runtime closure
Paddle native DLL/PYD files
Python distribution metadata needed for version validation
```

`release/law_rag.spec` explicitly collects Paddle, PaddleOCR and PaddleX Python modules/data/native libraries. It no longer excludes Paddle/PaddleOCR.

The frozen executable exposes:

```text
Law-Rag.exe --diagnose-ocr-runtime
```

This command:

1. validates the exact installed PaddlePaddle/PaddleOCR distribution versions;
2. imports the packaged Paddle and PaddleOCR modules;
3. runs `paddle.utils.run_check()` against the frozen native runtime;
4. never constructs `PaddleOCR`;
5. never chooses/downloads PP-OCR model weights;
6. never calls DeepSeek/Kimi.

Windows CI runs this frozen diagnostic with HTTP/HTTPS/ALL proxy variables pointed at an unusable local endpoint. A Stage 14.4 runtime check therefore cannot pass by silently reaching a remote model/service.

## OCR model boundary — Stage 14.5

Stage 14.4 intentionally does **not** bundle or initialize PP-OCR detector/recognizer model weights.

The onedir/RC scanners recursively reject known cache/model identities including:

```text
.paddlex
.paddleocr
model_cache
official_models
PP-OCRv6*_det
PP-OCRv6*_rec
```

Stage 14.5 owns:

- exact detector/recognizer model identity;
- model licensing/redistribution review;
- deterministic local paths;
- SHA-256/integrity metadata;
- no-download production initialization;
- offline packaged OCR inference;
- visible missing/corrupt model failure behavior.

Thus Stage 14.4 proves **runtime distribution**, not complete zero-setup OCR inference.

## Private runtime scan semantics

Mutable Law-Rag private application data belongs beside `Law-Rag.exe` under root locations such as:

```text
runtime/
uploads/
jobs/
logs/
data_private/
benchmark_private/
```

Those bundle-root application data locations are forbidden from release artifacts.

Do **not** reject every recursively nested directory named `runtime` or `logs`: third-party Python packages can legitimately use those generic names for code. PaddleX, for example, contains dependency-internal runtime modules. OCR caches/model identities remain recursively forbidden because those names identify data/assets rather than generic package structure.

The deterministic RC archive scanner follows the same boundary, so final ZIP creation does not misclassify dependency code as user/private data.

## Frontend release policy

Development may use Vite on port 5173, but the end-user release does not.

`frontend/package-lock.json` is committed with lockfile version 3. CI and release builds use `npm ci`. Node.js, npm, TypeScript and Vite are build-time tools only. The compiled SPA is served by the bundled FastAPI process on loopback.

## Public legal/retrieval assets

The release build deterministically creates:

```text
legal_data/seed/manifest.json
  -> public-assets/legal/legal.db
  -> public-assets/legal/retrieval.db
```

The retrieval asset is Exact + FTS5/BM25 lexical only. Semantic vectors/BGE weights are not included.

The bundled legal corpus remains `CURATED_EXCERPT`. No-hit is never represented as proof that no relevant legal rule exists.

## Current bundle scope

Bundled runtime includes:

- CPython collected by PyInstaller;
- FastAPI/Uvicorn;
- native PDF extraction;
- PDFium rendering;
- Pillow image support;
- PaddlePaddle CPU / PaddleOCR / PaddleX runtime;
- deterministic contract/rule layers;
- generated public legal/retrieval databases;
- production frontend static assets;
- runtime/job integrity diagnostics;
- release metadata and third-party notice evidence;
- DeepSeek/Kimi adapters, but no credentials.

Still excluded:

```text
PP-OCR model weights and downloaded Paddle caches
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
user runtime/jobs
API keys
private benchmark data
```

## Semantic policy

The base bundle supports Exact + lexical/BM25 retrieval. Semantic/BGE remains an external optional path and its model weights are not bundled.

## Provider policy

DeepSeek and Kimi remain external opt-in network providers. The bundle never contains API keys, Authorization headers, private provider responses or hidden reasoning.

## License/notices policy

`app.release_notices_cli` now accepts multiple exact release locks and collects license/COPYING/NOTICE material from the installed **base + OCR** runtime distributions into:

```text
THIRD-PARTY-NOTICES/python/
THIRD-PARTY-NOTICES/python-third-party-notices.json
```

Vite continues to emit:

```text
frontend/dist/third-party-frontend-licenses.json
```

The dependency inventory classifies PaddlePaddle/PaddleOCR/PaddleX as bundled runtime components. PP-OCR model weights remain explicitly `NOT_REDISTRIBUTED_STAGE14_4` until Stage 14.5 completes its exact model review.

Generated notice files are review evidence; their existence is not represented as automatic legal-compliance approval.

## Stage 14.4 clean Windows validation

Authoritative full run: **Law-Rag CI #648 (`32125214669`)**.

A clean Windows runner validated:

```text
exact base + OCR locks + pip check
Paddle/PaddleOCR import with network unusable
Paddle CPU native self-check
PyInstaller onedir build
exact Paddle/PaddleOCR/PaddleX pins in resolved inventory
Paddle native DLL/PYD presence
PDFium DLL preservation
no private app runtime data in bundle
no OCR cache/model payloads in bundle
Law-Rag.exe --diagnose
Law-Rag.exe --diagnose-ocr-runtime with network unusable
all four frontend routes / API
native PDF upload + PDFium render
deterministic portable RC ZIP + manifest
fresh extraction of final RC ZIP
final RC user-flow smoke
artifact upload
```

This closes Stage 14.4. The next packaging problem is **Stage 14.5 fixed/offline OCR model distribution**, not another Python/Paddle runtime installation step.
