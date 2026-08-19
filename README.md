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

The backend/source layer already supports modern DOCX and the Windows release already contains fixed offline OCR runtime/models. Stage 14.6 is the remaining product integration slice that makes the complete source set explicit through Home/intake and the authoritative Pipeline.

Law-Rag does not use a third model to vote on DeepSeek/Kimi disagreement. Unsupported, conflicting, stale, incomplete or insufficient-evidence states remain visible for human review.

## Status

**Stage 13G is complete. Stage 14.1–14.5 are complete. Stage 14.6 — Pipeline + Home integration — is next.**

Validated Stage 14 foundations now include:

- cross-format Evidence identities with typed PDF/image/DOCX source anchors;
- safe modern DOCX OOXML ingestion without synthetic page numbers;
- logical DOCX Source Viewer navigation to exact paragraphs/table cells;
- bundled Windows PaddlePaddle/PaddleOCR/PaddleX runtime;
- fixed `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec` assets fetched from approved official Paddle sources during clean release builds;
- archive and per-file SHA-256 model integrity validation;
- no runtime model download/fallback;
- real frozen Windows OCR inference with network unavailable;
- deterministic RC ZIP plus extracted-RC user-flow validation.

The only active implementation scope is [`CURRENT_TASK.md`](CURRENT_TASK.md).

## Main routes

```text
/           contract intake + production Pipeline status
/results    architecture-aware batch/result queue
/workspace  professional evidence-linked review workstation
/developer  Stage 13 read-only diagnostics; Legacy / RC2 tools are isolated below
```

Opening Results, Workspace or the Stage 13 Developer diagnostic surface reads persisted artifacts and does not implicitly call DeepSeek/Kimi.

## Provider boundary

Local ingest/OCR/structure/rules run before the first cloud-model phase. With:

```text
provider_mode = REQUIRE_APPROVAL
```

Law-Rag pauses before the Audit Planner's first actual provider call. A configured provider is still required before a provider request can run; approval is not a substitute for provider configuration.

Every later Planner/DeepSeek/Kimi request crosses the persisted provider/cancellation boundary independently. An already-started HTTP request cannot be recalled, but cancellation blocks subsequent requests.

Local OCR is independent of those cloud-provider permissions.

## Quick start on Windows

For source/development use:

- Python 3.11 or newer;
- Node.js 22 LTS recommended.

Base setup:

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

The packaged Windows onedir/portable RC does **not** require the end user to install Python, pip, PaddlePaddle, PaddleOCR or download OCR weights separately.

Pinned packaged OCR path:

```text
PaddlePaddle CPU 3.3.0
PaddleOCR 3.7.0
PaddleX 3.7.2
PP-OCRv6_medium_det
PP-OCRv6_medium_rec
```

`release/ocr-models-manifest.json` freezes official model provenance plus archive/file SHA-256 values. Model binaries are not committed to Git; clean Windows builds fetch and verify them before packaging.

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

## Issue V1 private job artifacts

Generated/private job data remains under ignored runtime paths:

```text
runtime/uploads/<job-id>/source.<ext>
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json
runtime/jobs/<job-id>/contract.json
runtime/jobs/<job-id>/audit-rules.json
runtime/jobs/<job-id>/pipeline.json
runtime/jobs/<job-id>/pipeline-control.json
runtime/jobs/<job-id>/audit-plan.json
runtime/jobs/<job-id>/issue-legal-context.json
runtime/jobs/<job-id>/issue-primary-audit.json
runtime/jobs/<job-id>/issue-secondary-review.json
runtime/jobs/<job-id>/issue-review-report.json
runtime/jobs/<job-id>/human-review.json
```

Historical RC2 jobs may also contain:

```text
ai-audit.json
secondary-review.json
review-report.json
```

Those files remain readable for `LEGACY_RC2` jobs. After an explicit legacy migration they are historical only and are not treated as authoritative Issue V1 results.

## Cross-format Evidence

Evidence IDs identify evidence; they do not encode source location. Typed source anchors carry location semantics.

```text
PDF/image -> PAGE_TEXT / PAGE_REGION
DOCX      -> DOCX_PARAGRAPH / DOCX_TABLE_CELL / DOCX_EMBEDDED_IMAGE
```

DOCX never receives fake page numbers. The logical Source Viewer resolves structural Evidence directly to the corresponding paragraph or table-cell paragraph.

Unsupported/partial DOCX constructs remain explicit source warnings instead of being silently dropped.

## Offline OCR integrity

Production OCR permits only the pinned detector and recognizer. Before pipeline construction Law-Rag validates the exact packaged model directories and file hashes and passes explicit local model paths plus a fixed minimal PaddleX OCR config.

The packaged path does not initialize document-orientation, unwarping or text-line-orientation model branches and does not silently use Hugging Face, BOS or downloaded Paddle caches at runtime.

PyInstaller preserves PaddleX `ocr-core` distribution metadata required by `importlib.metadata` dependency checks. For the pinned Windows PaddlePaddle 3.3.0 CPU path, `enable_mkldnn=False` is kept as a tested compatibility requirement after the real packaged regression exposed a oneDNN/PIR failure with that branch enabled.

## Audit Plan and coverage

`audit-plan.json` is the authoritative review scope for Issue V1. Every canonical clause/block is assigned one planning coverage state:

```text
REVIEWED_WITH_ISSUE
REVIEWED_NO_SPECIFIC_ISSUE
```

`REVIEWED_NO_SPECIFIC_ISSUE` means planning coverage only. It is never presented as a legal-safe conclusion.

Short contracts use a bounded direct Planner pass. Long contracts use complete-object chunk passes plus bounded global planning synthesis; canonical objects are not character-truncated merely to fit a model request.

## Legal evidence and retrieval

Canonical legal identity is:

```text
authority -> authority version -> article / Legal Evidence ID
```

Applicability is deterministic:

```text
effective_date <= as_of < end_date_exclusive
```

Retrieval combines:

```text
exact citation
+ SQLite FTS5 trigram / BM25
+ optional local BGE semantic retrieval
+ weighted reciprocal-rank fusion
```

The checked-in public legal seed is deliberately `CURATED_EXCERPT`. **Absence from the local seed is never evidence that no applicable legal rule exists.**

## Human review

Issue V1 human decisions bind to `AuditPlan.issue_id` and append revisions to `human-review.json`.

The server snapshots current Contract Evidence / Legal Evidence references and binds each revision to the current `issue-review-report.json` artifact fingerprint. If the audit chain later changes, the old revision remains visible as stale and cannot close the new review state.

Only fresh final `CONFIRMED` or `REJECTED` decisions close a mandatory Issue review. `NEEDS_MORE_REVIEW`, `UNREVIEWED`, stale revisions and incomplete planning coverage remain outstanding.

Legacy finding/omission review revisions remain readable without being fabricated into Issue identities.

## Results priority

The `/results` queue uses deterministic workload ordering:

```text
unresolved human review
> possible omission
> material disagreement
> critical
> high
> insufficient evidence
> medium
> low
```

This is an audit workload priority, **not a legal-risk probability or correctness score**.

## Developer diagnostics

`/developer` defaults to GET-only Stage 13 diagnostics for:

```text
architecture
pipeline
Audit Plan
Issue Legal Context
Issue Primary Audit
Issue Secondary Review
Issue Comparison
Human Review
```

Missing, stale/conflicting and invalid artifacts remain explicit. Historical Stage 1–9 execution tools are retained only under the collapsed `Legacy / RC2` area.

## Validation

Stage 14.5 authoritative packaged validation:

```text
Stage 14.5 OCR model assets #64 (32145367670)
  clean Windows onedir + locked models         PASS
  frozen model integrity, network unavailable  PASS
  real frozen OCR, network unavailable         PASS
  packaged base workflow                       PASS
  deterministic RC ZIP + manifest              PASS
  extracted final RC user flow                 PASS
  onedir + RC artifact upload                  PASS
```

Companion normal CI #727 (`32145367680`):

```text
backend pytest: 315 passed, 5 skipped, 1 warning
public deterministic quality gates: PASS
frontend production build: PASS
Windows exact OCR dependency smoke: PASS
```

The remaining warning is the existing Starlette TestClient/httpx deprecation warning.

No additional global Kimi coverage-synthesis call is part of Stage 13. The current regression evidence did not demonstrate a missing cross-Issue failure mode that justifies adding another provider call. That decision should be revisited only if later expert/benchmark evidence demonstrates such omissions.

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

This repository is public. Treat every committed file as public information.

Do not commit:

- real/private contracts;
- API keys or `.env` secrets;
- runtime uploads or generated job reports;
- private benchmark labels;
- model caches or private vector stores;
- logs containing private contract text.

See [`AGENTS.md`](AGENTS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`CURRENT_TASK.md`](CURRENT_TASK.md), and [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
