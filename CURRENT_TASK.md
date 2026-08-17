# CURRENT_TASK.md

# Stage 13 — Audit Architecture Refactor

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel control validated
Stage 13B       ACTIVE — Audit Planner foundation
Stage 13C       PENDING — hierarchical planning for long contracts
Stage 13D       PENDING — issue-based Legal RAG
Stage 13E       PENDING — DeepSeek issue-by-issue primary audit
Stage 13F       PENDING — Kimi finding + coverage review
Stage 13G       PENDING — end-to-end audit architecture regression
```

The Stage 13 roadmap was deliberately reordered after reviewing the existing Stage 8/9 architecture. Desktop tray/history work is deferred: the more important problem is that the current hard-coded Stage 8 topic router can narrow what the models are allowed to review.

## Stage 13A — Provider boundary + pause/cancel

**Status: complete and retained.**

The persisted provider/cancel control plane remains a hard security boundary. With the new architecture, Audit Planner becomes the first external model call. Therefore the provider boundary must eventually sit **before Planner transmission**, not merely before the current DeepSeek primary-audit call.

No future Planner/DeepSeek/Kimi implementation may bypass `pipeline-control.json`, cancellation semantics, or the atomic outbound-provider boundary.

See [`docs/PROVIDER_BOUNDARY.md`](docs/PROVIDER_BOUNDARY.md).

## Stage 13B — Audit Planner foundation

**Status: active. Implement this stage only.**

### Problem being fixed

Current Stage 8 uses a small hard-coded topic list to decide which clauses trigger legal retrieval and which contract objects enter the bounded primary-audit context. This is safe and explainable but can suppress issues the programmer did not predefine.

The new rule is:

> Contract structure describes facts; deterministic rules emit certain mechanical anomalies; neither layer may define the complete legal-review scope.

### Goal

Create a formal, evidence-bounded `AuditPlan` layer built from three sources:

```text
Baseline checklist
+ deterministic rule/topic hints
+ LLM dynamic planning
= validated AuditPlan
```

The Planner decides **what should be investigated**, not whether a clause is lawful/unlawful and not the final legal conclusion.

### Stage 13B deliverables

1. Versioned `AuditPlan` / planner-draft Pydantic schemas.
2. Explicit contract-type enum with `UNKNOWN` and `MIXED`; no forced guess.
3. Deterministic baseline checklist registry by contract type, with a conservative GENERAL fallback.
4. Deterministic hints derived from Stage 5 non-PASS results and the existing Stage 8 keyword topics.
5. Bounded Planner input containing canonical clause IDs/text, source Evidence IDs and deterministic hints.
6. DeepSeek Planner provider prompt that returns strict JSON and is forbidden to make final legal conclusions or invent IDs.
7. Provider-free fake Planner for tests.
8. Deterministic validator/merger that:
   - rejects unknown canonical object IDs;
   - rejects malformed/empty retrieval queries;
   - adds baseline checklist coverage independently of model preference;
   - de-duplicates dynamic issues/queries conservatively;
   - preserves provenance (`BASELINE`, `DETERMINISTIC_HINT`, `LLM_DYNAMIC`).
9. Persisted `audit-plan.json` artifact plus read API.
10. Explicit direct-planning size guard: no silent clause truncation. Contracts beyond the direct Planner input budget must return a structured `HIERARCHICAL_PLANNING_REQUIRED` condition for Stage 13C.
11. Any live Planner call must cross the Stage 13A provider boundary.

### Non-goals for 13B

- Do not yet replace the current Stage 8 primary audit execution path.
- Do not yet implement Map/Reduce long-contract planning (13C).
- Do not yet change legal retrieval to issue-by-issue execution (13D).
- Do not yet change DeepSeek primary findings (13E) or Kimi review semantics (13F).
- Do not expand OCR or legal corpus.
- Do not start tray/history/storage-management work.

### Legacy topic-router migration rule

The existing eight Stage 8 keyword topics remain temporarily available for old Stage 8 compatibility, but from Stage 13B onward they are classified as **deterministic hints**, not the future authoritative audit scope. Stage 13D will remove their role as the sole retrieval/audit entrypoint.

### Validation gates

Backend regressions must prove:

- baseline coverage cannot be removed by an empty/weak model draft;
- `UNKNOWN` and `MIXED` are valid classifications;
- Planner cannot cite nonexistent clause/Evidence IDs;
- deterministic Stage 5 anomalies survive into the final plan;
- existing keyword topics contribute hints but do not cap dynamic issues;
- duplicate LLM issues are merged predictably;
- over-budget contracts fail closed with `HIERARCHICAL_PLANNING_REQUIRED` instead of truncation;
- fake/provider-free tests require no API key or paid call;
- a live Planner boundary cannot bypass `REQUIRE_APPROVAL`, `LOCAL_ONLY`, or cancellation.

Existing Stage 11 quality gates and Stage 12/13A regressions must remain green.

## Stage 13C — Hierarchical planning for long contracts

Pending until 13B is independently complete.

Planned shape:

```text
Clause index
 -> bounded local/chunk Planner passes
 -> deterministic merge
 -> global Planner pass over summaries + checklist
 -> final AuditPlan
```

No silent truncation of a long contract is allowed.

## Stage 13D — Issue-based Legal RAG

Pending. Each validated AuditPlan issue will receive its own retrieval queries and Legal Evidence package. Existing hard-coded topic rules become optional deterministic retrieval hints only.

## Stage 13E — DeepSeek issue-by-issue primary audit

Pending. Each planned issue must receive an explicit terminal audit state such as supported finding, no material risk found, insufficient evidence, or review required.

## Stage 13F — Kimi finding + coverage review

Pending. Kimi must review both individual primary findings and coverage of the complete AuditPlan, so a missing primary finding is distinguishable from an issue that was actually reviewed and found acceptable.

## Stage 13G — End-to-end regression

Pending. Validate Planner coverage, issue-based retrieval, primary audit, secondary coverage review, provider boundary, cancellation/restart semantics and Windows packaged behavior before moving on.

## Deferred roadmap

After Stage 13G:

```text
Stage 14  OCR distribution + DOCX
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF reports + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

Implement **Stage 13B Audit Planner foundation only**. Do not start Stage 13C or later roadmap work in the same iteration.