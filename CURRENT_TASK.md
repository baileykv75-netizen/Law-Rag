# CURRENT_TASK.md

# Stage 11D — Windows Dependency and Reproducible Release Bundle

## Status

```text
Stage 11A  COMPLETE — versioned benchmark schema + public synthetic evaluator
Stage 11B  COMPLETE — layered metrics + failure diagnostics + deterministic CI quality gates
Stage 11C  COMPLETE — runtime/startup/data-integrity hardening
Stage 11D  ACTIVE   — Windows dependency + reproducible release-bundle work
Stage 11E  PENDING  — release-candidate validation / installer decision
```

Stage 11C added non-mutating startup diagnostics, read-only SQLite integrity/staleness checks, Job artifact integrity inspection, atomic Stage 4/5 writes, interrupted-write residue detection, safer Windows setup/start behavior, and explicit recovery guidance. See `docs/RUNTIME_HARDENING.md`.

## Goal

Produce a **reproducible Windows-oriented release bundle** that can be tested on a clean machine before deciding whether Law-Rag should have an installer or monolithic executable.

The bundle should reduce setup friction without hiding the architecture or weakening local-data/evidence boundaries.

Priority:

```text
inventory dependencies/licences
  -> choose the smallest defensible packaging approach
  -> define bundle layout
  -> automate deterministic build
  -> validate on Windows
  -> document first-run/optional-model behavior
  -> only then consider installer in 11E
```

Do not use packaging as a reason to skip runtime diagnostics or benchmark gates.

## Hard boundaries

1. Do not embed or commit API keys, `.env`, private contracts, runtime databases, logs, private benchmarks, model caches, or user review data.
2. Do not silently download OCR/BGE weights during bundle creation.
3. DeepSeek/Kimi remain external opt-in providers; no provider credentials are baked into the bundle.
4. `legal.db` / `retrieval.db` treatment must be explicit: either reproducibly generated from checked-in public seed or deliberately included as generated public release assets with fingerprints documented.
5. OCR and semantic stacks remain optional unless a packaging experiment proves a reliable redistributable path.
6. Do not add a repository open-source license without the owner’s explicit decision.
7. Before redistributing binaries/dependencies, inspect current official packaging-tool documentation and relevant dependency/license obligations; do not rely on stale memory.
8. Do not create an installer in 11D.
9. Do not create a single opaque `.exe` merely because a bundler supports it. Prefer an inspectable folder bundle first.
10. Stage 1–10 regressions, Stage 11B public quality gates, and Stage 11C runtime diagnostics must remain green.

## 11D-1 — Packaging decision record

Before adding a packaging dependency, verify current primary documentation and record:

- candidate packaging approaches and current Windows/Python support;
- whether they support the FastAPI backend and required binary wheels cleanly;
- folder bundle vs one-file tradeoffs;
- startup-time/debuggability implications;
- license/redistribution implications;
- impact of optional PaddleOCR/PaddlePaddle and sentence-transformers/PyTorch stacks;
- how frontend static assets are produced and served/launched;
- whether external Node.js is still required in the release bundle.

Choose one minimal approach for the first release bundle. Document rejected alternatives briefly.

## 11D-2 — Release dependency inventory

Create a machine-readable or reviewable inventory for:

```text
base Python runtime dependencies
frontend production assets
PDF/PDFium binaries
legal seed/retrieval generated assets
optional OCR stack
optional semantic stack
external DeepSeek/Kimi configuration
```

For each release-relevant dependency record at least:

- package/component name;
- pinned/resolved version used by the bundle build;
- source/package manager;
- whether bundled or external/optional;
- license/redistribution note where relevant;
- runtime role.

Do not claim license compliance unless the actual notices/requirements have been checked.

## 11D-3 — Reproducible base bundle

Build the smallest useful Windows bundle first, targeting the base/native-PDF + deterministic/legal/retrieval/workstation path.

Preferred first milestone:

```text
Law-Rag/
  app / launcher
  backend runtime
  frontend production assets
  public legal/retrieval assets or deterministic rebuild path
  config template
  diagnostics command
  THIRD_PARTY_NOTICES / dependency inventory as required
  README / first-run guide
  runtime/   (created locally at first use; empty/not shipped with private data)
```

The exact layout depends on the verified packaging approach.

The bundle must not contain:

```text
API keys
.env with real values
private uploads/jobs
private benchmark data
logs
model caches
hidden reasoning
user-specific human-review data
```

## 11D-4 — Frontend/runtime launch

Remove unnecessary development-only startup requirements from the release path.

In particular, determine whether the production frontend can be served as built static assets by the local application/runtime so end users do not need a separate Node/Vite dev server.

Development scripts may remain for contributors, but the release bundle should have one clear launch path and one diagnostics path.

## 11D-5 — Optional OCR / semantic policy

Do not force the largest optional ML stacks into the first bundle without evidence.

Document one of these explicit policies for each optional stack:

```text
bundled and verified
external optional install
first-use local download after explicit user action
deferred from first release
```

The base app must continue to explain the supported fallback when OCR or semantic retrieval is absent.

## 11D-6 — Windows validation

Add a reproducible Windows CI/smoke path that validates the selected base bundle on a clean runner as far as practical without external paid providers.

At minimum validate:

- bundle/build command completes;
- expected files exist;
- no banned private/secret paths are present;
- runtime diagnostics execute;
- backend starts or imports from the bundled environment;
- native PDF path has required binaries;
- public legal/retrieval path can be built/read;
- frontend production surface is present/reachable by the selected launch design;
- no DeepSeek/Kimi key is required for base startup;
- Stage 11B quality gate remains independent and green.

Do not run paid model calls in ordinary bundle CI.

## 11D-7 — Reproducibility metadata

Generate release-build metadata containing safe values such as:

- application/release version;
- source commit SHA;
- Python version;
- frontend build version/toolchain;
- selected packaging-tool version;
- legal seed manifest/source fingerprint;
- retrieval schema/index version;
- dependency inventory fingerprint;
- build timestamp if needed, while keeping reproducible-content semantics explicit.

Never include secrets or private paths in release metadata.

## Validation before 11D completion

1. packaging approach is chosen from current official information rather than assumption;
2. dependency/license inventory exists and distinguishes bundled vs optional/external components;
3. reproducible base Windows bundle is generated by a committed build path;
4. no secrets/private runtime artifacts are present in the bundle;
5. production frontend no longer requires a Vite development server in the release path, unless a documented blocker is accepted;
6. diagnostics work from the release layout;
7. native PDF/base local workflow is validated on Windows;
8. legal/retrieval public assets have a deterministic release strategy;
9. optional OCR/semantic policy is explicit;
10. provider keys remain user-supplied at runtime;
11. Windows bundle smoke is green;
12. backend regressions, Stage 11B quality gates, and frontend production build remain green;
13. release instructions reflect the actual bundle rather than development setup.

## Out of scope

Do not implement in 11D:

- MSI/Inno/NSIS installer;
- automatic system-wide registration;
- auto-updater;
- code-signing purchase/setup;
- single-file executable as a goal in itself;
- bundled real API keys;
- cloud deployment/authentication;
- new LLM/OCR/embedding model families;
- legal-corpus expansion/crawling;
- destructive migration of existing user runtime data.

Stage 11E may begin only after a clean Windows release-bundle smoke succeeds and the release contents/licensing boundaries are understood.
