# CURRENT_TASK.md

# Stage 11C — Runtime, Startup, and Data-Integrity Hardening

## Status

```text
Stage 11A  COMPLETE — versioned benchmark schema + public synthetic evaluator
Stage 11B  COMPLETE — layered metric helpers + failure diagnostics + deterministic CI quality gates
Stage 11C  ACTIVE   — runtime/startup/data-integrity hardening
Stage 11D  PENDING  — Windows dependency and release-bundle reproducibility
Stage 11E  PENDING  — release-candidate validation / installer decision
```

Stage 11B public CI now independently rebuilds the checked-in legal seed/retrieval index and enforces the named repository-safe quality profile. Its scores remain scoped regression evidence, not a general legal-accuracy claim.

## Goal

Make the existing Stage 1–10 local application fail safely and diagnostically under realistic local-runtime problems before attempting a Windows release bundle.

This phase is **not** a new reasoning/model feature and is **not** packaging work.

Priority:

```text
detect runtime problem
  -> preserve prior valid data
  -> return explicit diagnostic
  -> avoid destructive auto-repair
  -> provide a clear operator action
```

## Hard boundaries

1. Do not weaken evidence, legal-version, privacy, provider, Agent, or human-review boundaries from Stages 1–10.
2. Startup/workspace navigation must not call DeepSeek or Kimi.
3. No private contracts, benchmark labels, runtime databases, model caches, logs, or secrets may enter Git.
4. Never print API keys or full secret values in diagnostics.
5. Do not silently delete/rebuild a user's runtime directory to recover from corruption.
6. Do not overwrite a previously valid artifact with a failed/incomplete new result.
7. `legal.db` and `retrieval.db` remain local generated stores; recovery must be explicit.
8. OCR/semantic model downloads remain optional and outside Git.
9. No installer, embedded Python, or executable bundle work in 11C.
10. Existing backend tests, frontend build, and Stage 11B public quality gates must remain green.

## 11C-1 — Runtime health model

Create a typed, local runtime-diagnostics model and service that can inspect without mutating:

```text
Python/runtime basics
configured runtime directory
job storage writability
legal.db presence/readability
retrieval.db presence/readiness/staleness
OCR optional dependency readiness
semantic retrieval optional dependency readiness
DeepSeek/Kimi configuration presence (never secret values)
frontend/backend expected local ports or startup prerequisites where safely testable
```

Diagnostic states should be explicit, for example:

```text
OK
OPTIONAL_NOT_CONFIGURED
MISSING
STALE
CORRUPT
MISCONFIGURED
UNAVAILABLE
ACTION_REQUIRED
```

Do not label an optional component failure as fatal when the supported fallback path remains valid.

## 11C-2 — Startup diagnostics

Add a developer/user-facing local diagnostic command or endpoint that answers:

```text
Can base Law-Rag start?
Can native PDF processing run?
Is OCR installed/configured?
Is legal seed built?
Is lexical retrieval ready?
Is semantic retrieval available?
Are DeepSeek/Kimi keys configured?
What exact safe action should the user take next?
```

Examples of safe remediation messages:

```text
Run rebuild-legal-seed.bat
Run build-retrieval-index.bat
Run setup-ocr-cpu.bat only if scanned documents require OCR
Set DEEPSEEK_API_KEY locally before primary audit
Set MOONSHOT_API_KEY locally before secondary review
```

The diagnostic path itself must not download models, rebuild databases, call providers, or mutate job artifacts.

## 11C-3 — Critical artifact integrity

Audit and harden critical persisted artifacts:

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

For JSON artifacts, where practical verify:

- parseability;
- schema validation;
- expected job identity;
- required fingerprint/link relationships;
- atomic write behavior;
- previous-valid-result preservation on failed write/update.

For SQLite stores verify read/open/integrity behavior without destructive repair.

Corruption must be surfaced as `CORRUPT`/`ACTION_REQUIRED`, not converted into an empty successful state.

## 11C-4 — Runtime failure cases

Add deterministic regressions for representative failures, including as many as practical without platform-specific guessing:

- missing runtime directory parent / first-run creation boundary;
- unwritable configured runtime directory where safely testable;
- corrupt JSON artifact;
- corrupt `legal.db`;
- corrupt/stale `retrieval.db`;
- source file missing for an existing job;
- malformed environment/config value;
- missing optional OCR dependency;
- missing optional semantic dependency;
- no DeepSeek/Kimi key configured;
- stale human-review decision after report change;
- interrupted-write simulation or temp-file residue where applicable.

Tests must verify that a previous valid artifact is not destroyed by the failure path.

## 11C-5 — Windows-oriented startup behavior

Review the current `.bat` scripts for clear failure behavior before Stage 11D bundling:

```text
setup-dev.bat
start-dev.bat
setup-ocr-cpu.bat
setup-rag-semantic-cpu.bat
rebuild-legal-seed.bat
build-retrieval-index.bat
build-retrieval-index-semantic.bat
```

In 11C, improve diagnostics only where needed. Do not choose a packaging technology yet.

Pay particular attention to:

- missing Python/Node;
- virtualenv missing;
- command failure propagation;
- Chinese/space-containing paths;
- repeated start attempts;
- clear local URLs;
- no secret echoing.

## 11C-6 — Logging/error hygiene

Ensure new diagnostics and existing startup/runtime errors prefer IDs/states over raw private contract text.

Never include:

- full API keys;
- Authorization headers;
- unrestricted contract contents;
- hidden model reasoning;
- private benchmark contents.

## Validation

Before marking 11C complete:

1. runtime diagnostic inspection is provider-free and mutation-free;
2. optional OCR/semantic absence is distinguished from fatal base-runtime failure;
3. corrupt/missing legal/retrieval stores receive explicit diagnostics;
4. critical JSON corruption is not rendered as success;
5. previous valid artifacts survive failed stage writes/updates;
6. representative runtime failure regressions are green;
7. Windows developer scripts have explicit failure propagation/next-action messages where practical;
8. no secrets/private payloads appear in diagnostic output;
9. Stage 1–10 backend regressions remain green;
10. Stage 11B public deterministic quality gates remain green;
11. frontend TypeScript/production build remains green;
12. documentation reflects actual diagnostics and recovery boundaries.

## Out of scope

Do not implement in 11C:

- Windows installer;
- monolithic `.exe`;
- embedded Python distribution;
- dependency redistribution/license bundle;
- new OCR/model family;
- new LLM provider;
- third-model voting;
- automatic legal-corpus crawling;
- destructive automatic runtime repair;
- cloud deployment/authentication.

Stage 11D may begin only after 11C runtime/data-integrity diagnostics are demonstrably green.
