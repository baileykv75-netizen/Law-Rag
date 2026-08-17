# Stage 13E — Issue-by-Issue Primary Audit

## Purpose

Stage 13E replaces the legacy pattern of asking the primary model to return an arbitrary list of findings from one topic-gated context.

The new invariant is:

```text
validated AuditPlan issue
+ bounded contract context
+ Stage 13D Legal Evidence package
-> exactly one primary issue result
```

Every planned issue must remain observable through a terminal state. Absence of a finding is no longer allowed to mean either “reviewed and acceptable” or “never reviewed”.

## Terminal states

```text
SUPPORTED_FINDING
NO_MATERIAL_RISK_FOUND
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

`NO_MATERIAL_RISK_FOUND` is deliberately strong. It requires reliable contract Evidence, supplied applicable Legal Evidence, `legal_conclusion=true`, and Stage 13D support state `EVIDENCE_FOUND`. Partial curated-corpus coverage is not sufficient for this state.

## Evidence sufficiency

Stage 13E uses a dedicated sufficiency model instead of overloading the legacy Stage 8 enum:

```text
SUFFICIENT
PARTIAL_LEGAL_CORPUS
INSUFFICIENT_LEGAL_CORPUS
LEGAL_VERSION_UNCERTAIN
SOURCE_UNCERTAIN
CONTRACT_EVIDENCE_INSUFFICIENT
```

These states describe evidence conditions; they are not independent legal conclusions.

## Contract evidence selection

The Audit Planner remains authoritative when it binds an issue to canonical objects:

```text
EXPLICIT_PLAN
```

Some baseline checklist issues intentionally have no explicit clause binding. They are not dropped. Law-Rag performs bounded deterministic local text relevance over the issue topic, review questions and Legal-RAG queries and records:

```text
DETERMINISTIC_CONTRACT_RETRIEVAL
```

This fallback only selects candidate contract evidence for an already-valid AuditPlan issue. It does **not** decide whether an issue is allowed to be audited and therefore does not recreate the historical eight-topic gate.

If no contract object can be selected, the issue receives deterministic `INSUFFICIENT_EVIDENCE`; the model is not asked to invent contract evidence.

Related context is bounded and deterministic: adjacent clauses, parent/child clauses and resolved referenced targets may be supplied in addition to explicit/fallback targets.

## Legal conclusions vs contract/commercial findings

A useful distinction is enforced in the model schema:

```text
legal_conclusion = true | false
```

A contract may contain an ambiguity, one-sided commercial allocation or drafting problem even when the local legal corpus does not contain enough material to support a legal conclusion.

Therefore a `SUPPORTED_FINDING` is allowed with `legal_conclusion=false` if it cites supplied contract Evidence and carefully avoids asserting a legal rule.

If `legal_conclusion=true`, at least one supplied Legal Evidence ID must be cited. A model cannot cite a law/article/Evidence ID not supplied to that issue.

`NO_MATCH_IN_LOCAL_CORPUS` or `VERSION_REVIEW_REQUIRED` can never be converted into a confident legal no-risk conclusion.

## Provider boundary

Every DeepSeek issue request independently crosses the Stage 13A atomic provider boundary:

```text
begin_provider_call(job, "deepseek")
-> outbound request
-> finish_provider_call(job, "deepseek")
```

A cancellation/provider-policy change that wins before the boundary blocks the next request. A request already transmitted cannot be recalled; subsequent issues are stopped.

Direct Stage 13E execution creates a `REQUIRE_APPROVAL` control only when no previous policy exists, so a standalone API call cannot silently default to cloud transmission. Existing explicit pipeline policy is retained.

## Checkpoint and resume

Output:

```text
runtime/jobs/<job-id>/issue-primary-audit.json
```

Stage 13E checkpoints after every completed issue. An interruption is stored as `INTERRUPTED`, never as `COMPLETE`.

On explicit resume, a completed result is reused only when:

- the Stage 13D artifact fingerprint is unchanged;
- the per-issue context fingerprint is unchanged;
- provider and model are unchanged.

This prevents repeated paid calls for already-completed issues while refusing reuse after evidence/context drift.

## Bounded execution

Application-level bounds currently include:

```text
maximum planned issues       256
maximum issue context        120,000 serialized characters
maximum fallback targets     8
maximum related objects      16
maximum global facts         64 / 12,000 fact characters
```

These are application safety controls, not provider context-window claims.

An oversized issue is **not truncated**. It receives `REVIEW_REQUIRED` with `ISSUE_CONTEXT_BUDGET_EXCEEDED`, remains represented in the completed issue set, and no incomplete provider request is sent. If real benchmark data shows that this happens frequently, the correct follow-up is issue-level hierarchical audit rather than silent evidence deletion.

## API

```text
POST /api/documents/<job-id>/issue-primary-audit
GET  /api/documents/<job-id>/issue-primary-audit
```

GET is read-only and never invokes a provider.

## Migration boundary

Stage 13E is an independently validated new artifact path. The existing background production pipeline still uses the legacy Stage 8/9 path during migration.

Stage 13F will build the Kimi finding + coverage reviewer on top of the complete AuditPlan and Stage 13E results. Stage 13G will perform end-to-end regression and packaged-Windows validation before the legacy production path is retired.
