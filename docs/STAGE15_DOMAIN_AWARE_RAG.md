# Stage 15.4 — Domain-aware Legal RAG

## Purpose

Stage 15.4 narrows each AuditPlan Issue to the legal Corpus Packs that are eligible for that Issue **before** Exact / BM25 / local semantic fusion. It does not create a second RAG pipeline and does not change the proven ISSUE_V1 audit topology.

```text
AuditPlan Issue
 -> deterministic domain route
 -> READY Corpus Pack domain tags
 -> eligible Authority allowlist
 -> as_of applicable Authority Version
 -> Exact Citation + FTS5/BM25 + optional local BGE
 -> deterministic weighted RRF fusion
 -> IssueLegalEvidencePackage
 -> existing ISSUE_V1 primary / finding / comparison flow
```

## Architectural boundary

Unchanged canonical legal identity:

```text
Authority -> Version -> Article / Legal Evidence
```

Unchanged Stage 13 audit topology:

```text
AuditPlan Issue -> IssueLegalContext -> primary audit -> finding audit -> deterministic comparison
```

Stage 15.4 only adds an auditable eligibility layer between one Issue and the existing retrieval engine.

## Domain routing

Implementation: `backend/app/legal/domain_routing.py`.

Current deterministic domains:

```text
INTELLECTUAL_PROPERTY -> domain tag intellectual-property
ENTERPRISE_COMPLIANCE -> domain tag enterprise-compliance
LABOR_DISPUTE -> domain tag labor-dispute
CROSS_DOMAIN -> union of every matched domain
UNMAPPED -> all READY packs, preserving recall
```

The router resolves READY packs through their checked-in `domain_tags`; it does not hardcode one permanent Pack ID per domain. A future READY Pack carrying an existing domain tag can therefore join the eligible set without rewriting the retrieval engine.

### Signal policy

Issue-level signals are read from:

- `topic`;
- `why_review`;
- `questions`;
- `retrieval_queries`;
- `legacy_hint_topics`.

Signals are intentionally conservative. A false positive can incorrectly narrow legal scope, so ambiguous generic words are excluded. When no Issue-level signal matches:

- `EMPLOYMENT` falls back to labor-dispute;
- `EQUITY` falls back to enterprise-compliance;
- `TECHNOLOGY` falls back to IP + enterprise;
- all other contract types retain all READY packs.

The broad fallback is explicit in the persisted route and emits a warning. A no-match route is never treated as proof that no legal rule exists.

## Retrieval scope

`RetrievalRequest.authority_ids_allowlist` is optional. An empty list preserves the historical Stage 7 behavior.

When a scope is supplied, it is enforced in every channel:

### Exact

- a supplied Legal Evidence ID outside the allowlist is rejected from the exact channel;
- an Authority hint outside the allowlist is not resolved;
- recognized title/article exact lookup only searches eligible Authorities.

### FTS5 / BM25

The Authority predicate is applied in the FTS query before ranking, so out-of-domain rows do not consume the lexical candidate budget.

### Local semantic retrieval

Eligible Legal Evidence IDs are derived from `legal.db` first. Semantic vectors outside that set are excluded before semantic ranking.

### Fusion defense

The fused candidate pass checks Authority eligibility again before applicability and final ranking. This is defense in depth rather than the primary filtering mechanism.

## `as_of` version behavior

Domain routing selects **Authorities**, not a hardcoded legal Version. The existing version resolver remains authoritative:

```text
effective_date <= as_of < end_date_exclusive
```

For example, an IP-routed Trademark query resolves:

```text
2026-12-31 -> prc-trademark-law / effective-2019-11-01
2027-01-01 -> prc-trademark-law / effective-2027-01-01
```

Freezing a future Version therefore does not make it prematurely applicable.

## IssueLegalContext provenance

Each `IssueLegalEvidencePackage` now persists an `IssueDomainRoute` containing:

- router version;
- resolved domain;
- eligible Pack IDs;
- eligible Authority IDs from those Packs;
- actual Authority IDs applied to the local store;
- whether scope was applied;
- matched signals;
- whether broad all-READY fallback was used;
- deterministic routing reason.

`IssueLegalContextArtifact` also pins a `domain_routing_fingerprint` over READY Pack versions, domain tags and Authority/Version membership. A Pack routing change makes the stored context stale even when the legal body text itself did not change.

## Legacy / development corpus compatibility

Historical Stage 6/7 seed corpora contain Authorities that are not members of the three Stage 15 READY Packs. If the selected Pack scope has **zero** overlap with the current local legal store, Stage 15.4 records `scope_applied=false` and retains the legacy retrieval behavior with an explicit warning.

If some selected Authorities exist locally and some are absent, only the present intersection is used and the reduction is warned. Production three-domain corpus validation expects the full routed scope to be present.

## Regression and benchmark coverage

Stage 15.4 adds deterministic tests for:

- single-domain labor routing;
- IP + enterprise cross-domain routing;
- contract-type fallback and all-READY fallback;
- exact citation scope enforcement;
- FTS5/BM25 pre-fusion scope enforcement;
- semantic pre-fusion scope enforcement with a deterministic test embedding provider;
- Trademark 2019 -> 2027 `as_of` version resolution under an IP scope;
- persisted Issue-level routing provenance on the real 1274-Article corpus;
- legacy seed compatibility when Stage 15 Pack scope has no local overlap.

Checked-in benchmark:

`legal_data/fixtures/stage15_domain_retrieval_benchmark.json`

The benchmark contains nine natural-language, no-article-hint cases across IP, enterprise compliance and labor. For the full three-domain corpus it compares broad lexical retrieval with domain-scoped lexical retrieval and requires:

```text
scoped Recall@5 >= 0.90
scoped MRR      >= 0.80
scoped Recall@5 >= broad Recall@5
scoped MRR      >= broad MRR
all scoped candidates inside the eligible Authority set
```

The existing optional real `BAAI/bge-small-zh-v1.5` smoke remains the runtime check for the production local semantic provider; Stage 15.4 CI uses a deterministic fake embedding provider to test the scope mechanics without downloading a model.

## Non-goals

Stage 15.4 does **not**:

- change AuditPlan Issue generation;
- change deterministic audit rules;
- add a second legal database;
- change Authority/Version identity;
- change Corpus Release versioning;
- call a remote embedding service;
- change DeepSeek/Kimi request topology;
- package the Windows baseline corpus (Stage 15.5).

## Release gate

Stage 15.4 is not complete merely because the branch contains the implementation. Final closeout requires an observable PR-triggered Stage 15 CI proving:

1. full backend pytest PASS;
2. Stage 15 domain benchmark PASS on the 1274-Article corpus;
3. public deterministic quality gates PASS;
4. frontend production build PASS;
5. existing Stage 13/15.2/15.3 regressions remain green.
