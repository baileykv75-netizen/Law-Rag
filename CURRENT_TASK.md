# CURRENT_TASK.md

# Stage 6 — Versioned Legal Knowledge Base

## Goal

Build a trustworthy, local, version-aware legal-authority layer before any RAG retrieval or LLM legal reasoning is introduced.

At the end of this stage, Law-Rag should be able to import, validate, persist and inspect authoritative legal texts at article level while preserving exact source/version metadata and selecting the legally relevant version for a requested date when the metadata supports that decision.

This stage does **not** build embeddings, vector search, BM25 ranking, DeepSeek/Kimi/Qwen reasoning, or an Agent.

## Core principle

```text
authoritative public legal source
        ↓
source snapshot / normalized import record
        ↓
version-aware authority model
        ↓
article-level canonical legal evidence
        ↓
local validated legal database
```

Legal text must never enter the system as anonymous chunks with no title/article/version/source identity.

## Authoritative-source policy

For real legal seed data, use authoritative public sources only.

Initial preferred sources:

1. National Laws and Regulations Database (全国人大常委会办公厅 / 国家法律法规数据库) for national laws and other authority classes it publishes;
2. official State Council / Ministry of Justice administrative-regulation sources when needed for authoritative version/history confirmation;
3. Supreme People's Court official publication/gazette sources for judicial interpretations when source/version confirmation is required.

Do not use commercial law databases, blogs, search-result snippets, copied legal websites, or model memory as the source of record.

If two official sources disagree or version history is unclear, preserve the conflict explicitly and do not silently choose a version.

## Runtime/storage boundary

Target layout:

```text
legal_data/
  schemas/                 # checked-in schema/docs
  importers/               # deterministic import code
  fixtures/                # fictional legal fixtures for tests
  seed/                    # only curated/verified public source records if intentionally checked in

runtime/legal/
  legal.db                 # generated local SQLite database, ignored by Git
  source_snapshots/        # downloaded/imported source snapshots, ignored unless explicitly curated
  import_reports/          # validation/import reports, ignored
```

Generated SQLite databases and live-download snapshots must remain out of Git by default.

## In scope

### 1. Dedicated legal-domain schema

Create typed legal-domain models separate from contract/audit models.

The model must represent at least:

- authority ID;
- authority title;
- authority type / legal level;
- issuing body;
- document/promulgation number when available;
- jurisdiction/scope;
- authority version ID;
- version status;
- promulgation/publication date;
- effective date;
- expiry/repeal date when available;
- version relationship (`supersedes`, `superseded_by`, amendment lineage when known);
- source identity / official source URL;
- source snapshot/content hash;
- article ID;
- article number/token;
- exact article text;
- article content hash;
- import provenance and schema/importer version.

Do not attach vector embeddings in Stage 6.

### 2. Explicit authority/status enums

Define stable enums instead of free-text strings where practical.

Initial authority classes may include:

- `LAW`;
- `ADMINISTRATIVE_REGULATION`;
- `JUDICIAL_INTERPRETATION`;
- other classes only when actually required and source semantics are clear.

Version/status states should distinguish at least:

- `NOT_YET_EFFECTIVE`;
- `EFFECTIVE`;
- `SUPERSEDED` / `AMENDED` as the adopted model requires;
- `REPEALED`;
- `UNKNOWN`.

Do not infer status from publication order alone.

### 3. Stable legal Evidence IDs

Every imported article must receive a deterministic legal Evidence ID that survives re-import of unchanged source material.

Target concept:

```text
legal:<authority-id>:<version-id>:<article-id>
```

Exact formatting may differ, but IDs must be deterministic and machine-safe.

Later RAG/LLM layers must cite these IDs rather than inventing statute/article references.

### 4. Source snapshots and hashes

For each real imported authority/version:

- preserve the official source identity/URL;
- preserve or reference a local source snapshot when feasible;
- hash the normalized source snapshot/content;
- hash every article text;
- record importer/schema version;
- detect silent source changes on re-import.

If an official webpage changes while metadata claims the same version, emit a validation warning/error instead of silently overwriting history.

### 5. Deterministic article parsing

Implement article segmentation for common Chinese legal-text forms such as:

```text
第一条
第二条
第十条
第一百二十三条
```

Requirements:

- preserve original article token;
- preserve exact article text;
- do not lose headings/chapters when useful for context;
- do not split article-number references appearing inside ordinary paragraphs as new articles;
- support preamble/supplementary text explicitly rather than discarding it;
- parsing is deterministic and covered by fixtures.

No LLM article segmentation.

### 6. Local SQLite persistence

Use local SQLite as the Stage 6 structured legal store unless implementation evidence reveals a blocker.

Requirements:

- no external database server;
- schema version/migration metadata;
- unique constraints preventing duplicate authority/version/article identity;
- transactions for imports;
- rollback on validation failure;
- deterministic rebuild from the same curated inputs;
- generated database under ignored runtime storage.

Stage 7 may add FTS/BM25/vector indexes later without changing the canonical legal evidence schema.

### 7. Historical/version relationships

Do not retain only the latest legal text.

Represent historical versions whenever reliable official metadata is available.

At minimum support a query like:

```text
get authority/article version applicable on YYYY-MM-DD
```

Selection must use explicit effective/repeal/supersession metadata.

If version intervals overlap ambiguously or dates are incomplete, return an explicit ambiguity/error rather than guessing.

### 8. `as_of` semantics

Add a deterministic legal-version resolver that can answer:

- version effective on a requested date;
- current effective version based on stored metadata;
- no applicable version;
- ambiguous version.

The current wall-clock date must not be baked into stored legal evidence. Queries may supply `as_of`; UI/API defaults, if any, must make the resolved date visible.

### 9. Import pipeline / manifest

Create an explicit import manifest rather than hard-coding legal texts inside Python modules.

A normalized manifest/source record should capture:

- source name/URL;
- authority metadata;
- expected source hash when curated;
- parser/importer type;
- local snapshot path when used;
- validation state.

Support an explicit import/rebuild command, for example:

```text
python -m app.legal.cli rebuild --manifest ...
```

Exact command may differ.

Do not make Law-Rag depend on live web scraping every time the application starts.

### 10. Curated seed corpus

Before Stage 6 completion, add a **small, verified, contract-relevant seed corpus** from authoritative official sources.

Do not attempt to ingest every Chinese law in one iteration.

Seed selection should prioritize the laws/interpretations most useful for later contract review and must be chosen only after current official source/version verification.

For every seed item record:

- why it is included;
- official source;
- exact version/status;
- effective date;
- article count/hash validation.

If redistribution/packaging of a source snapshot has any unresolved issue, keep the import manifest/provenance but do not silently commit questionable downloaded artifacts.

### 11. Validation report

Every import should produce a machine-readable validation report with at least:

- source recognized;
- source hash;
- required metadata completeness;
- parsed article count;
- duplicate article tokens;
- empty articles;
- version interval conflicts;
- source/version identity conflicts;
- final imported/rejected state;
- warnings/errors.

Invalid critical metadata must block activation of that legal version.

### 12. API / inspection boundary

Add minimal local inspection endpoints, for example:

```text
GET /api/legal/summary
GET /api/legal/authorities
GET /api/legal/authorities/{authority_id}
GET /api/legal/evidence/{legal_evidence_id}
```

A version-resolution endpoint may also be added if useful.

Requirements:

- no RAG ranking;
- no semantic search;
- return source/version/status/effective-date metadata visibly;
- never expose arbitrary local filesystem paths.

### 13. Minimal UI inspection

Only add enough UI to confirm that the local legal knowledge base is healthy, for example:

- authorities count;
- versions count;
- articles count;
- active/invalid import status;
- source names;
- selected authority/version/effective dates.

Do not build the final legal-retrieval panel or risk-law mapping yet.

### 14. Tests

Use fictional legal fixtures for deterministic unit tests. Real seed data is validated separately against official source metadata.

Regression coverage must include at least:

- Chinese article segmentation;
- article references inside prose are not falsely split;
- deterministic legal Evidence IDs;
- same manifest/source rebuild is idempotent;
- changed source hash is detected;
- duplicate authority/version/article identities fail explicitly;
- missing required version metadata is rejected/reviewed according to schema rules;
- effective-date version resolution;
- no-applicable-version case;
- ambiguous/overlapping-version case;
- historical version remains queryable after a newer version is imported;
- transaction rollback on failed import;
- malformed source snapshot/manifest fails explicitly;
- API summary/evidence lookup;
- all Stage 1–5 regressions continue passing;
- frontend build/typecheck remains green if UI is touched.

## Out of scope

Do **not** add any of the following in Stage 6:

- embeddings;
- vector database/index;
- BM25 ranking;
- hybrid retrieval/reranking;
- contract-to-law retrieval;
- DeepSeek/Kimi/Qwen calls;
- LLM legal summaries;
- legal-risk conclusions based on statutes;
- Agent framework;
- secondary model review;
- automatic ingestion of every available Chinese law;
- commercial/legal-database credentials;
- real/private contract fixtures;
- public SaaS deployment;
- Windows `.exe` packaging.

## Acceptance criteria

Stage 6 is complete only when all of the following are true:

1. A versioned typed legal-authority/article schema exists.
2. Every legal article has deterministic legal Evidence ID and source/version identity.
3. Official source URL/identity and content hashes are preserved.
4. Article segmentation is deterministic and tested.
5. SQLite persistence is local, versioned, transactional and rebuildable.
6. Historical versions are not destroyed by later versions.
7. `as_of` version resolution is deterministic and exposes ambiguous/no-version states.
8. Critical metadata/source conflicts block silent activation.
9. An explicit manifest/import pipeline exists; app startup does not require live scraping.
10. A small contract-relevant real seed corpus is verified against current authoritative official sources.
11. Import validation reports are persisted locally.
12. Minimal legal knowledge inspection API exists.
13. No embeddings/RAG/LLM/Agent code is introduced.
14. Backend deterministic tests pass, including Stage 1–5 regressions.
15. Frontend build/typecheck passes if frontend is changed.
16. CI remains green.
17. README documents verified Stage 6 behavior before completion.

## Completion rule

Do not change this file to Stage 7 until these criteria are actually verified.

When Stage 6 is complete, the next task becomes **Stage 7 — Hybrid Legal RAG**, where exact legal citation lookup, lexical/BM25 retrieval, semantic/vector retrieval, fusion/reranking and retrieval-recall evaluation are added on top of the versioned legal evidence store.
