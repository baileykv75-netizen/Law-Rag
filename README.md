# Law-Rag

Law-Rag is a local-first contract audit assistant for personal research, testing, and professional review workflows.

The target product is a Windows-friendly local application rather than a generic legal chatbot. Extraction, OCR, canonical structure, deterministic rules, legal evidence and retrieval run locally. External model calls are explicit and receive bounded evidence packages rather than unrestricted raw-file access.

## Current production flow

New jobs use the Stage 13 `ISSUE_V1` architecture with the Stage 15 domain-aware legal retrieval layer:

```text
PDF / JPG / JPEG / PNG / DOCX
  -> reliable native PDF/DOCX text or local OCR where required
  -> cross-format Source Evidence
  -> evidence-grounded Canonical Contract
  -> deterministic audit rules
  -> Audit Planner + explicit canonical-object coverage
  -> deterministic Issue domain route
  -> READY Corpus Pack eligibility
  -> applicable Authority Version
  -> Exact Citation + FTS5/BM25 + optional local BGE
  -> deterministic retrieval fusion
  -> DeepSeek primary audit, one bounded call per AuditPlan Issue
  -> Kimi independent finding + coverage review, one bounded call per Issue
  -> deterministic Issue comparison
  -> issue-review-report.json
  -> append-only human review
  -> /results + /workspace
```

Source-format differences stop at the Evidence/Canonical boundary. Domain routing changes retrieval eligibility only; the Issue V1 Planner/RAG/DeepSeek/Kimi/comparison/Human Review topology does not branch on PDF/image/DOCX.

Law-Rag does not use a third model to vote on DeepSeek/Kimi disagreement. Unsupported, conflicting, stale, incomplete or insufficient-evidence states remain visible for human review.

## Status

**Stage 15 is complete. Stage 16 — expert benchmark + regression corpus + real-provider UAT — is next.**

Stage 15 delivered:

- extensible Corpus Pack architecture without changing canonical `Authority -> Version -> Article / Legal Evidence` identity;
- three READY official-law packs covering intellectual property, enterprise compliance and labor disputes;
- frozen `three-domain-core@1.0.0` baseline with **14 Authorities / 15 Versions / 1274 unique Articles**;
- official-source provenance, immutable snapshots, SHA-256 integrity and lifecycle-aware versions;
- independent Corpus Release versioning and deterministic corpus update planning;
- staged legal-store rebuild with atomic replacement and fail-closed mutation checks;
- deterministic Issue-domain routing into eligible READY Corpus Packs;
- Authority allowlists enforced before Exact, BM25/FTS5 and local semantic ranking;
- persisted routing provenance/fingerprint and explicit broad fallback behavior;
- Windows distribution of the immutable three-domain baseline with one-time writable runtime installation;
- preservation of an already-complete runtime corpus across application upgrades;
- non-mutating offline corpus diagnostics;
- final Windows onedir/portable-RC regression validation.

Authoritative final Stage 15 validation:

```text
Stage 15.4 domain-aware RAG
  Law-Rag Stage 15 CI #96 (32441338892)
  backend: 416 passed, 5 skipped, 1 warning
  public deterministic quality gates: PASS
  frontend production build: PASS

Stage 15.5 final branch head 355a003c67bdf4d9424e105d54e48779bca98c42
  Law-Rag Stage 15 CI #117 (32444333939)
  backend: 422 passed, 5 skipped, 1 warning
  public deterministic quality gates: PASS
  frontend production build: PASS

  Law-Rag Stage 15.5 Windows Baseline CI #6 (32444333963)
  exact Windows onedir build: PASS
  frozen baseline + runtime install verification: PASS
  packaged PDF/OCR/HTTP/privacy smoke: PASS
  deterministic portable RC + fresh extraction regression: PASS
```

Draft PR #13 and #14 remain stacked validation carriers and are intentionally unmerged unless separately authorized.

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

Local OCR and local legal retrieval are independent of cloud-provider permission.

## Legal corpus and retrieval

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

The installed baseline Corpus Release is:

```text
three-domain-core@1.0.0
3 READY Corpus Packs
14 Authorities
15 Versions
1274 unique Articles
```

Corpus Pack is a grouping/eligibility layer only. Shared Authority/Version text is not duplicated across packs. Corpus Release version, Pack version and Authority Version are independent identities.

Issue-level retrieval is:

```text
AuditPlan Issue
 -> deterministic legal-domain route
 -> eligible READY Corpus Packs
 -> eligible Authorities
 -> applicable Version for as_of
 -> Exact + FTS5/BM25 + optional local BGE
 -> deterministic weighted RRF fusion
```

When Issue signals cannot safely narrow legal scope, routing broadens explicitly rather than interpreting no match as no applicable law.

The current routing implementation and benchmark are documented in [`docs/STAGE15_DOMAIN_AWARE_RAG.md`](docs/STAGE15_DOMAIN_AWARE_RAG.md).

## Corpus updates

Legal text under an existing `(authority_id, version_id)` is immutable. A changed legal text requires a new Version identity.

Future corpus publication uses:

```text
official-source verification
 -> freeze new Authority Version where needed
 -> update lifecycle/supersession state
 -> bump affected Corpus Pack version
 -> build candidate Corpus Release
 -> deterministic update plan
 -> staged legal.db rebuild
 -> regression / quality gates
 -> publish immutable Corpus Release
```

The packaged application baseline is immutable. On first normal launch it is verified, staged and atomically copied into writable runtime storage. A complete existing runtime corpus is left untouched so later application upgrades cannot roll back an independently updated legal corpus.

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

For the pinned Windows PaddlePaddle 3.3.0 CPU path, `enable_mkldnn=False` remains a tested compatibility requirement after packaged regression exposed a oneDNN/PIR failure when that branch was enabled.

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

Model citations must resolve to supplied canonical Legal Evidence. Absence from the installed corpus is never proof that no applicable legal rule exists.

Human Review is append-only and fingerprint-bound. Only fresh final `CONFIRMED` or `REJECTED` decisions close a mandatory Issue review; stale or incomplete states remain visible.

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
13. **Legal corpus identity is immutable.** Changed legal text requires a new Authority Version.
14. **Corpus scope is auditable.** Domain routing narrows eligible Authorities without pretending unmapped scope means no law.

## Repository safety

This repository is public. Do not commit real/private contracts, API keys, runtime uploads, generated private reports, private benchmark labels, model caches/private vector stores, or logs containing private contract text.

See [`AGENTS.md`](AGENTS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`CURRENT_TASK.md`](CURRENT_TASK.md), and [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
