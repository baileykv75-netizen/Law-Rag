# Audit Planner — Stage 13B

## Purpose

Stage 13B introduces a formal review-scope planning layer so the old Stage 8 keyword router no longer represents the future complete audit scope.

The architecture rule is:

```text
Canonical contract structure = facts and evidence locations
Deterministic rules         = certain mechanical anomalies/hints
Audit Planner               = what should be investigated
Legal RAG                   = authoritative legal evidence for each issue (Stage 13D)
Primary/secondary models    = evidence-bounded review conclusions (Stage 13E/13F)
```

The Planner is not a legal-decision engine. It must not declare a clause lawful, unlawful, valid, invalid, enforceable or unenforceable.

## Three independent planning sources

A final `audit-plan.json` is the deterministic merge of:

```text
1. Baseline checklist
2. Deterministic hints
3. LLM dynamic issues
```

No source can delete another source.

### Baseline checklist

A conservative GENERAL checklist is always present and covers at least:

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

Recognized contract types may add type-specific coverage. Supported classification values are:

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

`UNKNOWN` and `MIXED` are valid outcomes. Law-Rag never forces the Planner to guess; these outcomes keep the GENERAL baseline.

### Deterministic hints

Stage 5 `FAIL`/`REVIEW` results become planning hints. `PASS` and `NOT_APPLICABLE` do not create anomaly hints.

The eight historical Stage 8 keyword topics are also retained, but only as deterministic hints. They may add a topic/query/contract-object reference; they are not a cap on what the Planner may discover.

### LLM dynamic issues

The Planner may add contract-specific review topics outside the baseline and historical keyword set. A dynamic issue must contain:

- topic;
- review priority (not final legal risk severity);
- why it deserves investigation;
- zero or more existing canonical object IDs;
- at least one review question;
- at least one concise Legal RAG query.

A dynamic issue may legitimately have no canonical object ID when the concern is an apparent omission rather than an existing clause.

## Evidence integrity

The Planner is never allowed to output Evidence IDs.

It may reference only canonical `clause_id` / `block_id` values supplied by Law-Rag. The application validates those IDs and derives their Evidence IDs deterministically from `contract.json`.

Therefore:

```text
model invents clause/block ID -> reject entire Planner draft
model cannot invent Evidence ID -> field is not in the model schema
```

Retrieval queries and questions are also validated; blank queries are rejected.

## De-duplication

Stage 13B intentionally uses conservative deterministic de-duplication. Topics are merged only when their normalized topic text matches exactly after whitespace/case normalization.

No fuzzy semantic merge is performed because silently merging legally distinct topics is riskier than leaving two review items for later consolidation.

## Direct-planning size guard

Stage 13B does not silently truncate long contracts.

The direct Planner input budget is currently an application-level guard of 60,000 canonical text characters. If the canonical clause/block text exceeds that budget, Law-Rag raises:

```text
HIERARCHICAL_PLANNING_REQUIRED
```

No provider request is made and no shortened audit plan is persisted. Stage 13C will implement bounded chunk planning plus a global merge.

This is an application safety budget, not a claim about any provider's context-window size.

## Provider boundary

Audit Planner is the first external model call in the new architecture.

For a new job, a Planner run with no persisted control record creates the provider control in `REQUIRE_APPROVAL`. A live call then uses the existing Stage 13A atomic provider boundary.

Therefore:

```text
REQUIRE_APPROVAL without approval -> no Planner request
LOCAL_ONLY                         -> no Planner request
cancel_requested                   -> no Planner request
approved/AUTO_CONTINUE             -> active_provider=<provider>-planner -> request
```

An already-started Planner request has the same Stage 13A limitation as other providers: it cannot be made unsent after transmission begins, but cancellation prevents subsequent provider/stage work.

## Persistence

Validated plans are written atomically to:

```text
runtime/jobs/<job-id>/audit-plan.json
```

The artifact records:

- schema/planner versions;
- contract type and confidence;
- source/content fingerprints;
- Planner input fingerprint;
- provider/model/request metadata;
- provider response hash/usage;
- merged issues with provenance;
- derived contract Evidence IDs;
- warnings.

`GET /api/documents/<job>/audit-plan` is read-only and never calls a model.

## API

```text
POST /api/documents/<job>/audit-plan
GET  /api/documents/<job>/audit-plan
```

The POST body accepts a Planner provider name. `deepseek` is the production provider and `fake` is a deterministic provider-free fixture.

## Stage boundary

Stage 13B does **not** yet replace the old Stage 8 primary-audit path. Existing production audit behavior remains available while the new planning artifact is validated independently.

The intended migration is:

```text
13B  formal AuditPlan
13C  hierarchical long-contract planning
13D  issue-based Legal RAG
13E  issue-by-issue DeepSeek audit
13F  Kimi finding + coverage review
13G  end-to-end migration/regression
```
