# CURRENT_TASK.md

# Stage 13 — Audit Architecture Refactor

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel
Stage 13B       COMPLETE — Audit Planner foundation
Stage 13C       COMPLETE — hierarchical long-contract planning + coverage
Stage 13D       COMPLETE — issue-based Legal RAG
Stage 13E       COMPLETE — DeepSeek issue-by-issue primary audit
Stage 13F       NEXT — Kimi finding + coverage review
Stage 13G       PENDING — end-to-end audit architecture regression + migration
```

Stage 13 prioritizes complete, evidence-bounded and auditable review scope before returning to desktop tray/history work.

## 13A — Provider boundary

Complete. Every Planner/DeepSeek/Kimi request must respect persisted provider policy and cancellation semantics. An already-started request cannot be recalled; cancellation blocks subsequent requests. See `docs/PROVIDER_BOUNDARY.md`.

## 13B — Audit Planner

Complete. `audit-plan.json` is generated from:

```text
baseline checklist
+ deterministic Stage 5 / legacy-topic hints
+ LLM dynamic planning
= validated AuditPlan
```

Baseline review scope cannot be deleted by weak model output. The model may cite only supplied canonical object IDs; Evidence IDs are derived by Law-Rag. Historical eight-topic Stage 8 rules are hints only, not the authoritative audit scope. See `docs/AUDIT_PLANNER.md`.

## 13C — Hierarchical long-contract planning

Complete. Short contracts use one DIRECT Planner pass. Long contracts use bounded CHUNK passes over complete canonical objects plus GLOBAL synthesis. No canonical object is character-truncated merely to fit a request.

`audit-plan.json` records explicit coverage for every canonical clause/block:

```text
REVIEWED_WITH_ISSUE
REVIEWED_NO_SPECIFIC_ISSUE
```

The latter is planning coverage only, never a legal “safe” conclusion. See `docs/HIERARCHICAL_AUDIT_PLANNING.md`.

## 13D — Issue-based Legal RAG

Complete. Every validated AuditPlan issue drives its own retrieval queries through the existing version-aware Stage 7 engine:

```text
AuditPlanIssue
 -> one or more retrieval queries
 -> Exact / lexical / optional semantic / RRF
 -> deterministic as_of version resolution
 -> de-duplicated Legal Evidence
 -> issue-legal-context.json
```

Support states:

```text
EVIDENCE_FOUND
EVIDENCE_FOUND_WITH_LIMITATIONS
NO_MATCH_IN_LOCAL_CORPUS
VERSION_REVIEW_REQUIRED
```

A local no-hit is never interpreted as absence of an applicable legal rule. The artifact is fingerprint-bound to the AuditPlan, contract, legal corpus and retrieval index. See `docs/ISSUE_BASED_LEGAL_RAG.md`.

## 13E — DeepSeek issue-by-issue primary audit

**Complete and independently validated.**

### One planned issue -> one terminal result

The primary model no longer returns an arbitrary finding list for a topic-gated context. Stage 13E runs one bounded audit request per AuditPlan issue and requires one terminal result:

```text
SUPPORTED_FINDING
NO_MATERIAL_RISK_FOUND
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

`COMPLETE` is impossible unless the final result set contains every AuditPlan issue exactly once.

### Evidence context

Each issue receives only its bounded evidence package:

```text
issue topic / questions / provenance
+ target canonical objects
+ bounded related objects
+ bounded global structured facts
+ deterministic Stage 5 hints
+ Stage 13D Legal Evidence
```

Planner-bound canonical IDs are authoritative. If a baseline issue has no explicit object binding, Law-Rag performs deterministic local contract-text relevance to select candidate evidence. This fallback supplies evidence for an already-valid issue; it does not decide whether the issue may be audited and does not recreate the old eight-topic gate.

### Legal vs contract/commercial findings

Stage 13E explicitly separates:

```text
legal_conclusion = true | false
```

A drafting/commercial risk may be `SUPPORTED_FINDING` from supplied contract Evidence with `legal_conclusion=false` even when the local legal corpus is incomplete. A legal conclusion requires supplied Legal Evidence IDs.

The model may cite only supplied canonical IDs, contract Evidence IDs and Legal Evidence IDs. Invented IDs/laws/articles are rejected.

`NO_MATERIAL_RISK_FOUND` is deliberately strong and requires reliable contract Evidence, applicable supplied Legal Evidence, `legal_conclusion=true`, and Stage 13D support state exactly `EVIDENCE_FOUND`. `NO_MATCH_IN_LOCAL_CORPUS`, version uncertainty and partial curated-corpus coverage cannot silently become a confident no-risk conclusion.

### Evidence sufficiency

Stage 13E records:

```text
SUFFICIENT
PARTIAL_LEGAL_CORPUS
INSUFFICIENT_LEGAL_CORPUS
LEGAL_VERSION_UNCERTAIN
SOURCE_UNCERTAIN
CONTRACT_EVIDENCE_INSUFFICIENT
```

These are evidence conditions, not standalone legal conclusions.

### Provider/cancel + checkpoint resume

Every DeepSeek issue request independently crosses the Stage 13A atomic provider boundary.

After every completed issue, `issue-primary-audit.json` is checkpointed. An interruption is persisted as `INTERRUPTED`, never `COMPLETE`.

On explicit retry/resume, a completed issue result is reused only when Stage 13D fingerprint, per-issue context fingerprint, provider and model are unchanged. Provider-free regression proves that an Issue completed before cancellation is not called again after resume; only remaining Issues are sent.

### Bounds

```text
max planned issues          256
max serialized issue context 120,000 chars
max fallback targets        8
max related objects         16
max global facts            64 / 12,000 fact chars
```

An oversized Issue is not truncated. It gets deterministic `REVIEW_REQUIRED / ISSUE_CONTEXT_BUDGET_EXCEEDED`; Law-Rag does not transmit a partial context. If real expert benchmarks show this frequently, add issue-level hierarchical auditing instead of deleting evidence.

### Artifact / API

```text
runtime/jobs/<job-id>/issue-primary-audit.json

POST /api/documents/<job-id>/issue-primary-audit
GET  /api/documents/<job-id>/issue-primary-audit
```

GET is read-only and never invokes a provider.

### Validation

Provider-free regressions prove:

- every AuditPlan issue receives one terminal primary result;
- baseline issues without explicit canonical binding can obtain deterministic local contract candidates;
- model-created canonical/contract/legal Evidence IDs are rejected;
- no local legal hit cannot become `NO_MATERIAL_RISK_FOUND`;
- contract-only commercial/drafting findings can remain visible without pretending to be legal conclusions;
- cancellation between issues checkpoints completed work without false `COMPLETE`;
- resume reuses completed issue results and does not repeat their provider calls;
- oversized issue contexts are not truncated or sent to the provider;
- Stage 13D/13E HTTP routes are mounted in the main app;
- existing backend regressions, public deterministic quality gates and frontend production build remain green.

CI #480 passed the initial Stage 13E implementation. CI #482 passed the dedicated evidence-sufficiency hardening. CI #485 passed checkpoint-resume and oversized-context safety together with the full backend/quality/frontend suite.

See `docs/ISSUE_BY_ISSUE_PRIMARY_AUDIT.md`.

### Migration boundary

Stage 13E remains a parallel validated artifact path. The existing background production Pipeline still uses the legacy Stage 8/9 path until Stage 13F and Stage 13G are validated. Do not retire the legacy path in 13E.

## Stage 13F — Kimi finding + coverage review

**Status: next; implement this stage only.**

Kimi must perform two distinct jobs:

```text
Finding Review
- review each Stage 13E primary issue result against supplied evidence

Coverage Review
- verify the complete AuditPlan issue set was addressed
- challenge questionable NO_MATERIAL_RISK_FOUND results
- surface possible omissions outside the primary result set only when supported by supplied canonical/legal evidence
```

Requirements:

- consume the complete AuditPlan plus Stage 13D and Stage 13E artifacts;
- preserve one-to-one AuditPlan coverage accounting;
- never treat “DeepSeek emitted no finding” as proof of review;
- secondary model may not invent contract/Legal Evidence IDs;
- distinguish disagreement, missing evidence and possible omission;
- every Kimi external call crosses Stage 13A provider/cancel control;
- bounded long-plan scheduling/checkpoints are required;
- no automatic retirement of the legacy Stage 9 path yet; that belongs to 13G.

## Stage 13G — End-to-end audit architecture regression

Pending. Validate Planner coverage -> issue Legal RAG -> DeepSeek primary issue audit -> Kimi finding/coverage review -> comparison/human review together with provider boundary, cancellation/restart, packaged Windows behavior and migration from the legacy Stage 8/9 route.

## Deferred after Stage 13G

```text
Stage 14  OCR distribution + DOCX
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF reports + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 13E is closed.**

The next explicit implementation task is **Stage 13F Kimi finding + coverage review**. Do not start Stage 13G or switch the production pipeline in the same iteration.
