# CURRENT_TASK.md

# Stage 13 — Audit Architecture Refactor

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel control validated
Stage 13B       COMPLETE — Audit Planner foundation validated
Stage 13C       NEXT — hierarchical planning for long contracts
Stage 13D       PENDING — issue-based Legal RAG
Stage 13E       PENDING — DeepSeek issue-by-issue primary audit
Stage 13F       PENDING — Kimi finding + coverage review
Stage 13G       PENDING — end-to-end audit architecture regression
```

The Stage 13 roadmap was deliberately reordered after reviewing the existing Stage 8/9 architecture. Desktop tray/history work is deferred: the more important problem is that the old hard-coded Stage 8 topic router can narrow what the models are allowed to review.

## Stage 13A — Provider boundary + pause/cancel

**Status: complete and retained.**

The persisted provider/cancel control plane remains a hard security boundary. In the new architecture Audit Planner is the first external model call, so Planner/DeepSeek/Kimi must all respect `pipeline-control.json`, cancellation semantics and the atomic outbound-provider boundary.

See [`docs/PROVIDER_BOUNDARY.md`](docs/PROVIDER_BOUNDARY.md).

## Stage 13B — Audit Planner foundation

**Status: complete and independently validated.**

### Architecture now implemented

A versioned `audit-plan.json` is produced by deterministic merging of three independent sources:

```text
Baseline checklist
+ deterministic rule/topic hints
+ LLM dynamic planning
= validated AuditPlan
```

The Planner decides **what should be investigated**. It does not make the final legal conclusion.

### Contract-type layer

The strict Planner schema supports:

```text
GENERAL
PURCHASE
SERVICE
LEASE
EMPLOYMENT
CONSTRUCTION
TECHNOLOGY
LOAN
EQUITY
UNKNOWN
MIXED
```

`UNKNOWN` and `MIXED` are valid outcomes. They keep the conservative GENERAL baseline rather than forcing a guess.

### Baseline coverage

The GENERAL baseline cannot be removed by weak/empty model output and covers at least:

- parties/authority;
- subject/scope;
- price/payment;
- performance/delivery;
- quality/acceptance;
- term/effectiveness;
- breach/liability;
- change/termination;
- force majeure/risk events;
- confidentiality/IP/data;
- dispute resolution;
- notice/attachments/document priority.

Recognized contract types add deterministic type-specific review topics.

### Canonical Planner input

The bounded Planner input contains:

1. complete canonical clause/unnumbered-block text within the direct-planning budget;
2. canonical object IDs and source Evidence IDs;
3. global structured facts derived from `contract.json`, including available title, party, date, amount, percentage, identifier and reference facts;
4. Stage 5 `FAIL`/`REVIEW` hints;
5. the historical Stage 8 keyword topics as deterministic hints only.

Global facts help contract-type classification but the model is not allowed to output fact IDs or Evidence IDs as authoritative references.

### Evidence integrity

The LLM may output only existing canonical `clause_id`/`block_id` values. Unknown object IDs reject the Planner draft.

The LLM does **not** output Evidence IDs. Law-Rag derives contract Evidence IDs deterministically from validated canonical object IDs.

Dynamic issues must contain at least one review question and one non-empty bounded Legal-RAG query. Duplicate topics are merged only by conservative exact normalized topic equality; no fuzzy merge is used.

### Provider boundary

Planner is treated as an external provider step.

New jobs without existing control fail closed to `REQUIRE_APPROVAL`. `LOCAL_ONLY`, missing approval and cancellation all prevent the Planner request before `generate()` starts. The active provider is recorded as `<provider>-planner` after the atomic boundary is crossed.

The deterministic fake Planner is disabled by default and requires:

```text
LAW_RAG_ALLOW_FAKE_AUDIT_PLANNER=1
```

for explicit tests only.

### Long-contract guard

Stage 13B deliberately does not truncate large contracts. The current application-level direct Planner budget is 60,000 canonical text/fact characters.

If exceeded, Law-Rag returns:

```text
HIERARCHICAL_PLANNING_REQUIRED
```

before any Planner provider request and does not persist a shortened plan. Stage 13C is responsible for the hierarchical solution.

### Persistence/API

Validated plans are atomically persisted to:

```text
runtime/jobs/<job-id>/audit-plan.json
```

API:

```text
POST /api/documents/<job-id>/audit-plan
GET  /api/documents/<job-id>/audit-plan
```

GET is read-only and never calls a provider.

### Regression validation completed

Backend tests prove:

- baseline coverage survives empty/weak Planner drafts;
- `UNKNOWN`/`MIXED` remain valid;
- nonexistent canonical object IDs are rejected;
- Stage 5 anomalies survive into the plan;
- old keyword topics contribute hints but do not cap dynamic issues;
- dynamic issues can exist beyond the old topic list;
- duplicate dynamic topics merge predictably;
- Evidence IDs are derived from canonical objects rather than model output;
- canonical title/party global facts enter the Planner input with Evidence lineage;
- blank/missing dynamic retrieval queries are rejected;
- long contracts fail closed instead of truncating;
- new Planner calls default to approval-required;
- `LOCAL_ONLY` and cancellation cannot be bypassed;
- fake Planner is disabled unless explicitly enabled for tests.

CI run #449 passed the initial Planner foundation. CI run #450 passed the hardened global-facts/fake-provider regression set together with all existing backend tests, public quality gates and frontend production build.

See [`docs/AUDIT_PLANNER.md`](docs/AUDIT_PLANNER.md).

### Legacy Stage 8 boundary

Stage 13B intentionally does **not** replace the existing Stage 8 production primary-audit path yet. The old eight-topic router remains temporarily for compatibility, but it is now conceptually a deterministic hint source, not the future authoritative audit scope.

Migration occurs in Stage 13D–13G after long-contract planning is solved.

## Stage 13C — Hierarchical planning for long contracts

**Status: next; not started in the Stage 13B iteration.**

Goal:

```text
Canonical contract
 -> stable clause index
 -> bounded chunk Planner passes
 -> deterministic local-plan validation
 -> deterministic merge/de-dup
 -> bounded global Planner pass over chunk summaries + baseline coverage
 -> final AuditPlan
```

Requirements for 13C:

- no silent omission or character truncation;
- every source clause/block must have explicit planning coverage metadata;
- chunk boundaries must preserve nearby clause context where necessary;
- chunk outputs must obey the same canonical-ID and no-Evidence-ID-invention rules as 13B;
- global Planner cannot delete baseline/deterministic coverage;
- duplicate/overlapping local issues must merge deterministically;
- provider boundary/cancellation must apply to every external Planner request;
- provider-call count must be bounded and observable;
- provider-free regression fixtures must cover a contract above the 13B direct budget.

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

**Stage 13B is closed.**

The next explicit implementation task is **Stage 13C hierarchical planning for long contracts**. Do not start Stage 13D or later work in the same iteration.