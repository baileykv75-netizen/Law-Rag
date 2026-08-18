# Stage 13F — Kimi Finding + Coverage Review

Stage 13F is the independent secondary-review layer for the new AuditPlan architecture.

It does not review an arbitrary list of DeepSeek findings. It consumes the complete Stage 13E issue-result set, where every AuditPlan issue already has one explicit primary terminal state.

## Execution model

```text
AuditPlan issue
+ Stage 13D issue Legal Evidence
+ Stage 13E primary issue result
+ the same bounded canonical context
        |
        v
Kimi secondary review
        |
        +-- Finding Review
        |   Is the primary result supported by the supplied evidence?
        |
        +-- Coverage Review
            Was this planned issue adequately addressed?
            Is a possible omission still visible in the supplied evidence?
```

One bounded Kimi call is made per AuditPlan issue. `COMPLETE` is impossible unless every planned issue has exactly one Stage 13F result.

## Secondary assessments

Finding assessment:

```text
SUPPORTED
PARTIALLY_SUPPORTED
DISAGREED
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Coverage assessment:

```text
COVERED
COVERED_BUT_QUESTIONABLE
POSSIBLE_OMISSION
INSUFFICIENT_EVIDENCE
```

Agreement between DeepSeek and Kimi is never treated as proof.

`NO_MATERIAL_RISK_FOUND` receives active challenge in the provider prompt and cannot be confirmed by Stage 13F without supplied contract and Legal Evidence. It also cannot be confidently confirmed when the Stage 13D legal support state is incomplete or version-uncertain.

## Evidence controls

Kimi may cite only:

- contract Evidence IDs present in the bounded Stage 13E issue context;
- Legal Evidence IDs present in the Stage 13D package for that issue.

Invented IDs are rejected before persistence.

`POSSIBLE_OMISSION` requires supplied contract Evidence plus an explicit omission title/reasoning. The provider prompt requires supplied Legal Evidence as well when the omission is presented as a legal proposition.

When Stage 13D reports `NO_MATCH_IN_LOCAL_CORPUS` or `VERSION_REVIEW_REQUIRED`, a model claim of fully covered evidence is deterministically downgraded to `INSUFFICIENT_EVIDENCE` coverage with an explicit review reason.

## Bounded requests

```text
max secondary issue requests  256
max serialized secondary context  120,000 chars
```

The context budget includes both the Stage 13E issue context and the primary result.

If an issue exceeds the limit, Law-Rag does not truncate the contract, legal evidence or primary result and does not call Kimi. It emits a deterministic secondary result:

```text
assessment = REVIEW_REQUIRED
coverage_assessment = INSUFFICIENT_EVIDENCE
review_reason = SECONDARY_CONTEXT_BUDGET_EXCEEDED
```

If expert benchmarks later show this frequently, the correct extension is issue-level hierarchical secondary review rather than silent evidence deletion.

## Provider boundary and checkpoints

Every outbound Kimi issue request independently crosses the Stage 13A atomic provider boundary.

After each completed issue, Law-Rag atomically checkpoints:

```text
runtime/jobs/<job-id>/issue-secondary-review.json
```

If the user cancels between issues, the artifact is `INTERRUPTED`. On explicit resume, a completed issue is reused only when provider/model, Stage 13E artifact fingerprint and per-issue context fingerprint still match. Already completed Kimi calls are not repeated.

## Freshness lineage

The Stage 13F artifact binds to:

```text
audit_plan_fingerprint
issue_legal_context_fingerprint
issue_primary_audit_fingerprint
per-issue context_fingerprint
artifact_fingerprint
```

Stage 13E freshness transitively validates the Stage 13D legal context and its AuditPlan/legal-retrieval lineage.

## API

```text
POST /api/documents/<job-id>/issue-secondary-review
GET  /api/documents/<job-id>/issue-secondary-review
```

GET is read-only and never invokes Kimi.

## Scope boundary

Stage 13F provides **complete issue-level coverage review** of the validated AuditPlan. It is intentionally not a second unconstrained Audit Planner.

Kimi may surface a possible omission when it is visible in the supplied target/related canonical evidence for the issue, but Stage 13F does not invent a new unrestricted global review scope from model memory. Cross-issue migration, deterministic comparison, human-review integration and deciding whether an additional global coverage synthesis is justified belong to Stage 13G end-to-end validation.

The legacy Stage 9 secondary path remains untouched until Stage 13G validates and migrates the complete new architecture.
