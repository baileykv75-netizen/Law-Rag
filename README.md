# Law-Rag

Law-Rag is a local-first contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application rather than a generic legal chatbot. Extraction, OCR, canonical structure, deterministic rules, legal evidence and retrieval run locally. External model calls are explicit and receive bounded evidence packages rather than unrestricted raw-file access.

## Current production flow

New jobs use the Stage 13 `ISSUE_V1` architecture:

```text
PDF / JPG / JPEG / PNG / DOCX
  -> reliable native PDF/DOCX text or local OCR where required
  -> cross-format Source Evidence
  -> evidence-grounded Canonical Contract
  -> deterministic audit rules
  -> Audit Planner + explicit canonical-object coverage
  -> issue-based version-aware Legal RAG
  -> DeepSeek primary audit, one bounded call per AuditPlan Issue
  -> Kimi independent finding + coverage review, one bounded call per Issue
  -> deterministic Issue comparison
  -> issue-review-report.json
  -> append-only human review
  -> /results + /workspace
```

Source-format differences stop at the Evidence/Canonical boundary. The Issue V1 Planner/RAG/DeepSeek/Kimi/comparison/Human Review topology does not branch on PDF/image/DOCX.

Law-Rag does not use a third model to vote on DeepSeek/Kimi disagreement. Unsupported, conflicting, stale, incomplete or insufficient-evidence states remain visible for human review.

## Status

**Stage 14 is complete. Stage 15 — official legal corpus expansion + update/versioning + retrieval tuning — is next.**

Stage 14 delivered:

- cross-format Evidence identities with typed PDF/image/DOCX source anchors;
- safe modern DOCX OOXML ingestion without synthetic page numbers;
- logical DOCX Source Viewer navigation to exact paragraphs/table cells;
- Home/intake support for PDF, DOCX, JPG/JPEG and PNG;
- source warnings preserved from ingestion through Home/Workspace;
- source-format-aware Pipeline loading for historical paginated PDF/image Evidence and DOCX `SourceEvidenceArtifact`;
- bundled Windows PaddlePaddle/PaddleOCR/PaddleX runtime;
- fixed `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec` assets fetched from approved official Paddle sources during clean release builds;
- archive and per-file SHA-256 model integrity validation;
- no runtime model download/fallback;
- real frozen Windows OCR inference with outbound network unavailable;
- final packaged Windows DOCX/PDF/image/provider-boundary/privacy/RC regression.

The only active implementation scope is [`CURRENT_TASK.md`](CURRENT_TASK.md).

## Main routes

```text
/           contract intake + production Pipeline status
/results    architecture-aware batch/result queue
/workspace  professional evidence-linked review workstation
/developer  Stage 13 read-only diagnostics; Legacy / RC2 tools are isolated below
```

Opening Results, Workspace or the Stage 13 Developer diagnostic surface reads persisted artifacts and does not implicitly call DeepSeek/Kimi.

## Supported inputs

```text
native PDF
scanned PDF
JPG / JPEG / PNG
modern DOCX
```

Legacy `.doc` is not accepted as DOCX.

DOCX has no stable source pagination. It uses structural anchors such as:

```text
DOCX_PARAGRAPH
DOCX_TABLE_CELL
DOCX_EMBEDDED_IMAGE
```

The UI therefore shows DOCX as structural Source Evidence rather than inventing page 1 or presenting `0 pages` as if it were an error.

## Provider boundary

Local ingest/OCR/structure/rules run before the first cloud-model phase. With:

```text
provider_mode = REQUIRE_APPROVAL
```

Law-Rag pauses before the Audit Planner's first actual provider call. A configured provider is still required before a provider request can run; approval is not a substitute for provider configuration.

Every later Planner/DeepSeek/Kimi request crosses the persisted provider/cancellation boundary independently. An already-started HTTP request cannot be recalled, but cancellation blocks subsequent requests.

Stage 14 regression proves a native DOCX job can run the real local STRUCTURE + RULES stages and still stop at `AUDIT_PLAN`, 48%, with `PROVIDER_APPROVAL_REQUIRED` before the configured Planner can execute.

Local OCR is independent of cloud-provider permission.

## Windows OCR distribution

The packaged Windows onedir/portable RC does **not** require the end user to install Python, pip, PaddlePaddle, PaddleOCR or download OCR weights separately.

Pinned packaged OCR path:

```text
CPython 3.12.10
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

`release/ocr-models-manifest.json` freezes official model provenance plus archive/file SHA-256 values. Model binaries are not committed to Git; clean Windows builds fetch and verify them before packaging.

Production OCR permits only the pinned detector and recognizer. Law-Rag validates the exact packaged model directories and file hashes and passes explicit local model paths plus a fixed minimal PaddleX OCR config. The runtime path does not silently use Hugging Face, BOS or downloaded Paddle caches.

PyInstaller preserves PaddleX `ocr-core` distribution metadata required by `importlib.metadata` dependency checks. For the pinned Windows PaddlePaddle 3.3.0 CPU path, `enable_mkldnn=False` remains a tested compatibility requirement after packaged regression exposed a oneDNN/PIR failure when that branch was enabled.

## Development quick start

For source/development use:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

```text
setup-dev.bat
rebuild-legal-seed.bat
build-retrieval-index.bat
start-dev.bat
```

Optional local semantic retrieval:

```text
setup-rag-semantic-cpu.bat
build-retrieval-index-semantic.bat
```

Initial local embedding provider:

```text
BAAI/bge-small-zh-v1.5
```

Developer OCR setup remains available for source checkouts:

```text
setup-ocr-cpu.bat
```

### Configure DeepSeek

```bat
set DEEPSEEK_API_KEY=<your-local-key>
set DEEPSEEK_BASE_URL=https://api.deepseek.com
set DEEPSEEK_MODEL=deepseek-v4-pro
```

### Configure Kimi

```bat
set MOONSHOT_API_KEY=<your-local-key>
set MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
set MOONSHOT_MODEL=kimi-k3
```

Never commit real keys or a private `.env` file.

## Cross-format Evidence

Evidence IDs identify evidence; they do not encode source location. Typed source anchors carry location semantics.

```text
PDF/image -> PAGE_TEXT / PAGE_REGION
DOCX      -> DOCX_PARAGRAPH / DOCX_TABLE_CELL / DOCX_EMBEDDED_IMAGE
```

Unsupported/partial DOCX constructs remain explicit source warnings instead of being silently dropped. Pipeline and Workspace validate the persisted source representation rather than forcing DOCX into the historical paginated schema.

## Audit Plan, legal evidence and review

`audit-plan.json` is the authoritative review scope for Issue V1. Every canonical clause/block receives explicit planning coverage.

Canonical legal identity is:

```text
authority -> authority version -> article / Legal Evidence ID
```

Retrieval combines exact citation lookup, SQLite FTS5 trigram/BM25, optional local BGE semantic retrieval and weighted reciprocal-rank fusion. Absence from a checked-in `CURATED_EXCERPT` source is never proof that no applicable legal rule exists.

Human Review is append-only and fingerprint-bound. Only fresh final `CONFIRMED` or `REJECTED` decisions close a mandatory Issue review; stale or incomplete states remain visible.

## Stage 14 final validation

Normal regression on the validated Stage 14.7 head:

```text
Law-Rag CI #755 (32245812433)
  backend pytest: 320 passed, 5 skipped, 1 warning
  public deterministic quality gates: PASS
  frontend production build: PASS
  Windows exact OCR dependency smoke: PASS
```

Final packaged Windows regression:

```text
Stage 14.7 final Windows release validation (32245812422)
  clean Windows onedir + exact runtime/models      PASS
  frozen OCR model integrity, network unavailable  PASS
  packaged PDF/OCR/UI/privacy smoke                PASS
  packaged DOCX Pipeline + image OCR API smoke      PASS
  deterministic portable RC ZIP + manifest          PASS
  extracted final RC complete user-flow smoke       PASS
  model payload absent from Git                     PASS
  onedir + RC artifact upload                       PASS
```

Validated artifacts:

```text
law-rag-windows-onedir-stage14-7
law-rag-windows-x64-stage14-7
```

The remaining pytest warning is the existing Starlette TestClient/httpx deprecation warning.

## Core engineering principles

1. **Evidence first.** Material conclusions trace to exact contract evidence; legal conclusions additionally trace to canonical Legal Evidence.
2. **Native text before OCR.** Reliable native text is not degraded unnecessarily.
3. **Deterministic before probabilistic.** Machine-checkable conditions stay in code.
4. **One canonical contract model.** Downstream systems do not independently reinterpret source files.
5. **Complete planning coverage before Issue reasoning.** Missing review scope remains visible.
6. **No fabricated legal authority.** Model citations must come from supplied canonical Legal Evidence.
7. **Post-model validation, not prompt trust.** Invented IDs/versions fail closed.
8. **Two-model agreement is not proof.** Disagreement and uncertainty remain reviewable.
9. **Provider transmission is explicit.** Persisted approval/cancel policy governs every external model request.
10. **Human review is append-only.** Decisions never rewrite source/model/legal evidence.
11. **Legacy compatibility is explicit.** Issue V1 and RC2 artifacts are not silently mixed.
12. **Local-first private data.** Private artifacts and model caches stay outside Git.

## Repository safety

This repository is public. Do not commit real/private contracts, API keys, runtime uploads, generated private reports, private benchmark labels, model caches/private vector stores, or logs containing private contract text.

See [`AGENTS.md`](AGENTS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`CURRENT_TASK.md`](CURRENT_TASK.md), and [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
