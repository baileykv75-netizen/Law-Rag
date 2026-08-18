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
Stage 13F       COMPLETE — Kimi finding + issue-coverage review
Stage 13G       IN PROGRESS — end-to-end audit architecture regression + migration
                13G.1 deterministic issue comparison/report COMPLETE
                13G.2 provider-free new-chain regression COMPLETE
                13G.3 production Pipeline migration COMPLETE
                13G.4 RC2 / Issue V1 compatibility boundary COMPLETE
                13G.5 Workspace migration COMPLETE
                13G.6 Human Review migration NEXT
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

One bounded DeepSeek request is run per AuditPlan issue. Every planned issue receives exactly one terminal result:

```text
SUPPORTED_FINDING
NO_MATERIAL_RISK_FOUND
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Each issue receives bounded target/related canonical evidence, structured global facts, deterministic hints and its Stage 13D Legal Evidence package. Model-created canonical/contract/Legal Evidence IDs are rejected.

Legal and commercial/drafting findings are separated with `legal_conclusion=true|false`. A legal conclusion requires supplied Legal Evidence. `NO_MATERIAL_RISK_FOUND` requires reliable contract Evidence, applicable Legal Evidence and Stage 13D support exactly `EVIDENCE_FOUND`; incomplete corpus/version/source evidence cannot silently become a confident no-risk result.

Every DeepSeek issue request crosses Stage 13A. Results checkpoint after every completed issue and explicit resume reuses unchanged completed results. Oversized issue contexts are not truncated or sent.

```text
max planned issues             256
max serialized issue context   120,000 chars
max fallback targets           8
max related objects            16
max global facts               64 / 12,000 fact chars
```

Artifact/API:

```text
runtime/jobs/<job-id>/issue-primary-audit.json
POST /api/documents/<job-id>/issue-primary-audit
GET  /api/documents/<job-id>/issue-primary-audit
```

See `docs/ISSUE_BY_ISSUE_PRIMARY_AUDIT.md`.

## 13F — Kimi finding + coverage review

**Complete; independently implemented as a parallel artifact path.**

Stage 13F performs two distinct tasks for every AuditPlan issue:

```text
Finding Review
- independently challenge/support the Stage 13E DeepSeek result

Coverage Review
- determine whether the planned issue was adequately addressed
- challenge questionable NO_MATERIAL_RISK_FOUND results
- surface a possible omission only when supplied bounded evidence supports it
```

### One AuditPlan issue -> one Kimi result

Stage 13F schedules one bounded Kimi request per AuditPlan issue. `COMPLETE` is impossible unless every AuditPlan issue has exactly one secondary result.

Finding assessments:

```text
SUPPORTED
PARTIALLY_SUPPORTED
DISAGREED
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Coverage assessments:

```text
COVERED
COVERED_BUT_QUESTIONABLE
POSSIBLE_OMISSION
INSUFFICIENT_EVIDENCE
```

This makes secondary coverage auditable rather than treating absence of a second-model finding as proof that an issue was reviewed.

### Evidence controls

Kimi may cite only contract Evidence IDs and Legal Evidence IDs supplied in the same bounded issue context. Invented IDs are rejected.

`POSSIBLE_OMISSION` requires supplied contract Evidence plus an explicit omission title/reasoning. The provider prompt requires Legal Evidence too when the omission is presented as a legal proposition.

A Kimi confirmation of primary `NO_MATERIAL_RISK_FOUND` requires supplied contract and Legal Evidence and cannot be confidently confirmed unless Stage 13D support is exactly `EVIDENCE_FOUND`.

When local legal support is `NO_MATCH_IN_LOCAL_CORPUS` or `VERSION_REVIEW_REQUIRED`, a model claim of fully covered evidence is deterministically downgraded to `INSUFFICIENT_EVIDENCE` coverage with an explicit review reason.

### Provider/cancel + checkpoint resume

Every Kimi issue request crosses Stage 13A independently.

After each completed issue, Law-Rag atomically checkpoints:

```text
runtime/jobs/<job-id>/issue-secondary-review.json
```

Cancellation persists `INTERRUPTED`. Explicit resume reuses a completed issue only when provider/model, Stage 13E artifact fingerprint and per-issue context fingerprint are unchanged, so completed Kimi calls are not repeated.

### Bounds

```text
max secondary issue requests       256
max serialized secondary context   120,000 chars
```

The secondary context budget includes both the bounded Stage 13E issue context and the primary result.

If the complete secondary context exceeds the budget, Law-Rag does not truncate evidence and does not call Kimi. It emits deterministic:

```text
assessment = REVIEW_REQUIRED
coverage_assessment = INSUFFICIENT_EVIDENCE
review_reason = SECONDARY_CONTEXT_BUDGET_EXCEEDED
```

### Artifact / API

```text
runtime/jobs/<job-id>/issue-secondary-review.json
POST /api/documents/<job-id>/issue-secondary-review
GET  /api/documents/<job-id>/issue-secondary-review
```

GET is read-only and never calls Kimi.

### Scope boundary

Stage 13F provides complete **issue-level** coverage review of the validated AuditPlan. It is intentionally not a second unconstrained Audit Planner. Possible omissions can be surfaced from supplied target/related evidence; whether an additional cross-issue global synthesis is justified must be decided from Stage 13G regression/benchmark evidence rather than added by assumption.

The existing production Pipeline and legacy Stage 9 secondary path are not retired in 13F.

See `docs/ISSUE_SECONDARY_REVIEW.md`.

## Stage 13G — End-to-end audit architecture regression + migration

**Status: in progress; 13G.1–13G.5 complete, 13G.6 next.**

Stage 13G validates and connects the complete new chain:

```text
canonical contract
 -> Audit Planner / hierarchical coverage
 -> issue-based Legal RAG
 -> DeepSeek issue primary audit
 -> Kimi issue finding + coverage review
 -> deterministic issue comparison / issue-review-report
 -> human review / workstation
```

Completed in the current Stage 13G migration branch:

- deterministic comparison semantics between Stage 13E and 13F issue states;
- one-to-one AuditPlan coverage through `issue-review-report.json`;
- deterministic human-review priority for Kimi omission/disagreement/insufficient-evidence states;
- provider-free end-to-end new-chain regression;
- application-owned production Pipeline migration to Stage 13 issue artifacts while preserving per-Issue checkpoints and Stage 13A provider controls;
- explicit `ISSUE_V1` / `LEGACY_RC2` / fail-closed `CONFLICT` compatibility boundary, including integrity-checked legacy pipeline snapshots for explicit migration;
- `/workspace` architecture-aware migration: Issue V1 jobs show AuditPlan coverage, every planned Issue, issue Legal RAG, DeepSeek, Kimi, deterministic comparison and evidence links; legacy RC2 jobs retain their original Stage 8/9 view without schema fabrication.

Still required before Stage 13G closes:

- migrate human review from old Finding/Omission identity to Issue identity while preserving append-only legacy decisions and stale detection;
- update batch results and home/intake surfaces to consume/display the new authoritative chain;
- update developer diagnostics for Stage 13 issue artifacts;
- run final provider-free full regression plus clean Windows packaged smoke;
- decide from regression evidence whether Stage 13F needs an additional bounded global coverage-synthesis pass; do not add it merely for symmetry.

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

**Stage 13G.5 Workspace migration is closed at the implementation boundary.**

The next explicit implementation task is **Stage 13G.6 Human Review migration**. Do not begin Stage 13G.7 or Stage 14 in the same iteration.
