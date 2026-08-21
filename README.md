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

**Stage 16.1–16.3 are COMPLETE. Stage 16.4 — real-provider ISSUE_V1 UAT observation capture — is NEXT.**

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

Authoritative Stage 15 closeout validation:

```text
Law-Rag Stage 15 CI #123 (32456205510)                  SUCCESS
Law-Rag Stage 15.5 Windows Baseline CI #9 (32456205586) SUCCESS
```

Stage 16 keeps evaluation evidence classes explicit:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

Stage 16.1 added a versioned deterministic evaluation-suite architecture with public/private/UAT isolation, sanitized reports and input fingerprints. Final Stage 16.1 closeout validation:

```text
head 706ce85bc5b472896d33dcf4d926501755656247
Law-Rag Stage 16 CI #15 (32458037391)  SUCCESS
Law-Rag Stage 15 CI #130 (32458037327) SUCCESS
```

Stage 16.2 promoted the existing nine-case Stage 15 three-domain retrieval fixture into an explicit versioned public regression dataset and added a separate deterministic regression profile without changing the historical Stage 11B quality profile.

It validates:

- broad/scoped lexical Recall@5 and MRR;
- Authority routing/scope invariants;
- `UNMAPPED` broad fallback;
- cross-domain Pack union;
- frozen `three-domain-core@1.0.0` article count;
- trademark `as_of` version boundary;
- semantic identity of the promoted Stage 15 benchmark truth;
- selected Corpus Release identity and READY routing-catalog compatibility.

Final Stage 16.2 validation:

```text
head 67407e54b27e595e82119b055774241ce708b971
Law-Rag Stage 16 CI #50 (32459347103) SUCCESS
backend pytest                             434 passed, 5 skipped, 1 warning
historical Stage 11B public gates          PASS
Stage 16.2 public regression               10 / 10 gates PASS
expanded Stage 16b suite                   3 / 3 entries PASS
frontend production build                 PASS
```

Named nine-case public regression values:

```text
scoped Recall@5 / MRR       1.00 / 1.00
broad Recall@5 / MRR        1.00 / 1.00
scoped-broad deltas         0.00 / 0.00
Authority compliance       1.00
route eligibility          1.00
UNMAPPED fallback           1.00
CROSS_DOMAIN union          1.00
trademark version boundary 1.00
Article count               1274
```

Those numbers are **scoped deterministic regression evidence for the named public dataset**, not a claim of 100% legal correctness or professional audit accuracy.

Stage 16.3 adds the private expert benchmark protocol/evaluator needed to measure professional labels safely:

```text
ExpertBenchmarkProtocol
  + private BenchmarkDataset
  + private BenchmarkObservationSet
  + ExpertLabelAuditArtifact
  -> sanitized ExpertBenchmarkRunReport
```

Private inputs must remain external or under ignored `benchmark_private/`; every case uses `PRIVATE_EXTERNAL` provenance. Expert labels have explicit `AGREED`, `ADJUDICATED` or `AMBIGUOUS` states. Each audit record is SHA-256 bound to the case's current expected truth so later label mutation invalidates the old expert audit.

The initial professional metrics are scoped binary classification and exhaustive set extraction precision/recall/F1. `AMBIGUOUS` cases stay visible in label-quality counts/rates and are excluded from performance scoring rather than silently relabeled. The report also exposes agreement/adjudication/ambiguity/usable rates, because system metrics are not interpreted independently of expert-truth quality.

Validated Stage 16.3 implementation:

```text
head 3393caa150e2baee459ca0969e8f17ee451d6156
Law-Rag Stage 16 CI #62 (32460155009) SUCCESS
backend pytest                             443 passed, 5 skipped, 1 warning
historical Stage 11B public gates          PASS
Stage 16.2 public regression               PASS
Stage 16b public suite                     PASS
frontend production build                 PASS
```

**No real professionally labeled dataset has been committed or executed.** Therefore Stage 16.3 completion means the private expert protocol/evaluator infrastructure is validated; Law-Rag does not yet have a measured professional audit accuracy, high-risk recall, citation-relevance score or release threshold.

Stage 16.4 will capture explicit DeepSeek/Kimi `ISSUE_V1` UAT observations under the existing provider-approval/cancellation boundary, with provider/model/artifact fingerprints and private storage. Real-provider UAT remains separate from expert truth and ordinary public CI.

See [`docs/STAGE16_EVALUATION.md`](docs/STAGE16_EVALUATION.md), [`docs/STAGE16_EXPERT_BENCHMARK.md`](docs/STAGE16_EXPERT_BENCHMARK.md) and [`CURRENT_TASK.md`](CURRENT_TASK.md).

Draft PR #13/#14/#15/#16/#17 remain stacked validation carriers and are intentionally unmerged unless separately authorized.

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

## Evaluation

Stage 16 evaluation remains split by evidence class:

```text
PUBLIC_REGRESSION
  EvaluationSuiteManifest / public deterministic regression profiles

PRIVATE_EXPERT
  private BenchmarkDataset + ObservationSet + ExpertLabelAuditArtifact
  -> ExpertBenchmarkRunReport

REAL_PROVIDER_UAT
  explicit provider/model observations; Stage 16.4
```

Public deterministic regression from `backend/`:

```text
python -m app.public_regression_cli \
  --repo-root .. \
  --profile ../benchmarks/public/stage16b_three_domain_regression.json
```

Expanded public suite:

```text
python -m app.evaluation_suite_cli \
  --repo-root .. \
  --suite ../benchmarks/public/stage16b_evaluation_suite.json
```

Private expert evaluator:

```text
python -m app.expert_benchmark_cli \
  --repo-root .. \
  --protocol <external-or-benchmark_private/protocol.json>
```

The historical `stage16a_evaluation_suite.json` remains unchanged for Stage 16.1 auditability. No evaluation command implicitly executes paid/network DeepSeek or Kimi.

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
15. **Evaluation evidence classes stay separate.** Public regression, private expert truth, and real-provider UAT are not collapsed into one fake score.
16. **Benchmark identity is versioned.** Public regression truth, Corpus Release identity and routing catalog must remain reproducibly attributable.
17. **Expert truth is audited.** Professional labels are reviewer-counted, ambiguity-aware and fingerprint-bound before metrics are interpreted.

## Repository safety

This repository is public. Do not commit real/private contracts, API keys, runtime uploads, generated private reports, private benchmark labels, model caches/private vector stores, or logs containing private contract text.

See [`AGENTS.md`](AGENTS.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`CURRENT_TASK.md`](CURRENT_TASK.md), [`docs/STAGE16_EVALUATION.md`](docs/STAGE16_EVALUATION.md), [`docs/STAGE16_EXPERT_BENCHMARK.md`](docs/STAGE16_EXPERT_BENCHMARK.md), and [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
