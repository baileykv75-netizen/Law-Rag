# CURRENT_TASK.md

# Stage 5 — Deterministic Audit Rules

## Goal

Build the first explainable audit layer on top of the Stage 4 canonical contract model.

Stage 5 should detect hard, machine-checkable inconsistencies using ordinary code before any legal RAG or LLM reasoning is introduced. Every rule result must be traceable to canonical objects and ultimately to source Evidence IDs.

This stage does **not** determine nuanced legal risk, retrieve statutes, call DeepSeek/Kimi/Qwen, or implement an Agent.

## Core principle

```text
contract.json
    ↓
deterministic audit rules
    ↓
PASS / FAIL / REVIEW / NOT_APPLICABLE
    ↓
rule explanation + exact canonical/source evidence
```

A deterministic rule must never fabricate missing facts. If required inputs are missing, ambiguous, unresolved, or based on low-confidence OCR, return an explicit non-pass state rather than guessing.

## Inputs

Stage 5 consumes the persisted Stage 4 canonical contract:

```text
runtime/jobs/<job-id>/contract.json
```

The rule layer may follow canonical source spans back to earlier evidence, but it must not bypass Stage 4 and independently reinterpret raw files.

## Output

Persist an audit result such as:

```text
runtime/jobs/<job-id>/audit-rules.json
```

The exact schema is implementation-defined but must be typed, versioned, deterministic for unchanged canonical input, and regression-testable.

## Required rule-result schema

Each rule result should include at least:

- stable rule ID;
- rule version;
- rule family;
- state: `PASS`, `FAIL`, `REVIEW`, or `NOT_APPLICABLE`;
- severity only when appropriate for a deterministic finding;
- concise machine-readable reason code;
- human-readable explanation;
- involved canonical object IDs;
- source spans / Evidence IDs;
- observed values used in the calculation/comparison;
- explicit uncertainty/review reason where applicable.

Do not attach fake probability/confidence scores.

## In scope

### 1. Rule engine boundary

Create a dedicated deterministic rule engine rather than embedding checks in FastAPI routes or Stage 4 extraction code.

Requirements:

- rules registered explicitly;
- stable rule IDs/versions;
- deterministic execution order;
- one rule failure must not silently suppress unrelated rules;
- rule exceptions become visible engine errors/review states rather than disappearing;
- output remains idempotent for unchanged `contract.json`.

### 2. Percentage-total checks

Initial target: explicit payment/phase percentage groups where a conservative grouping rule can identify a common context.

Examples:

```text
首付款30% + 进度款50% + 尾款30% = 110%
```

Requirements:

- never sum unrelated percentages across the whole document;
- preserve each PercentageMention ID and source span;
- detect obvious totals above/below expected 100% only when the group meaning is explicit enough;
- return `REVIEW`/`NOT_APPLICABLE` when grouping is ambiguous;
- arithmetic uses Decimal, not floating-point approximation.

### 3. Explicit amount consistency

Check only comparisons supported by explicit labelled/contextual facts.

Potential deterministic cases:

- duplicate labelled total contract amounts with different numeric values;
- explicit subtotal/total arithmetic when all operands and relationship are recoverable;
- repeated payment amount fields that conflict under the same label/context.

Do not compare every money mention globally.

### 4. Chinese uppercase/lowercase money consistency

Implement a conservative parser for common Chinese uppercase RMB forms only if it can be covered well by tests.

Examples:

```text
人民币壹拾万元整
人民币拾万元整
```

If reliable parsing is not achieved in this stage, record uppercase money as a review limitation rather than shipping a weak comparison rule.

### 5. Party-name consistency candidates

Stage 4 deliberately did not decide entity equivalence. Stage 5 may now detect explicit inconsistencies conservatively.

Requirements:

- group mentions by the same explicit role label first;
- normalize only lossless formatting differences (whitespace, safe punctuation where justified);
- exact normalized equality can pass;
- conflicting explicit names for the same role can fail/review;
- do not fuzzy-merge different company names automatically;
- preserve all conflicting mention IDs/evidence.

Example:

```text
甲方：北京甲建设有限公司
...
甲方：北京甲建筑有限公司
```

should not be silently treated as the same entity.

### 6. Identifier consistency

For the same explicit label (for example `合同编号`), detect multiple conflicting values.

Requirements:

- exact normalized equality is consistent;
- conflicting values produce a deterministic finding;
- different labels such as `合同编号` and `项目编号` are not compared as if identical;
- preserve IdentifierMention IDs and evidence.

### 7. Date-order rules

Only compare dates when explicit field/context labels support the relationship.

Initial safe checks may include:

- signing date vs explicit effective date;
- start date vs end date;
- delivery date vs signing date only if rule semantics are explicitly configured rather than assumed globally.

Impossible dates are already unresolved Stage 4 facts and should route to `REVIEW`, not be reinterpreted.

Do not infer missing dates.

### 8. Required-field profiles

Required fields depend on contract type/use case, so do not hard-code a universal claim that every contract must contain the same fields.

Implement explicit audit profiles, initially a neutral/basic profile such as:

- at least two resolved party mentions;
- at least one explicit contract title candidate;
- optionally an identifier/date only if the selected profile requires it.

The selected profile must be visible in results.

### 9. Duplicate/conflicting factual values

Detect only deterministic duplicate/conflict patterns with a defined grouping key.

Potential groups:

- same party role;
- same identifier label;
- same explicit date field label;
- same explicit amount field/context label when safely available.

Do not create a generic "different values = conflict" rule without context.

### 10. OCR uncertainty propagation

If a rule depends materially on Stage 4 source spans originating from low-confidence OCR, it must not present a high-impact `FAIL` as unquestionable truth.

At minimum:

- expose the low-confidence source Evidence IDs;
- permit rule state escalation to `REVIEW`;
- keep the deterministic calculation/result visible;
- explain that source recognition requires verification.

### 11. API integration

Add local endpoints for rule execution/retrieval, for example:

```text
POST /api/documents/{job_id}/audit-rules
GET  /api/documents/{job_id}/audit-rules
```

Requirements:

- Stage 4 structure must already exist;
- no external model/API key;
- persist results locally;
- explicit errors for missing/malformed canonical input;
- idempotent output for unchanged input.

### 12. UI integration

Only extend the current UI enough to inspect deterministic checks.

Minimal view:

- total rules executed;
- pass/fail/review/not-applicable counts;
- rule ID/title;
- state/severity;
- concise explanation;
- involved observed values;
- evidence/review warning indicator.

Do not build final legal-risk cards, statute panels, chat, or Agent traces yet.

### 13. Regression tests

Use fictional/synthetic fixtures only.

Cover at least:

- explicit percentage group sums to 100 -> pass;
- explicit percentage group above/below 100 -> fail/review as specified;
- unrelated percentages are not incorrectly summed together;
- same role + same party name -> consistent;
- same role + conflicting explicit party names -> finding;
- same identifier label + conflicting values -> finding;
- different identifier labels are not falsely compared;
- labelled date-order valid/invalid cases;
- unresolved/invalid dates route to review/not-applicable;
- required-field profile pass/fail;
- low-confidence OCR dependency propagates to review;
- rule evidence IDs all originate from canonical source spans;
- engine output deterministic/idempotent;
- missing/malformed contract.json fails explicitly;
- one broken rule cannot erase results/errors from other rules;
- all Stage 1–4 regression tests continue passing.

## Out of scope

Do **not** add any of the following in Stage 5:

- nuanced semantic/legal-risk conclusions;
- statute/legal corpus ingestion;
- legal-version handling;
- embeddings/vector database;
- BM25/vector/hybrid retrieval;
- DeepSeek/Kimi/Qwen API calls;
- LLM-based extraction or rule interpretation;
- Agent framework;
- second-model review;
- real/private contract fixtures;
- public deployment;
- Windows `.exe` packaging.

## Acceptance criteria

Stage 5 is complete only when all of the following are true:

1. A versioned deterministic rule-result schema exists.
2. Rules run through an explicit registry/engine boundary.
3. Rule output always preserves canonical/source evidence links.
4. Percentage arithmetic never blindly sums unrelated percentages.
5. Party consistency uses conservative exact/lossless normalization only.
6. Identifier consistency is grouped by explicit identifier label.
7. Date-order checks require explicit supported field relationships.
8. Required fields are driven by an explicit audit profile rather than universal assumptions.
9. Low-confidence OCR evidence can force a finding into `REVIEW`.
10. Missing/unresolved inputs produce explicit `REVIEW`/`NOT_APPLICABLE` rather than guessed facts.
11. Rule output is persisted locally and deterministic/idempotent.
12. No external LLM/API key is required.
13. Backend deterministic tests pass, including all prior regressions.
14. Frontend build/typecheck passes.
15. CI remains green.
16. README documents verified Stage 5 behavior before completion.

## Completion rule

Do not change this file to Stage 6 until these criteria are actually verified.

When Stage 5 is complete, the next task becomes **Stage 6 — Versioned Legal Knowledge Base**, where public legal authorities are ingested with article identity, issuing body, dates, status/version, jurisdiction and source metadata before any RAG retrieval is built.
