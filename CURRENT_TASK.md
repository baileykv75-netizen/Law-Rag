# CURRENT_TASK.md

# Stage 11 — Benchmark, Hardening, and Windows Release

## Goal

Turn the Stage 1–10 feature-complete local contract-audit pipeline into something that can be measured, stress-tested, reproduced, and distributed on Windows without weakening the evidence/privacy boundaries already established.

Stage 11 is **not** a new reasoning/model stage. The priority order is:

```text
measure first
  -> identify real failure modes
  -> harden runtime/data integrity
  -> validate Windows setup/bundle behavior
  -> produce a reproducible release bundle
  -> consider installer only after the bundle is proven
```

Do not use packaging as a substitute for quality validation.

## Hard boundaries inherited from Stages 1–10

1. No private contracts, private expert labels, private benchmark data, API keys, runtime databases, model caches or private logs may be committed to the public repository.
2. Public CI must remain deterministic and must not require paid DeepSeek/Kimi calls.
3. Real-provider smokes remain explicit opt-in tests using synthetic/public content only.
4. Benchmark scores must name the dataset/scope/version; never present a tiny public fixture score as a general legal-accuracy claim.
5. `CURATED_EXCERPT` legal coverage remains explicit; missing corpus content cannot be counted as proof of legal absence.
6. OCR, canonical extraction, deterministic rules, legal retrieval, DeepSeek, Kimi, comparison, Agent and human-review artifacts remain independently inspectable.
7. Release packaging must not embed secrets or private runtime artifacts.
8. Model/OCR weights and caches must stay outside Git and have a documented first-run/offline policy.
9. Existing dependency licenses and binary redistribution obligations must be rechecked before shipping a Windows bundle.
10. Do not add a repository open-source license without the project owner's explicit decision.
11. No automatic final legal approval is introduced in Stage 11.
12. All Stage 1–10 regressions must remain green throughout hardening.

## Delivery strategy

Implement Stage 11 in small verifiable sub-phases:

```text
11A — benchmark schema + public synthetic evaluation harness
11B — quality/failure diagnostics + regression gates
11C — runtime/startup/data-integrity hardening
11D — Windows dependency/bundle reproducibility
11E — release candidate checklist + optional installer decision
```

Do not implement all sub-phases in one uncontrolled rewrite.

## 11A — Benchmark schema

Create a versioned benchmark/evaluation schema that can represent multiple layers without conflating them.

At minimum support separately scored tasks for:

```text
OCR
canonical structure extraction
deterministic rule behavior
legal retrieval
legal citation validity
contract Evidence localization
primary audit findings
secondary disagreement/omission detection
human-review workflow integrity
```

A benchmark case should record enough metadata to reproduce the expected comparison, such as:

- case ID/version;
- fixture/document ID;
- task type;
- expected page/Evidence/Legal Evidence IDs where applicable;
- expected structured values/labels;
- allowed alternatives/tolerances where genuinely necessary;
- dataset scope/source/provenance;
- whether the case is public synthetic/public legal/private external evaluation;
- evaluator version.

Do not create one vague aggregate “legal accuracy” number.

## 11A — Public vs private evaluation data

Repository-safe public benchmark data may contain only:

- fictional/synthetic contracts;
- verified public legal text/provenance already permitted by the legal-data policy;
- synthetic OCR/page-layout fixtures;
- non-sensitive expected labels.

Private real-contract benchmarks and expert labels must remain outside Git. If a private benchmark runner is supported, it should accept an external local path/config without assuming the data is checked in.

## 11B — Metrics

Report metrics by layer.

Candidate metrics include:

### OCR

- character error rate / normalized text accuracy where reference text exists;
- block detection/coverage;
- low-confidence/failure rate;
- page-level success rate.

### Canonical structure

- clause boundary precision/recall;
- party/date/money/percentage/identifier extraction precision/recall;
- source-span/Evidence linkage accuracy;
- cross-page continuation accuracy.

### Retrieval

Preserve existing retrieval metrics and extend only when justified:

```text
Recall@K
MRR
exact citation hit rate
version/applicability correctness
coverage-state correctness
```

### Audit findings

For a labeled benchmark, report separately:

```text
precision
recall
F1
high-risk recall
false-positive count/category
unsupported-citation rate
Evidence-link validity
Legal Evidence/version validity
review-required calibration by category
```

Do not convert model agreement into a correctness probability.

### Dual-model/Agent

Track at least:

- agreement/minor/material disagreement distribution;
- possible-omission yield on labeled cases;
- Agent follow-up activation rate;
- Agent action count/tool distribution;
- unresolved `HUMAN_REVIEW_REQUIRED` rate;
- invalid/forbidden action rate (expected zero).

## 11B — Regression gates

Only introduce a CI quality gate when:

1. the benchmark is deterministic enough for CI;
2. its dataset is public/repository-safe;
3. the metric meaning is documented;
4. the threshold is justified by the current fixture scope.

Keep opt-in heavy/real-provider benchmarks separate from normal CI.

A regression gate must fail loudly on degraded results; do not silently update expected labels/thresholds just to restore green CI.

## 11B — Failure diagnostics

Benchmark output should help locate failures rather than emit only a score.

For every failed case, retain safe diagnostics such as:

- case/task ID;
- expected vs observed structured result;
- page/Evidence IDs;
- Legal Evidence/version IDs;
- provider/model/version when relevant;
- deterministic stage responsible when known;
- explicit reason/category.

Do not persist hidden model reasoning or secrets.

## 11C — Runtime hardening

Audit the local runtime for real release blockers, including:

- startup when Python/Node/runtime dependency is missing;
- model/OCR dependency unavailable;
- corrupted/incomplete runtime artifact;
- stale retrieval/legal index;
- source file missing/duplicated;
- interrupted/partial writes;
- port conflicts;
- malformed local configuration;
- very long/Chinese Windows paths where practical;
- repeated start/stop behavior;
- clear offline/first-run behavior for OCR/embedding models;
- disk-space/cache location visibility;
- no secrets in logs/errors.

Prefer explicit diagnostics over automatic destructive repair.

## 11C — Data integrity/recovery

Review atomic-write behavior for critical artifacts and add recovery/diagnostic behavior where needed.

At minimum protect:

```text
contract.json
audit-rules.json
ai-audit.json
secondary-review.json
review-report.json
human-review.json
legal.db
retrieval.db
```

Do not overwrite a previously valid artifact with a failed/incomplete stage result.

## 11D — Windows dependency audit

Before bundling, re-verify current official license/redistribution information for shipped dependencies and binary components, especially:

- Python/runtime choice;
- pypdf;
- pypdfium2/PDFium;
- Pillow;
- PaddlePaddle/PaddleOCR and model redistribution assumptions;
- SQLite/FTS behavior;
- Node/Vite frontend build output;
- any semantic embedding runtime/models that are bundled or downloaded separately.

Record shipping implications in `docs/DECISIONS.md` or a dedicated release/dependency document.

Do not bundle a component whose redistribution requirements are unclear.

## 11D — Release bundle target

First target a reproducible Windows-oriented folder/bundle rather than an installer.

A candidate release should provide a documented path similar to:

```text
Law-Rag/
  start-law-rag.bat
  backend/runtime or embedded Python strategy
  frontend built assets
  configuration template
  legal seed/build assets or verified local database bootstrap
  license notices required by redistributed dependencies
  README / first-run diagnostics
```

Exact packaging technology must be chosen only after testing size, startup reliability, subprocess behavior, model-cache strategy and license implications.

## 11D — Release privacy checks

A release artifact must be inspected to ensure it contains no:

- API key;
- `.env` secret;
- real/private contract;
- local `runtime/jobs` output;
- private benchmark;
- private log;
- user-specific absolute path;
- unintended model/cache copy.

## 11E — Release candidate validation

Before calling anything a release candidate, verify at least:

- clean-machine/clean-directory setup path is documented;
- startup diagnostics are understandable;
- core local workflow can open the professional workstation;
- optional OCR path is documented/tested;
- legal seed/retrieval bootstrap is reproducible;
- external model configuration is explicit and secret-safe;
- no external model call happens just by startup/workspace navigation;
- benchmark report can be reproduced from the named public fixture version;
- Stage 1–10 regressions remain green;
- frontend production build remains green;
- Windows-specific smoke is green;
- release contents pass privacy/secret scan;
- required third-party notices are included.

Only after a release bundle is reliable should an installer format be evaluated.

## Test strategy

Normal CI remains local and secret-free.

Expected Stage 11 test layers:

```text
fast deterministic unit/regression suite
public synthetic benchmark gate(s)
frontend TypeScript/production build
opt-in Windows OCR dependency smoke
opt-in/local semantic retrieval smoke
opt-in paid DeepSeek/Kimi synthetic smoke
Windows release-bundle smoke when implemented
```

Do not make normal CI depend on downloaded private models, private benchmarks or paid API availability.

## Out of scope

Do not add in Stage 11 unless a concrete release blocker requires it:

- new reasoning models;
- third-model voting;
- public SaaS/auth/multi-tenancy;
- cloud document storage;
- automatic legal-corpus crawling;
- fine-tuning on private contracts;
- auto-filing/submission;
- automatic final legal approval;
- mobile app;
- an installer before the release bundle itself is proven.

## Acceptance criteria

Stage 11 is complete only when all are true:

1. A versioned evaluation schema/harness exists.
2. Repository-safe public synthetic benchmark cases cover multiple pipeline layers.
3. Metrics are reported by layer rather than as one unsupported legal-accuracy number.
4. Benchmark failures provide case-level diagnostics.
5. Existing Stage 7 retrieval benchmark remains intact or is deliberately versioned with documented rationale.
6. At least one meaningful deterministic quality regression gate is enforced in CI beyond existing unit tests.
7. Runtime startup/dependency/configuration failure states have explicit diagnostics.
8. Critical artifact write/recovery behavior is hardened or explicitly documented.
9. Windows dependency/license redistribution review is documented from current primary sources before bundling.
10. A reproducible Windows-oriented release bundle path exists.
11. Release bundle contains no secrets/private runtime/private benchmark data.
12. First-run/offline/model-cache behavior is documented.
13. A Windows release smoke validates startup and core local UI/workstation access.
14. No hidden model call occurs on startup/workspace navigation.
15. Stage 1–10 backend regressions remain green.
16. Frontend TypeScript/production build remains green.
17. README/architecture/release docs reflect the shipped behavior.
18. Final CI/release checks are green.

## Completion rule

Do not claim a production-quality legal accuracy level or Windows release until the named benchmark scope and release checks actually support that claim.

Begin with **11A — benchmark schema + public synthetic evaluation harness**. Do not start installer work first.
