# Hierarchical Audit Planning — Stage 13C

## Purpose

Stage 13C removes the Stage 13B direct-planning size dead end without silently truncating long contracts.

The routing is automatic:

```text
canonical contract <= direct budget
  -> DIRECT Planner pass

canonical contract > direct budget
  -> bounded CHUNK Planner passes
  -> deterministic local validation
  -> bounded GLOBAL synthesis pass
  -> final AuditPlan
```

This stage still creates **review scope only**. It does not perform the Stage 13D Legal RAG or Stage 13E/13F legal conclusions.

## Direct planning

The direct application budget remains 60,000 canonical text/fact characters.

A direct plan records:

```text
planning_mode = DIRECT
planner_passes = [direct-0001]
coverage = one record per canonical clause/block
coverage_complete = true when every canonical object entered the direct pass
```

Short and long contracts therefore share the same coverage schema.

## Stable canonical object index

Planning operates on Stage 4 canonical objects in their persisted order:

- `clause_id` objects;
- `block_id` objects for unnumbered blocks.

Each object retains its Evidence IDs. The Planner may reference only supplied canonical object IDs; it never creates Evidence IDs.

No canonical object is split across chunk requests. If one single canonical object itself exceeds the bounded Planner request limit, planning fails closed. Law-Rag does not cut the object into characters and pretend the complete clause was reviewed.

## Local chunk passes

Long contracts are partitioned deterministically using bounded contiguous canonical-object groups.

Current application bounds:

```text
chunk target canonical text: 18,000 chars
max canonical objects/chunk: 24
max total hierarchical provider passes: 256 (including global pass)
```

These are application safety/resource limits, not claims about a provider context window.

Every source clause/block is a primary member of exactly one local chunk. Regression tests compare the actual canonical text supplied to local Planner calls against the persisted canonical object text byte-for-character at the Python string level.

Each local model draft is validated immediately against only the canonical IDs available to that pass. An invented ID or malformed draft stops hierarchical planning before later passes and no final `audit-plan.json` is persisted.

## Cross-chunk context

Stage 13C does not duplicate adjacent full-text clauses into multiple local passes merely to simulate overlap. Repeating the same Evidence in several chunks would complicate coverage accounting and can overweight a boundary clause.

Instead cross-chunk reasoning is explicit:

```text
all local full-text passes
  -> validated local issue summaries
  + complete canonical object index
  -> GLOBAL synthesis pass
```

The GLOBAL pass is instructed that its `*_INDEX_SUMMARY` text is a navigation/synthesis view only. It must not treat compact previews as a substitute for the original contract; every original object has already been reviewed in full by a local pass.

## Global synthesis input

The global pass receives:

1. all canonical object IDs in stable order;
2. compact deterministic text previews for navigation;
3. global structured facts available from `contract.json`;
4. Stage 5 deterministic hints and legacy keyword hints;
5. deterministic topic-level summaries of validated local Planner outputs.

Local summaries are compressed only for the GLOBAL request. The complete validated local dynamic issues/questions/retrieval queries remain separately preserved and are merged into the final AuditPlan after global synthesis.

Therefore bounding the global request does **not** mean deleting local findings.

If even the compact global synthesis input exceeds the bounded request budget, Law-Rag fails closed and states that a deeper reduction layer is required. It does not silently drop local issues or canonical objects.

## Per-pass versus final issue capacity

`ModelAuditPlanDraft` remains capped at 120 issues for any single external model response.

A long contract can produce more than 120 issues across multiple local passes. Stage 13C deliberately does not rebuild all local outputs as one synthetic `ModelAuditPlanDraft`, because that would incorrectly apply a single-call limit to a multi-pass result.

Instead:

```text
GLOBAL draft
  -> baseline + deterministic merge
  -> merge validated LLM_DYNAMIC issues from every local pass
  -> exact normalized-topic de-duplication
  -> final AuditPlan
```

This preserves the Stage 13B conservative merge semantics while separating provider-response limits from final multi-pass plan capacity.

## Provider boundary and cancellation

Every external Planner pass independently crosses the Stage 13A provider boundary:

```text
chunk-0001
chunk-0002
...
global-0001
```

Before each request Law-Rag performs the same atomic provider/cancellation check. Cancellation after one chunk returns prevents the next chunk/global request from starting.

An already-started request cannot be recalled; this is the same limitation documented in `PROVIDER_BOUNDARY.md`.

## Planning coverage semantics

Every canonical clause/block receives one `AuditPlanningCoverage` record.

Possible states are:

```text
REVIEWED_WITH_ISSUE
REVIEWED_NO_SPECIFIC_ISSUE
```

`REVIEWED_WITH_ISSUE` means the final AuditPlan contains at least one issue referencing that canonical object.

`REVIEWED_NO_SPECIFIC_ISSUE` means the canonical object was supplied in full to a valid Planner pass but no final issue references it.

**It does not mean the clause is lawful, safe, valid or free of material risk.** Legal evaluation happens only after issue-based Legal RAG and the later primary/secondary audit stages.

`coverage_complete=true` is persisted only when every canonical object belongs to a recorded planning pass. Incomplete coverage is a hard error; a partial plan is not persisted.

## Observable pass metadata

`audit-plan.json` schema 1.1 records:

- `planning_mode`;
- `planner_passes`;
- input fingerprint per pass;
- response hash per pass;
- provider request ID/usage when available;
- canonical object IDs assigned to each pass;
- per-object coverage state;
- aggregated provider usage;
- combined response hash.

This makes provider-call count and coverage inspectable without storing hidden model reasoning.

## API behavior

The same endpoint handles both modes:

```text
POST /api/documents/<job-id>/audit-plan
GET  /api/documents/<job-id>/audit-plan
```

POST automatically selects DIRECT or HIERARCHICAL based on the canonical input budget. GET is read-only and never resumes planning or calls a provider.

## Regression coverage

Stage 13C provider-free regressions verify at least:

- a contract above the direct budget automatically switches to hierarchical planning;
- every canonical object's full text appears in a local Planner request;
- no canonical object is omitted;
- short contracts receive the same explicit coverage metadata;
- local invalid IDs fail before global synthesis;
- cancellation after the first chunk blocks all later provider calls;
- one over-limit canonical object is never silently split/truncated;
- the global pass sees all canonical IDs and validated local-topic summaries;
- baseline and deterministic hints survive global/local model behavior;
- local dynamic issues are merged outside the single-response 120-issue limit.

## Stage boundary

Stage 13C does not yet use the AuditPlan to retrieve Legal Evidence or replace the legacy primary-audit path.

Next migration step:

```text
Stage 13D
validated AuditPlan issue
  -> issue-specific retrieval queries
  -> version-aware Legal Evidence package
```
