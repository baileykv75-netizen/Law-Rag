# CURRENT_TASK.md

# Stage 13 — Audit Architecture Refactor

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel control validated
Stage 13B       COMPLETE — Audit Planner foundation validated
Stage 13C       COMPLETE — hierarchical long-contract planning + explicit coverage validated
Stage 13D       NEXT — issue-based Legal RAG
Stage 13E       PENDING — DeepSeek issue-by-issue primary audit
Stage 13F       PENDING — Kimi finding + coverage review
Stage 13G       PENDING — end-to-end audit architecture regression
```

Stage 13 was reordered after reviewing the old Stage 8/9 architecture. The priority is to make review scope complete and auditable before returning to desktop tray/history work.

## Stage 13A — Provider boundary + pause/cancel

**Complete and retained.**

Audit Planner is now the first external model stage in the new architecture. Every Planner/DeepSeek/Kimi request must respect persisted provider policy, cancellation semantics and the atomic outbound boundary documented in [`docs/PROVIDER_BOUNDARY.md`](docs/PROVIDER_BOUNDARY.md).

## Stage 13B — Audit Planner foundation

**Complete and validated.**

A versioned `audit-plan.json` is generated from three independent sources:

```text
Baseline checklist
+ deterministic Stage 5 / legacy-topic hints
+ LLM dynamic planning
= validated AuditPlan
```

Implemented guarantees:

- conservative contract-type enum includes `UNKNOWN` and `MIXED`;
- GENERAL baseline cannot be removed by weak model output;
- type-specific checklist additions are deterministic;
- Planner receives canonical clause/block text plus structured global facts;
- Planner may cite only supplied canonical object IDs;
- Evidence IDs are derived by Law-Rag, never invented by the model;
- dynamic issues require review questions and later Legal-RAG queries;
- duplicate topic merging is conservative/deterministic;
- fake Planner is test-only and default-deny;
- Planner calls cross the Stage 13A provider boundary.

See [`docs/AUDIT_PLANNER.md`](docs/AUDIT_PLANNER.md).

## Stage 13C — Hierarchical planning for long contracts

**Complete and independently validated.**

The former 60,000-character direct-planning dead end is replaced by automatic routing:

```text
short/medium canonical contract
 -> DIRECT Planner

large canonical contract
 -> contiguous bounded CHUNK Planner passes over complete canonical objects
 -> immediate per-chunk validation
 -> bounded GLOBAL synthesis over complete object index + validated local-topic summaries
 -> deterministic final merge
 -> AuditPlan
```

### No silent truncation

Every canonical clause/block is supplied **in full** to exactly one primary local Planner pass. Canonical objects are never character-split merely to fit a model request.

If a single canonical object itself exceeds the maximum bounded Planner request size, Law-Rag fails closed and does not claim that object was reviewed.

The GLOBAL pass receives compact `*_INDEX_SUMMARY` previews only after all original canonical objects have already been reviewed in full by local passes. The prompt explicitly states that the compact index is a synthesis/navigation view, not a substitute for source text.

### Current application bounds

```text
direct Planner budget             60,000 canonical text/fact chars
hierarchical chunk target         18,000 canonical text chars
max canonical objects / chunk     24
max hierarchical provider passes  256 including GLOBAL
```

These are resource/safety controls, not claims about provider context-window size.

### Final-plan capacity

The strict `ModelAuditPlanDraft` still caps each individual model response at 120 issues.

Multi-chunk planning does **not** combine all local drafts back into one constrained model-draft object. Validated local `LLM_DYNAMIC` issues are merged directly into the final AuditPlan after global synthesis, so a multi-pass plan is not incorrectly limited to one response's 120-issue cap.

### Global synthesis

The GLOBAL pass receives:

- all canonical object IDs in stable order;
- compact deterministic object previews;
- available global structured facts;
- Stage 5 / legacy deterministic hints;
- deterministic topic-level summaries of validated local Planner outputs.

Full local questions/retrieval queries remain preserved separately for final merge. They are not silently deleted to fit the global request.

If even this bounded synthesis representation exceeds the direct Planner budget, Law-Rag fails closed and reports that a deeper reduction layer is required rather than silently dropping objects/issues.

### Explicit planning coverage

`audit-plan.json` schema 1.1 now records:

```text
planning_mode = DIRECT | HIERARCHICAL
planner_passes[]
coverage[]
coverage_complete
```

Every canonical clause/block receives one coverage record:

```text
REVIEWED_WITH_ISSUE
REVIEWED_NO_SPECIFIC_ISSUE
```

`REVIEWED_NO_SPECIFIC_ISSUE` means only that the complete canonical object was supplied to a valid Planner pass but no final planning issue references it. It is **not** a legal conclusion that the clause is safe/lawful/valid.

A partial plan is not persisted when canonical-object coverage is incomplete.

### Provider/cancel semantics

Every CHUNK and GLOBAL provider request independently crosses the Stage 13A atomic boundary.

Cancellation after one completed chunk prevents the next chunk/global request from starting. An already-started request remains subject to the documented non-recall limitation.

### Validation completed

Provider-free regressions cover:

- >60k canonical contracts automatically selecting HIERARCHICAL mode;
- multiple bounded chunk passes plus one global pass;
- exact full-text equality between every source canonical object and its local Planner input;
- every canonical object appearing in planning coverage;
- short contracts receiving equivalent DIRECT coverage metadata;
- invented local canonical IDs failing before global synthesis and before persistence;
- cancellation after the first chunk blocking every later provider pass;
- one over-limit canonical object never being split/truncated;
- GLOBAL synthesis receiving every canonical ID and validated local-topic summaries;
- final local dynamic issue merging outside the single-response issue cap;
- existing backend regressions and public quality gates remaining green.

CI run #457 passed the initial Stage 13C hierarchy/coverage regression set. CI run #459 passed the hardened automatic DIRECT/HIERARCHICAL API path together with backend tests, public deterministic quality gates and frontend production build.

See [`docs/HIERARCHICAL_AUDIT_PLANNING.md`](docs/HIERARCHICAL_AUDIT_PLANNING.md).

## Stage 13D — Issue-based Legal RAG

**Status: next; not started in Stage 13C.**

Goal:

```text
validated AuditPlan issue
 -> one or more validated retrieval queries
 -> version-aware local Legal RAG
 -> issue-specific Legal Evidence package
```

Requirements for 13D:

- every planned issue gets an explicit retrieval outcome;
- retrieval is driven by the AuditPlan, not capped by the old eight hard-coded topics;
- baseline/deterministic/dynamic issue provenance is retained;
- applicable-law date/version resolution stays deterministic;
- Legal Evidence IDs must come only from the local versioned legal store;
- zero/partial corpus coverage is explicit and cannot be converted into a confident legal conclusion;
- duplicate retrieval queries should be cached/reused deterministically where safe;
- the old Stage 8 topic router remains only a compatibility/hint source during migration;
- no DeepSeek issue-by-issue legal conclusion yet; that belongs to 13E.

## Stage 13E — DeepSeek issue-by-issue primary audit

Pending. Every planned issue must receive an explicit terminal audit state such as supported finding, no material risk found, insufficient evidence, or review required.

## Stage 13F — Kimi finding + coverage review

Pending. Kimi must review both primary findings and coverage of the complete AuditPlan.

## Stage 13G — End-to-end audit architecture regression

Pending. Validate Planner coverage, issue-based retrieval, primary audit, secondary coverage review, provider boundary, cancellation/restart semantics and packaged Windows behavior before retiring the legacy Stage 8/9 path.

## Deferred roadmap after Stage 13G

```text
Stage 14  OCR distribution + DOCX
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF reports + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 13C is closed.**

The next explicit implementation task is **Stage 13D issue-based Legal RAG**. Do not start Stage 13E or later work in the same iteration.
