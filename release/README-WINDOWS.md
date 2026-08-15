# Law-Rag Windows Base Bundle

This Stage 11D bundle is an inspectable **one-folder** release candidate, not an installer and not a single-file executable.

## Start

Double-click:

```text
Law-Rag.exe
```

The launcher binds only to:

```text
http://127.0.0.1:8000/
```

and opens the local workstation in the default browser.

The browser UI and FastAPI backend are served from the same local process. Node.js, npm and Vite are not required on the end-user machine.

## Diagnose without starting

```text
Law-Rag.exe --diagnose
Law-Rag.exe --diagnose --json
```

Diagnostics are local and non-mutating. They do not call DeepSeek/Kimi, download OCR/BGE models, rebuild databases, or print API key values.

## Included base capabilities

The first base bundle is intentionally limited to the stable native-PDF path:

- PDF/JPG/PNG upload;
- native PDF extraction and PDFium page rendering;
- deterministic contract structure and rules;
- checked-in public curated legal seed compiled into `legal.db`;
- exact + lexical/BM25 legal retrieval;
- workstation UI and evidence navigation;
- local runtime/integrity diagnostics;
- optional DeepSeek/Kimi calls only when the user supplies credentials and triggers those stages.

The bundled legal seed remains a `CURATED_EXCERPT`, not a complete statement of Chinese law. A no-hit result cannot be interpreted as absence of a legal rule.

## Not included in the base bundle

These remain optional external/local extensions for Stage 11D:

```text
PaddleOCR / PaddlePaddle
OCR model weights
sentence-transformers / PyTorch
BAAI/bge-small-zh-v1.5 weights
```

Native-text PDF workflows remain available without those components.

## Local data

Private jobs are written below the extracted bundle directory at:

```text
runtime/
```

Do not place the release folder in a read-only directory. The packaged public `legal.db` and lexical `retrieval.db` live separately inside the application data collected by PyInstaller; they are not user job data.

## DeepSeek / Kimi

No API key is embedded in the bundle.

The current release launcher reads the same environment variables as the development application:

```text
DEEPSEEK_API_KEY
MOONSHOT_API_KEY
```

Provider calls are external network operations and remain explicit audit/review actions. Local navigation, extraction, deterministic rules and legal evidence inspection do not require those keys.

`config.env.example` is provided only as a reference. The current Stage 11D launcher does not silently load that file.

## Troubleshooting

If the application does not start, run:

```text
Law-Rag.exe --diagnose
```

Do not delete `runtime/` as a first troubleshooting step. Stage 11C diagnostics are designed to surface missing/stale/corrupt components without destructive auto-repair.

## Release metadata

The bundle includes:

```text
python-runtime.json
python-resolved.txt
_internal/release/public-assets-metadata.json
_internal/release/dependency-inventory.json
_internal/frontend-dist/third-party-frontend-licenses.json
```

These files support reproducibility and dependency/license review. Their presence does not by itself constitute a claim that every redistribution obligation has been completed; Stage 11D release validation still checks exact binary notices, especially PDFium/pypdfium2.
