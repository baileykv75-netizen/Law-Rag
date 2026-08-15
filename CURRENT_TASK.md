# CURRENT_TASK.md

# Stage 4 — Canonical Contract Structure

## Goal

Convert the page-level evidence produced by Stages 2 and 3 into one typed, evidence-grounded contract representation that later rule, RAG, LLM, and Agent layers can consume consistently.

At the end of this stage, Law-Rag should be able to reconstruct a contract's document hierarchy and common factual values conservatively while preserving exact links back to native/OCR evidence.

This stage does **not** decide whether a clause is legally risky, retrieve statutes, call DeepSeek/Kimi/Qwen, or implement an Agent.

## Core principle

Derived structure is never allowed to replace source evidence.

```text
source page evidence / OCR block evidence
        ↓
normalized evidence stream
        ↓
canonical contract structure
        ↓
clauses / parties / dates / amounts / references
        ↓
EVERY derived object keeps evidence links
```

If structure cannot be recovered reliably, preserve an explicit unresolved/candidate state instead of inventing content.

## Stage boundary

### Inputs

Stage 4 may consume only persisted/local outputs from earlier stages:

```text
runtime/jobs/<job-id>/document.json
runtime/jobs/<job-id>/evidence.json
runtime/jobs/<job-id>/ocr.json   # when OCR was required and run
```

### Output

Create a canonical result such as:

```text
runtime/jobs/<job-id>/contract.json
```

The exact schema is implementation-defined but must be typed, versioned, deterministic for the same input evidence, and regression-testable.

## In scope

### 1. Unified evidence stream

Create one ordered abstraction over native and OCR evidence.

Requirements:

- preserve 1-based page numbers;
- keep native PDF evidence IDs for native pages;
- use OCR block IDs for OCR-derived text where available;
- preserve source method (`native_pdf_text` / `ocr`);
- preserve OCR confidence/coordinates rather than flattening them away;
- retain page text character offsets for native evidence when deriving spans;
- keep stable ordering within each page;
- never silently substitute OCR text for a page already marked `NATIVE_TEXT_USABLE`.

A useful normalized unit may contain:

- unit/span ID;
- page number;
- text;
- source evidence IDs;
- source method;
- character offsets for native page evidence where applicable;
- OCR bbox/polygon references where applicable;
- confidence/uncertainty metadata.

### 2. Canonical contract schema

Define typed Pydantic/domain models under a dedicated contract-structure module rather than continuing to grow generic API models indefinitely.

The schema should include at least:

- schema version;
- job/document ID;
- document title candidate(s);
- ordered sections/clauses;
- party mentions/roles;
- date mentions;
- monetary amount mentions;
- percentage mentions;
- contract/document identifier mentions where recoverable;
- attachment/reference mentions;
- unresolved/candidate items;
- extraction warnings;
- source evidence references for every derived object.

Do not yet assign legal conclusions or legal-risk severity.

### 3. Source span model

Every derived object must point back to source evidence using a reusable source-span model.

A source span should support enough information to locate the derivation later, for example:

- page number;
- evidence ID;
- source method;
- exact quoted source text/excerpt;
- native text character start/end when known;
- OCR block IDs and/or pixel bbox references when known.

Do not expose arbitrary absolute local filesystem paths to the frontend.

### 4. Section/clause hierarchy

Implement deterministic, conservative clause-boundary parsing for common Chinese contract numbering styles.

Initial patterns should consider at least:

```text
第一条 / 第二条 / 第十二条
一、 / 二、 / 三、
（一） / （二）
1. / 2. / 3.
1、 / 2、
1.1 / 1.2 / 2.1
1.1.1
(1) / （1）
```

Requirements:

- preserve the original heading/number token;
- retain body text;
- keep page range;
- support clauses that continue onto the next page;
- do not split every numbered value/date into a clause;
- retain parent/child relationships when numbering makes hierarchy reasonably clear;
- fall back to an `UNNUMBERED`/candidate block when structure cannot be confidently inferred.

Cross-page stitching must be deterministic and covered by tests.

### 5. Party mentions and role extraction

Extract **mentions**, not final legal identity judgments.

Initial deterministic role patterns may include common labels such as:

- 甲方 / 乙方 / 丙方;
- 买方 / 卖方;
- 出租方 / 承租方;
- 委托方 / 受托方;
- 发包方 / 承包方;
- 采购方 / 供应方;
- 用人单位 / 劳动者;
- other role labels only when supported by explicit source text.

Each party mention must preserve:

- raw role label;
- raw entity/name text;
- normalized text only if normalization is lossless/reversible;
- source spans/evidence IDs;
- extraction rule/provenance;
- unresolved state when the label exists but the actual party name is absent/ambiguous.

Do not yet merge similar party names or decide whether two names refer to the same legal entity; that belongs to deterministic audit/entity-resolution work in later stages.

### 6. Dates

Extract common explicit date formats conservatively, for example:

```text
2026年8月15日
2026-08-15
2026/08/15
```

For every date mention preserve:

- raw text;
- normalized ISO date only when it parses unambiguously;
- source span;
- surrounding context/field label when recoverable;
- parser rule/provenance;
- invalid/unresolved state for impossible or ambiguous dates.

Do not infer missing dates from context.

### 7. Monetary amounts and percentages

Extract explicit monetary and percentage mentions while preserving raw source text.

Examples include:

```text
人民币 100,000 元
¥100000.00
10万元
百分之十
10%
```

Requirements:

- raw text is always retained;
- normalized numeric value/unit only when deterministic;
- distinguish money from percentage;
- preserve currency/unit when explicit;
- attach source spans/evidence IDs;
- expose parsing uncertainty instead of guessing;
- avoid treating clause/article numbers as monetary values merely because they contain digits.

Chinese uppercase monetary text may be recorded as a raw candidate in this stage; reliable uppercase-to-number comparison can be completed with Stage 5 deterministic rules if necessary.

### 8. Document/contract identifiers

Conservatively capture explicit identifiers such as fields labelled:

```text
合同编号：...
项目编号：...
协议编号：...
```

Store label, raw value, source span, and extraction provenance.

Do not invent an identifier when no explicit labelled field exists.

### 9. References and attachments

Extract reference mentions without pretending the target always exists.

Initial references may include:

- `附件1`, `附件一`, etc.;
- `见附件...`;
- explicit clause references such as `第八条`, `第8条`, `8.2条` where reasonably unambiguous.

Represent:

- raw reference text;
- reference type;
- source span;
- parsed target label when recoverable;
- resolved target canonical ID when a unique target exists;
- `UNRESOLVED`/`AMBIGUOUS` when it does not.

No semantic interpretation of the referenced content belongs in Stage 4.

### 10. Tables / structured blocks

Do not fabricate table structure from flattened text.

Stage 4 may create table/structured-block objects only when evidence supports a recoverable structure, for example:

- clearly delimited native-text rows;
- spatially aligned OCR blocks with a deterministic reconstruction rule;
- another explicit source structure available from prior evidence.

If reliable table reconstruction is not possible with current evidence, preserve a `TABLE_CANDIDATE`/unresolved structured region rather than generating invented cells.

Full document-layout understanding can evolve later without changing the canonical evidence contract.

### 11. Deterministic extraction provenance

Every derived object should include machine-readable provenance such as:

- extractor/rule ID;
- extractor version;
- confidence category (`HIGH`, `MEDIUM`, `LOW`, or explicit unresolved state) if useful;
- source evidence IDs.

Avoid pseudo-probability scores unless they are actually calibrated.

### 12. API integration

Add a local endpoint for canonical structure generation/retrieval, for example:

```text
POST /api/documents/{job_id}/structure
GET  /api/documents/{job_id}/structure
```

Exact API shape may differ, but it must:

- never require an external model API;
- return explicit errors if OCR-required pages have not been processed successfully enough to build structure;
- persist `contract.json` locally;
- not expose arbitrary local paths;
- be idempotent for unchanged evidence.

### 13. UI integration

Only extend the UI enough to inspect Stage 4 output.

A minimal view may show:

- detected title candidate;
- number of clauses/sections;
- party mentions;
- date/amount/percentage/identifier counts;
- unresolved warnings;
- a simple clause outline with page ranges.

Do not build final legal-risk cards, statute panels, chat, or audit workflow yet.

### 14. Regression tests

Use only synthetic/fictional fixtures.

Add deterministic coverage for at least:

- Chinese `第X条` clause parsing;
- Arabic nested numbering such as `1`, `1.1`, `1.1.1`;
- Chinese `一、` / `（一）` hierarchy;
- cross-page clause continuation;
- mixed native/OCR source evidence retained after structure creation;
- source spans point to valid evidence IDs;
- party role/name extraction;
- ISO/Chinese date extraction;
- monetary amount extraction;
- percentage extraction;
- explicit contract number extraction;
- attachment/clause reference extraction;
- ambiguous/unresolved references remain explicit;
- structure output is deterministic/idempotent;
- missing OCR for required pages produces an explicit incomplete/error state;
- malformed source evidence does not crash the application;
- all Stage 1–3 tests continue passing.

## Out of scope

Do **not** add any of the following in Stage 4:

- legal-risk judgments;
- contract compliance conclusions;
- deterministic risk rules such as payment-total validation or party-name conflict judgment;
- statute/legal corpus ingestion;
- legal-version handling;
- embeddings/vector database;
- BM25/vector/hybrid legal retrieval;
- DeepSeek/Kimi/Qwen API calls;
- LLM-based information extraction;
- Agent framework;
- second-model review;
- real/private contract fixtures;
- public deployment;
- Windows `.exe` packaging.

If deterministic extraction proves insufficient for a category, record the limitation rather than quietly introducing an LLM early.

## Acceptance criteria

Stage 4 is complete only when all of the following are true:

1. Native and OCR evidence can be consumed through one ordered evidence abstraction.
2. A versioned typed canonical contract schema exists.
3. Every derived canonical object has at least one valid source-evidence reference or is explicitly unresolved with supporting source context.
4. Common Chinese and Arabic clause numbering is parsed conservatively.
5. Cross-page clause continuation is represented without losing page/evidence links.
6. Party mentions/roles are extracted without prematurely performing entity equivalence judgment.
7. Explicit date mentions are extracted with raw text and safe normalization.
8. Explicit money/percentage mentions are extracted with raw text and safe normalization.
9. Explicit labelled contract/document identifiers are extracted.
10. Attachment/clause references can be represented as resolved or unresolved.
11. Table structure is never fabricated when evidence is insufficient.
12. Structure output is persisted locally and is deterministic/idempotent for unchanged evidence.
13. Missing/incomplete OCR evidence produces an explicit error/incomplete state rather than silently omitting pages.
14. No external LLM/API key is required.
15. Backend deterministic tests pass, including all prior regressions.
16. Frontend build/typecheck passes.
17. CI remains green.
18. README documents the verified Stage 4 behavior before completion.

## Completion rule

Do not change this file to Stage 5 until the acceptance criteria above are actually verified.

When Stage 4 is complete, the next task becomes **Stage 5 — Deterministic Audit Rules**, where arithmetic, percentages, dates, entity consistency, required fields, and other explainable hard checks are evaluated against the canonical contract model.
