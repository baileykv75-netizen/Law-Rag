# CURRENT_TASK.md

# Stage 7 — Hybrid Legal RAG

## Goal

Build a measurable, version-aware legal retrieval layer over the Stage 6 canonical legal evidence store.

At the end of Stage 7, Law-Rag should accept an evidence-grounded legal retrieval request, resolve the legally applicable authority versions for an explicit `as_of` date, retrieve/rank relevant article-level Legal Evidence IDs through complementary exact/lexical/semantic channels, and make corpus/version uncertainty visible.

Stage 7 is **retrieval only**. It does not ask DeepSeek/Kimi/Qwen to judge contract risk, write legal conclusions, or invent citations. Primary LLM audit reasoning remains Stage 8.

## Core principle

```text
canonical contract/rule context + explicit as_of
        ↓
version/coverage constraints
        ↓
exact citation lookup
+ lexical/BM25 retrieval
+ semantic retrieval
        ↓
candidate fusion/reranking
        ↓
versioned Legal Evidence IDs
+ retrieval provenance
+ coverage/ambiguity state
```

A retrieval score is not a legal conclusion. A missing hit in an incomplete corpus is not proof that no legal rule exists.

## Hard boundaries inherited from Stage 6

1. Retrieval consumes canonical Stage 6 legal evidence. It must not rebuild anonymous chunks from raw seed files and discard authority/version/article identity.
2. Legal Evidence IDs are created only by the legal knowledge layer. Retrieval may return them but may not fabricate them.
3. `as_of` is mandatory for version-sensitive retrieval paths. The version resolver runs before evidence is accepted as legally applicable.
4. `AMBIGUOUS` legal-version resolution must remain explicit and must not be hidden by ranking.
5. `CURATED_EXCERPT` coverage must propagate to retrieval results. No-hit results from partial coverage must use an insufficient-corpus/review state rather than a negative legal claim.
6. Search/index artifacts are derivative and rebuildable. SQLite authority/version/article records remain the source of truth.

## In scope

### 1. Typed retrieval-domain schema

Create dedicated retrieval models with explicit versioning.

A retrieval request/result should represent at least:

- request/query ID;
- query text;
- optional exact authority title/ID hint;
- optional explicit article token/citation hint;
- required or explicitly defaulted `as_of` date;
- requested top-K;
- channels executed;
- Legal Evidence ID;
- authority/version/article metadata;
- channel-specific scores/ranks;
- fused/reranked score;
- matched text/snippet for inspection;
- version-resolution provenance;
- corpus coverage type;
- retrieval state / uncertainty reason;
- index/schema/provider versions.

Do not expose a fake calibrated probability of legal correctness.

### 2. Exact citation / article lookup channel

Implement deterministic exact lookup before probabilistic retrieval.

Support at least:

- internal authority ID + exact article token;
- recognized explicit authority title + article token;
- normalized common Chinese article references such as `第五百八十五条`;
- exact Legal Evidence ID lookup where supplied.

Requirements:

- resolve the applicable authority version for `as_of` first;
- exact article hits receive explicit `EXACT` provenance;
- an exact hit is not displaced solely because a vector similarity score is lower/higher;
- missing article in `CURATED_EXCERPT` becomes coverage-insufficient rather than `NO_SUCH_LAW`;
- ambiguous version resolution blocks exact applicability rather than selecting one silently.

### 3. Lexical / BM25 channel

Use a local deterministic lexical index over canonical article evidence.

Preferred baseline: SQLite FTS5/BM25 if available in the supported Python/SQLite runtime. If a blocker is found, document and use another local implementation without changing the canonical legal schema.

Requirements:

- index stores/references Legal Evidence IDs, never anonymous legal text only;
- Chinese tokenization strategy must be explicit/tested rather than assumed to behave well by accident;
- authority title/article token can receive deterministic lexical boosts;
- lexical index can be rebuilt from `legal.db`;
- version/coverage constraints are applied to returned evidence;
- ranking remains reproducible for unchanged query/index/version.

### 4. Semantic/vector channel

Add a provider-neutral embedding boundary.

Requirements:

- embedding provider/model/version/dimension are explicit;
- vector/index files live under ignored runtime paths;
- canonical article identity and Legal Evidence ID accompany every vector;
- provider can later be replaced by a Chinese/local model without rewriting retrieval-domain logic;
- tests use deterministic fake embeddings where appropriate;
- at least one real/local semantic path must be documented and smoke-testable before Stage 7 is declared complete, unless current dependency/license/platform evidence shows a blocker and the limitation is explicitly accepted;
- external model API must not be required merely to run exact/lexical retrieval.

Do not call a generative LLM for semantic retrieval.

### 5. Candidate fusion / reranking

Combine channels in a deterministic, explainable manner.

Initial options may include reciprocal-rank fusion (RRF) plus explicit exact-match priority and authority/article-token boosts.

Requirements:

- retain each channel's original rank/score;
- fused ranking is deterministic;
- exact citation hits retain priority when applicable;
- duplicate Legal Evidence IDs from multiple channels are merged, not duplicated;
- no opaque LLM reranker in Stage 7;
- fusion parameters/version are stored in retrieval provenance.

### 6. Version-aware filtering

Retrieval must not merely search all historical text and label the top result current afterward.

For authority-specific searches:

```text
resolve authority version on as_of
    ↓
retrieve only applicable version
```

For broad searches across multiple authorities:

- determine candidate authority versions applicable on `as_of` before final evidence acceptance;
- suppress not-yet-effective / expired historical versions unless explicitly requested for historical comparison;
- retain explicit ambiguity/no-applicable states.

Historical comparison mode, if added, must be an explicit request mode rather than accidental mixing.

### 7. Coverage-aware retrieval state

Define retrieval states such as:

- `RESULTS_FOUND`;
- `NO_RESULTS_FULL_COVERAGE` when a complete authority corpus was actually searched;
- `INSUFFICIENT_CORPUS` for partial/curated coverage;
- `VERSION_AMBIGUOUS`;
- `NO_APPLICABLE_VERSION`;
- `INDEX_UNAVAILABLE` / channel degraded when a derivative index is missing.

Exact enum names may differ, but the semantics must be explicit.

A later LLM must be able to distinguish “retrieval found nothing” from “we do not have enough corpus to know.”

### 8. Query construction from current Law-Rag evidence

Add a deterministic retrieval-request boundary that can consume:

- explicit user/developer retrieval text for testing;
- canonical clause text/source context;
- deterministic rule result + observed values;
- explicit contract date/as-of supplied by the caller.

Do not let Stage 7 infer nuanced legal issues through an LLM.

If a deterministic heuristic constructs keywords (for example `违约金`, `格式条款`, `定金`), record the query-construction method and keep the source contract/rule IDs.

### 9. Index build/rebuild lifecycle

Add explicit commands instead of silently indexing at application startup.

Target concept:

```text
python -m app.legal.retrieval_cli rebuild
```

Generated artifacts may include:

```text
runtime/legal/retrieval/
  lexical index / FTS tables or metadata
  vectors.*
  retrieval-manifest.json
```

Requirements:

- source legal DB fingerprint or article-hash set recorded;
- stale indexes detected when `legal.db` changes;
- rebuild is deterministic/atomic where practical;
- index artifacts remain outside Git;
- startup can report index health without mutating it.

### 10. Retrieval API

Add minimal local endpoints, for example:

```text
GET  /api/legal/retrieval/health
POST /api/legal/retrieve
```

Request must expose `query`, `as_of`, `top_k`, and optional authority/article hints.

Response must expose:

- retrieval state;
- channels executed/degraded;
- exact/lexical/semantic/fused provenance;
- applicable version metadata;
- coverage type;
- Legal Evidence IDs and article text/snippet;
- no-result/ambiguity explanations.

No model-generated legal advice in these endpoints.

### 11. Minimal retrieval UI

Extend the Stage 6 legal panel only enough to inspect retrieval quality manually:

- query input;
- visible `as_of` date;
- optional authority/article hint fields if useful;
- top results with title, article token, effective version and Legal Evidence ID;
- channel badges/ranks;
- coverage warning;
- ambiguity/no-result state.

Do not build the final risk-law audit workstation yet.

### 12. Retrieval benchmark

Create a small checked-in benchmark using only public curated/legal seed evidence and fictional contract questions.

Each case should define:

- query;
- `as_of`;
- expected relevant Legal Evidence ID(s);
- optional exact citation expectation;
- expected coverage/ambiguity state when applicable.

Measure at least:

- exact-citation accuracy;
- Recall@1;
- Recall@3;
- Recall@5 where corpus size supports it;
- channel-specific recall;
- fused recall;
- no-result/coverage-state correctness.

The benchmark must make regressions visible in CI. Do not declare retrieval “accurate” based only on a few screenshots.

### 13. Tests

Use fictional legal fixtures for deterministic edge cases plus the verified Stage 6 seed for public retrieval benchmark cases.

Cover at least:

- exact article lookup on the correct `as_of` version;
- explicit article absent from `CURATED_EXCERPT` -> insufficient corpus, not negative legal conclusion;
- old/new version separation by `as_of`;
- ambiguous overlapping versions block confident retrieval;
- lexical query retrieves expected Legal Evidence IDs;
- inline article references do not create fake exact evidence;
- semantic fake-provider ranking is deterministic;
- real semantic provider smoke path is isolated/optional in normal CI;
- fusion merges duplicates and preserves exact-hit priority;
- stale derivative index detected after legal DB/article hash changes;
- retrieval without semantic index degrades explicitly rather than silently pretending all channels ran;
- API health/retrieve behavior;
- benchmark Recall@K thresholds;
- all Stage 1–6 regressions remain green;
- frontend typecheck/build remain green.

## Out of scope

Do **not** add the following in Stage 7:

- DeepSeek/Kimi/Qwen generative audit calls;
- LLM-generated legal-risk analysis;
- model-created statute/article citations;
- second-model legal review;
- Agent framework/orchestration;
- final professional risk cards;
- human approval workflow;
- real/private contract fixtures;
- public deployment;
- Windows installer packaging.

## Acceptance criteria

Stage 7 is complete only when all of the following are true:

1. A versioned retrieval request/result schema exists.
2. Exact citation lookup is deterministic and version-aware.
3. A working local lexical/BM25 channel exists.
4. A provider-neutral semantic embedding boundary exists with a documented real/local smoke path or an explicitly accepted blocker.
5. Candidate fusion is deterministic and retains per-channel provenance.
6. `as_of` version applicability is enforced before final legal evidence is returned.
7. `CURATED_EXCERPT` no-hit behavior cannot masquerade as proof that no legal rule exists.
8. Retrieval/index artifacts are derivative, local, rebuildable and stale-detectable.
9. Retrieval returns only canonical Legal Evidence IDs from Stage 6.
10. Minimal API and UI inspection are implemented.
11. A labeled retrieval benchmark exists with explicit Recall@K output/thresholds.
12. No generative LLM is needed for Stage 7 retrieval.
13. All prior backend regressions pass.
14. Frontend typecheck/production build passes.
15. CI remains green.
16. README documents verified Stage 7 behavior before completion.

## Completion rule

Do not change this file to Stage 8 until all Stage 7 acceptance criteria are actually verified.

When Stage 7 is complete, the next task becomes **Stage 8 — Primary LLM Audit Reasoning**, where a provider-neutral LLM interface (DeepSeek planned first) may reason only over canonical contract evidence plus retrieved Legal Evidence IDs and must support an explicit insufficient-evidence state rather than inventing authorities.
