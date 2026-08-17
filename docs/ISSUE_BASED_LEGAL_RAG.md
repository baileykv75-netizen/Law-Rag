# Stage 13D — Issue-based Legal RAG

## Purpose

Stage 13D changes the legal-retrieval entry point from the historical Stage 8 hard-coded topic router to the validated `AuditPlan` produced by Stage 13B/13C.

The governing rule is:

> Every validated AuditPlan issue owns its own Legal RAG queries. Historical keyword topics may contribute deterministic hints to the AuditPlan, but they no longer decide whether an issue is eligible for legal retrieval.

Stage 13D is local-only. It does not call DeepSeek, Kimi, or any external model provider.

## Input

Required local artifacts/data:

```text
audit-plan.json
legal.db
retrieval.db
```

`audit-plan.json` must have `coverage_complete=true`. Law-Rag refuses to build legal context from a partial planning scope.

Each `AuditPlanIssue` must contain at least one validated `retrieval_query`.

## Retrieval flow

For every AuditPlan issue:

```text
AuditPlanIssue
  -> retrieval_query 1 -> Stage 7 retrieval engine
  -> retrieval_query 2 -> Stage 7 retrieval engine
  -> ...
  -> preserve every RetrievalResponse
  -> de-duplicate Legal Evidence IDs across queries
  -> retain query provenance
  -> IssueLegalEvidencePackage
```

The existing Stage 7 retrieval engine remains authoritative for:

- deterministic exact article/Legal Evidence lookup;
- FTS5 trigram lexical retrieval;
- optional semantic retrieval when a compatible semantic index is present;
- RRF fusion;
- as-of legal-version resolution;
- `CURATED_EXCERPT` coverage warnings;
- exact Legal Evidence IDs and version IDs.

Stage 13D does not reimplement those mechanics.

## Persisted artifact

Output:

```text
runtime/jobs/<job-id>/issue-legal-context.json
```

The artifact records:

- audit-plan schema/planner versions;
- complete audit-plan fingerprint;
- contract source/content fingerprints inherited from the plan;
- `as_of` date used for legal-version resolution;
- every issue and its contract object/Evidence IDs;
- every retrieval query and full `RetrievalResponse`;
- de-duplicated Legal Evidence candidates;
- which query indexes matched each Legal Evidence ID;
- legal source fingerprint;
- retrieval-index fingerprint and retrieval metadata;
- semantic provider/model when actually executed;
- artifact fingerprint.

## Legal Evidence de-duplication

If multiple queries find the same Legal Evidence ID, Stage 13D stores one issue-level Legal Evidence hit and records all matching query indexes.

Example:

```text
query 1 -> Article 585
query 2 -> Article 585

issue legal evidence:
Article 585
matched_query_indexes = [1, 2]
```

The underlying query-specific retrieval responses remain preserved, so ranking/channel provenance is not lost.

## Support states

Issue support states describe only what the current local corpus/retrieval layer returned. They are not legal conclusions.

```text
EVIDENCE_FOUND
EVIDENCE_FOUND_WITH_LIMITATIONS
NO_MATCH_IN_LOCAL_CORPUS
VERSION_REVIEW_REQUIRED
```

`NO_MATCH_IN_LOCAL_CORPUS` must never be interpreted as:

```text
no applicable law exists
```

In particular, the current bundled corpus contains `CURATED_EXCERPT` versions. A no-hit result means only that the current local corpus did not return supporting Legal Evidence for the query.

## Version semantics

The POST API requires an explicit `as_of` date.

Legal candidates are retained only when the Stage 7 version resolver considers that authority/version applicable as of that date.

If version resolution is ambiguous or no applicable stored version exists, the issue is marked `VERSION_REVIEW_REQUIRED`; Law-Rag does not silently substitute a different legal version.

## Freshness guards

A persisted Stage 13D artifact is stale if either:

1. `audit-plan.json` changes; or
2. the legal corpus changes; or
3. retrieval-index metadata/configuration changes.

Freshness is checked using:

```text
audit_plan_fingerprint
legal_source_fingerprint
retrieval_index_fingerprint
```

The read API returns a stale conflict instead of silently serving old legal context.

## Resource bounds

Stage 13D does not silently drop planned queries.

The current application-level safety limit is:

```text
MAX_TOTAL_RETRIEVAL_QUERIES = 2000
```

If a plan exceeds this bound, the build fails before persisting an apparently complete artifact.

## API

```text
POST /api/documents/<job-id>/issue-legal-context
GET  /api/documents/<job-id>/issue-legal-context
```

POST body:

```json
{
  "as_of": "2026-08-17",
  "use_semantic": false,
  "top_k_per_query": 5
}
```

GET is read-only with freshness validation. It never performs Legal RAG or provider work.

## Planner API integration repair

During Stage 13D integration, Law-Rag found that `audit_planner_api.py` existed but was not mounted into the main FastAPI router. Stage 13D mounts both:

```text
/api/documents/<job-id>/audit-plan
/api/documents/<job-id>/issue-legal-context
```

and adds OpenAPI/API regression coverage so this cannot silently regress.

## Validation

Provider-free regressions verify that:

- an LLM-dynamic topic outside the historical eight-topic router can independently drive Legal RAG;
- Civil Code Article 585 is retrieved and version-pinned from dynamic issue queries;
- duplicate evidence across multiple queries is de-duplicated while query provenance survives;
- contract Evidence IDs from the AuditPlan survive into the issue package;
- no-hit results explicitly avoid negative legal conclusions;
- historical `as_of` dates preserve `NO_APPLICABLE_VERSION` behavior;
- changing the AuditPlan makes the persisted legal context stale;
- Planner and issue-legal-context routes are actually mounted in FastAPI;
- all existing Stage 7 quality gates remain green.

## Stage boundary

Stage 13D creates the legal Evidence package only.

It does **not** replace the old Stage 8 primary-audit execution path in this iteration. Stage 13E will consume `audit-plan.json + issue-legal-context.json` and implement DeepSeek issue-by-issue primary audit. The production pipeline is migrated only after the new audit stages are validated.
