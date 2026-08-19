# Windows Packaging Decision

Law-Rag uses an inspectable Windows **PyInstaller onedir** distribution. Stage 11D established the base packaging architecture; Stage 14.4 bundled the pinned Paddle OCR runtime and Stage 14.5 adds the exact verified PP-OCR detector/recognizer assets required for offline inference.

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
PaddlePaddle/PaddleOCR/PaddleX runtime bundled
PP-OCRv6 medium detector + recognizer bundled from verified build-time fetch
semantic ML stack excluded from the base bundle
```

The distributable target remains an inspectable folder inside a portable ZIP, not an installer and not a one-file executable.

## Why PyInstaller onedir

The packaging architecture is optimized for:

- no Python installation on the end-user machine;
- no Node/Vite development server at runtime;
- inspectable PDFium/Paddle native binaries, local OCR models, legal assets, frontend assets and notices;
- easier debugging than a self-extracting one-file build;
- clean Windows-specific CI builds;
- no audit-architecture rewrite merely for packaging.

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

The OCR runtime layer then installs:

```text
paddlepaddle==3.3.0
backend/requirements-release-ocr-lock-windows.txt
```

using the official PaddlePaddle CPU wheel index and exact `--no-deps` pins, followed by `pip check`.

The base release lock remains authoritative for overlapping packages such as:

```text
pypdfium2==5.12.1
Pillow==12.3.0
```

This prevents PaddleOCR's unconstrained dependency resolver from silently drifting the already validated PDF/image stack.

Before PyInstaller runs, the isolated environment performs a local import/native validation through `app.ocr_runtime.probe_ocr_runtime(import_modules=True, run_native_check=True)`.

The release bundle records:

```text
python-resolved.txt
python-runtime.json
release-metadata.json
public-assets-metadata.json
ocr-models-manifest.json
```

`release-metadata.json` fingerprints both the base and OCR exact locks.

## OCR runtime packaging — Stage 14.4

The Windows onedir contains:

```text
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
exact transitive OCR Python/runtime closure
Paddle native DLL/PYD files
Python distribution metadata required by frozen runtime checks
```

`release/law_rag.spec` explicitly collects Paddle, PaddleOCR and PaddleX Python modules/data/native libraries.

The frozen executable exposes:

```text
Law-Rag.exe --diagnose-ocr-runtime
```

This validates exact runtime versions, imports Paddle/PaddleOCR and runs `paddle.utils.run_check()` without constructing the OCR pipeline or selecting models.

## Fixed offline OCR models — Stage 14.5

The production Windows bundle now also contains exactly:

```text
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

Git does **not** contain the model payloads. `release/ocr-models-manifest.json` contains the approved official Paddle archive URLs, Apache-2.0 model-license identity, archive SHA-256, archive roots, deterministic packaged directory names, exact required files and per-file SHA-256 values.

Locked archive SHA-256 values:

```text
PP-OCRv6_medium_det  144d0621e059566e5086e228829171591c144c2deb07b2dad4962214fbabfcf7
PP-OCRv6_medium_rec  4eecc1c6a4623765042e6fc15446da0da110b7d875b6b72b2d351d2b2dbd4da6
```

During a clean Windows release build Law-Rag:

1. downloads only those approved official Paddle archives;
2. verifies archive SHA-256 before accepting the payload;
3. rejects unsafe tar paths, links and device entries;
4. extracts to ignored build storage;
5. verifies the exact inference file set and per-file SHA-256;
6. places the approved model directories under the frozen release asset root;
7. fails the build if upstream content changes.

Runtime model integrity is rechecked before PaddleOCR construction. Missing, corrupt or unexpected files fail visibly. The release does not silently download a replacement model or switch to another model identity.

## Fixed PaddleX OCR configuration

Law-Rag packages a minimal fixed OCR pipeline configuration containing only the approved detector and recognizer. Production passes that file explicitly through `paddlex_config` rather than depending on PaddleX locating its package-relative default configuration.

The fixed configuration disables:

```text
document orientation classification
document unwarping
text-line orientation
```

so runtime OCR cannot implicitly request `PP-LCNet`, `UVDoc` or other auxiliary model assets.

## Frozen PaddleX metadata boundary

PaddleX `3.7.2` checks its `ocr-core` extra through `importlib.metadata.version(...)`. In a PyInstaller executable the Python modules can be present while their distribution metadata is absent, causing PaddleX to falsely report that OCR dependencies are missing.

Therefore `release/law_rag.spec` explicitly preserves `.dist-info` metadata for:

```text
imagesize
opencv-contrib-python
pyclipper
pypdfium2
python-bidi
shapely
```

These are already members of the exact OCR runtime closure; this is packaging metadata preservation, not an additional dependency set or a bypass of PaddleX's dependency gate.

## CPU inference compatibility boundary

For the pinned PaddlePaddle `3.3.0` / PP-OCR Windows CPU path, production uses:

```text
engine = paddle_static
enable_mkldnn = false
```

The Stage 14.5 real packaged inference regression exposed a oneDNN/PIR `ArrayAttribute<Double>` failure with MKLDNN enabled. Disabling that branch preserves the pinned CPU/static-engine path and is treated as a tested release compatibility requirement. Do not remove this setting merely as a performance optimization without a replacement Windows real-inference regression proving the upstream issue is gone.

## Offline inference diagnostics

The frozen executable exposes:

```text
Law-Rag.exe --diagnose-ocr-models
Law-Rag.exe --diagnose-ocr-inference <image>
```

The model diagnostic verifies the approved local file set/hashes without initializing inference. The inference diagnostic uses the production `PaddleOcrProvider` against a local image.

Windows CI runs the frozen inference path with HTTP/HTTPS/ALL proxy variables pointed at an unusable local endpoint. A successful Stage 14.5 inference therefore cannot depend on Hugging Face, BOS, Paddle model caches or a remote OCR service.

Diagnostic failures preserve the exception cause chain so Paddle/PaddleX packaging regressions remain actionable instead of collapsing into a generic wrapper message.

## Private runtime and cache scan semantics

Mutable Law-Rag private application data belongs beside `Law-Rag.exe` under root locations such as:

```text
runtime/
uploads/
jobs/
logs/
data_private/
benchmark_private/
```

Those application-data locations are forbidden from release artifacts.

Do **not** reject every recursively nested directory named `runtime` or `logs`: third-party Python packages can legitimately use those generic names for code. PaddleX itself contains dependency-internal runtime modules.

Downloaded Paddle caches remain forbidden, including identities such as:

```text
.paddlex
.paddleocr
model_cache
official_models
```

The two approved PP-OCR model directories are allowed only through the deterministic Stage 14.5 release path and are verified against the manifest. Arbitrary or downloaded model/cache directories remain forbidden.

The deterministic RC archive scanner follows the same boundary.

## Frontend release policy

Development may use Vite on port 5173, but the end-user release does not. `frontend/package-lock.json` is committed with lockfile version 3. CI and release builds use `npm ci`. Node.js, npm, TypeScript and Vite are build-time tools only. The compiled SPA is served by the bundled FastAPI process on loopback.

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
- fixed verified PP-OCRv6 medium detector + recognizer assets;
- deterministic contract/rule layers;
- generated public legal/retrieval databases;
- production frontend static assets;
- runtime/job/model integrity diagnostics;
- release metadata and third-party notice evidence;
- DeepSeek/Kimi adapters, but no credentials.

Still excluded:

```text
Paddle downloaded caches / unapproved OCR models
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
user runtime/jobs
API keys
private benchmark data
```

## Provider policy

DeepSeek and Kimi remain external opt-in network providers. The bundle never contains API keys, Authorization headers, private provider responses or hidden reasoning. Local OCR does not use those providers.

## License/notices policy

`app.release_notices_cli` collects license/COPYING/NOTICE material from the exact installed base + OCR runtime distributions. Vite emits bundled frontend license metadata. `release/ocr-models-manifest.json` separately records the approved PP-OCR model provenance/license identity and exact payload hashes.

Generated notice files and the dependency inventory are review evidence; their existence is not represented as automatic legal-compliance approval.

## Stage 14.4 clean Windows validation

Authoritative runtime-only full run: **Law-Rag CI #648 (`32125214669`)**.

It proved the exact OCR runtime closure, offline Paddle native self-check, PyInstaller onedir build, PDFium preservation, privacy/cache scans, deterministic RC archive and final extracted-RC user flow.

## Stage 14.5 clean Windows validation

Authoritative fixed-model/offline-inference run: **Stage 14.5 OCR model assets #64 (`32145367670`)**.

A clean Windows runner validated:

```text
exact base + OCR runtime locks
locked official detector/recognizer download + SHA-256
PyInstaller onedir build
verified model resolution
frozen model integrity with network unavailable
real production PaddleOCR inference with network unavailable
packaged base/PDF workflow smoke
deterministic portable RC ZIP + manifest
fresh extraction of final RC ZIP
final extracted RC user-flow smoke
model payload absent from Git history/tracked files
onedir + portable RC artifact upload
```

Companion normal CI #727 (`32145367680`) passed:

```text
backend pytest                      315 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

This closes Stage 14.5. The next packaging/product integration problem is **Stage 14.6 Pipeline + Home integration**, followed by the final combined Stage 14.7 regression.
