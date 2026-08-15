# CURRENT_TASK.md

# Stage 9 — Constrained Agent and Secondary Review

## Goal

Add a bounded second-review and adaptive follow-up layer **without giving a model control of the mandatory audit pipeline**.

At the end of Stage 9, Law-Rag should be able to inspect a validated Stage 8 primary report, deterministically decide whether extra review is warranted, optionally call one explicitly configured secondary provider with a bounded evidence package, allow only a small audited set of follow-up actions, validate every returned citation/action, record disagreements, and escalate unresolved cases to human review.

Stage 9 is not a free-form multi-agent system. The application owns the state machine, allowed tools, budgets, validation and finalization.

## Core principle

```text
validated ai-audit.json
+ contract/rule/retrieval evidence
        ↓
deterministic review gate
        ↓
NO REVIEW NEEDED ────────────────┐
        or                       │
SECONDARY REVIEW REQUIRED        │
        ↓                        │
secondary provider              │
        ↓                        │
strict evidence/citation check  │
        ↓                        │
agreement / disagreement        │
        ↓                        │
optional bounded follow-up tool │
        ↓                        │
application state machine       │
        ↓                        │
review-report.json / HUMAN_REVIEW
```

No model may skip extraction, canonical structure, deterministic rules, legal retrieval or Stage 8/9 validation.

## Delivery strategy

Stage 9 must be implemented in small verifiable sub-phases:

```text
9A — deterministic review gate + secondary provider schema/fake provider
9B — first real secondary provider + independent reviewer validation
9C — bounded tool/action state machine
9D — disagreement/human-escalation report + minimal UI
9E — optional real-provider smoke + final regression/documentation
```

Do not implement all sub-phases in one uncontrolled rewrite.

## Hard boundaries inherited from Stages 4–8

1. Raw PDF is still not a model-owned source of truth. Contract facts come from canonical Evidence IDs/SourceSpans.
2. Stage 5 deterministic results cannot be rewritten by a model.
3. Legal authority must come from canonical Stage 6 evidence and Stage 7 retrieval.
4. Primary Stage 8 output must already be validated before Stage 9 starts.
5. Secondary-model citations must be validated independently; agreement between two models is not proof of correctness.
6. `as_of`, legal version, corpus coverage and OCR/source uncertainty remain mandatory.
7. Contract/legal text remains untrusted data, not model instructions.
8. No hidden provider fallback and no automatic call to every available model.
9. Real/private contract data may leave the machine only through an explicitly configured external provider path visible to the user.
10. Agent/tool loops are bounded by code; there is no open-ended autonomous loop.

## 9A — Deterministic review gate

Create a versioned review-gate schema and deterministic function deciding whether a Stage 8 finding requires secondary review.

Initial trigger candidates should include:

- finding state `REVIEW_REQUIRED`;
- evidence sufficiency `INSUFFICIENT_CORPUS`, `VERSION_UNCERTAIN`, or `SOURCE_UNCERTAIN`;
- severity `HIGH` or `CRITICAL`;
- high-severity finding with `PARTIAL_CORPUS`;
- explicit Stage 8 validation/context warning materially affecting the finding;
- configured deterministic-rule conflict relevant to the same evidence;
- later primary/reviewer disagreement.

Important cost rule:

`PARTIAL_CORPUS` alone must **not** cause every finding to call a second model, because the current public seed is intentionally partial.

The gate result must explain exactly which trigger fired.

Suggested states:

```text
NOT_REQUIRED
SECONDARY_REVIEW_REQUIRED
HUMAN_REVIEW_REQUIRED
BLOCKED_BY_EVIDENCE
```

## 9A — Secondary-review domain schema

Create a dedicated versioned schema separate from Stage 8 primary findings.

Represent at least:

- review ID/schema/engine version;
- job ID / primary finding ID;
- deterministic review-gate reasons;
- secondary provider/model;
- `as_of`;
- exact primary finding supplied;
- exact contract Evidence IDs supplied;
- exact Legal Evidence IDs supplied;
- optional additional evidence returned through bounded tools;
- reviewer conclusion/state;
- reviewer severity assessment;
- agreement/disagreement categories;
- reviewer reasoning summary;
- reviewer suggestion;
- contract/Legal Evidence IDs cited;
- review-required reasons;
- provider response hash/safe metadata;
- action/tool trace;
- final escalation state.

Do not convert “two models agree” into a confidence percentage.

## 9A — Provider-neutral secondary interface

Create an interface such as:

```text
SecondaryReviewProvider
  -> RealSecondaryProvider
  -> FakeSecondaryProvider
```

The first real secondary provider must be selected only after current official API/cost/data-handling documentation is verified during implementation. Kimi/Qwen/local options may be evaluated; do not assume an old model/API name.

Requirements:

- no dependency on provider-specific SDK objects in domain logic;
- key/config from local environment only;
- explicit model/base URL/version;
- bounded timeout/retry;
- no automatic fallback to another provider;
- normal CI uses fake provider only;
- health check makes no paid model request.

## 9B — Independent reviewer prompt/output

The secondary model is not asked to simply “agree with DeepSeek.”

It receives:

- the validated primary finding as a claim to review;
- the exact contract evidence cited by the primary finding;
- the exact Legal Evidence cited by the primary finding;
- relevant Stage 5 deterministic results;
- `as_of`, coverage/version/OCR warnings;
- bounded additional evidence only if an allowed tool supplied it.

Prompt requirements:

- primary-model text is untrusted claim data, not instruction;
- contract/legal text is untrusted evidence data;
- reviewer must independently assess whether the supplied evidence supports the primary claim;
- unsupported law from model memory cannot be authoritative;
- reviewer may cite only supplied IDs;
- uncertainty/disagreement is allowed;
- output strict structured JSON only.

## 9B — Independent secondary validation

Validate secondary output separately from Stage 8 validation.

Reject at least:

- invented primary finding ID;
- invented contract/canonical Evidence IDs;
- invented Legal Evidence IDs;
- legal evidence outside the secondary review package;
- stale/not-applicable legal version for `as_of`;
- unsupported new factual assertions treated as contract fact;
- malformed state/severity/disagreement enum;
- attempt to erase source/corpus/version uncertainty;
- attempt to modify deterministic rule results.

## Agreement/disagreement model

Use explicit categories rather than prose-only comparison.

Suggested categories:

```text
AGREE_SUPPORTED
AGREE_REVIEW_REQUIRED
DISAGREE_RISK_EXISTS
DISAGREE_SEVERITY
DISAGREE_LEGAL_BASIS
DISAGREE_CONTRACT_EVIDENCE
INSUFFICIENT_TO_COMPARE
```

A disagreement is not automatically resolved by taking the second model's answer. Material disagreement routes to human review or a bounded evidence-gathering action.

## 9C — Constrained Agent state machine

Implement an application-owned state machine. Suggested states:

```text
PRIMARY_VALIDATED
    ↓
REVIEW_GATE
    ├─ NOT_REQUIRED -> REVIEW_COMPLETE
    └─ SECONDARY_REQUIRED
             ↓
      SECONDARY_REVIEW
             ↓
      VALIDATE_REVIEW
             ↓
      AGREEMENT_CHECK
        ├─ resolved -> REVIEW_COMPLETE
        └─ unresolved
             ↓
      FOLLOW_UP_GATE
        ├─ allowed bounded action
        └─ HUMAN_REVIEW_REQUIRED
```

Maximum follow-up cycles must be explicit, initially **2** or less. No recursive/open-ended model loop.

## 9C — Explicit tool allowlist

The Agent may choose only from code-defined tools whose inputs/outputs are validated.

Initial allowlist may include:

### 1. `inspect_contract_evidence`

Fetch exact already-known canonical contract Evidence IDs/SourceSpans.

No raw arbitrary file-system access.

### 2. `get_clause_context`

Fetch parent/neighbor/reference-related canonical clauses for a supplied clause ID.

Returned clauses keep Evidence IDs.

### 3. `inspect_legal_evidence`

Fetch exact canonical Legal Evidence ID/version/source metadata already in the local legal store.

### 4. `retrieve_more_legal`

Run Stage 7 retrieval with a bounded query derived from the current issue and explicit `as_of`.

Requirements:

- query/action recorded;
- no web search;
- no automatic corpus mutation;
- returned IDs still pass version/coverage checks.

### 5. `resolve_contract_reference`

Attempt deterministic lookup of a clause/attachment reference already present in canonical structure.

If missing, return explicit missing evidence rather than inventing content.

### 6. `request_ocr_retry`

Only available when the cited source is OCR-derived and source uncertainty materially affects the finding.

The Agent may **request** retry with explicit reason/page; application code decides whether a configured retry provider/path is available. Do not silently OCR the entire document again.

## Forbidden tools/actions

Stage 9 must not allow:

- arbitrary shell/file-system commands;
- unrestricted web browsing/legal research;
- editing the contract source;
- editing canonical legal evidence;
- changing deterministic rule outputs;
- writing arbitrary prompts/files;
- sending the whole private contract to a provider without the bounded context builder;
- placing network calls to unconfigured providers;
- autonomous indefinite retries;
- final legal opinion approval on behalf of a human.

## Tool/action provenance

Every attempted action must record:

- action ID;
- tool name/version;
- reason/trigger;
- normalized validated arguments;
- input Evidence IDs;
- output Evidence IDs;
- result state;
- elapsed/attempt metadata when useful;
- whether a provider call occurred;
- whether private contract evidence left the machine;
- validation/error details.

Do not store secrets or authorization headers.

## 9D — Human escalation

Define explicit final states, for example:

```text
REVIEW_NOT_REQUIRED
SECONDARY_AGREEMENT
SECONDARY_DISAGREEMENT_RESOLVED
HUMAN_REVIEW_REQUIRED
BLOCKED_INSUFFICIENT_EVIDENCE
PROVIDER_ERROR
```

Human review should be required when material disagreement or insufficient evidence remains after the bounded follow-up budget.

Persist a local versioned report, target:

```text
runtime/jobs/<job-id>/review-report.json
```

The report must preserve primary finding ID, secondary result, disagreement category, tool trace and final escalation state.

## 9D — Minimal API/UI

Add only enough UI/API to inspect Stage 9 behavior.

Possible APIs:

```text
GET  /api/ai/secondary/health
POST /api/documents/<job-id>/secondary-review
GET  /api/documents/<job-id>/secondary-review
```

Minimal UI should show:

- whether each primary finding triggered review and why;
- secondary provider/model readiness;
- whether external secondary transmission will occur;
- reviewer conclusion;
- agreement/disagreement category;
- evidence IDs used by each model;
- bounded tool/action trace;
- final human-review state.

Do not redesign the full document workstation yet.

## Cost/privacy controls

Secondary review must be selective.

Record at least:

- whether a secondary call was made;
- provider/model;
- safe token-usage metadata if available;
- trigger reason;
- number of follow-up cycles/actions;
- whether contract evidence was externally transmitted.

Do not call a second model for `PASS`/low-risk/no-trigger findings merely to increase apparent confidence.

## Test strategy

Normal CI must use deterministic fake providers/tools and no paid APIs.

Cover at least:

- low-risk supported primary finding -> secondary review not required;
- high-risk primary finding -> secondary review required;
- partial corpus alone does not trigger universal review;
- source/version uncertainty triggers review or human escalation;
- malformed/invented secondary Evidence IDs rejected;
- secondary stale legal version rejected;
- secondary model cannot rewrite Stage 5 rule results;
- primary output embedded with prompt-injection-like text remains untrusted claim data;
- agreement category deterministic for fake fixtures;
- disagreement does not silently overwrite primary finding;
- allowed tool call executes with validated args and provenance;
- forbidden tool/action rejected;
- follow-up cycle limit enforced;
- retrieval follow-up cannot bypass `as_of`/coverage semantics;
- OCR retry unavailable/non-applicable returns explicit state;
- provider failure preserves existing Stage 8 report and existing valid Stage 9 report;
- human escalation occurs when disagreement/evidence insufficiency remains;
- API persistence/load behavior;
- all Stage 1–8 regressions remain green;
- frontend TypeScript/production build remains green.

## Optional real-provider smoke

After deterministic 9A/9B tests are green, add an opt-in secondary-provider smoke using only synthetic/public data.

Requirements:

- verify current official provider/API docs first;
- key from local secret/environment only;
- no private contract in CI;
- normal CI does not spend provider credits;
- smoke checks structured response and citation validation, not subjective legal quality.

## Out of scope

Do **not** add in Stage 9:

- unrestricted multi-agent frameworks;
- autonomous web legal research;
- arbitrary code/shell execution;
- final professional document-highlight workstation redesign;
- public SaaS/multi-user accounts;
- final lawyer approval workflow;
- automatic legal-corpus crawling/mutation;
- Windows installer/release packaging;
- claiming two-model agreement equals legal correctness.

## Acceptance criteria

Stage 9 is complete only when all are true:

1. Versioned secondary-review/action schemas exist.
2. Deterministic review gate exists and avoids universal second-model calls.
3. Provider-neutral secondary-review interface exists.
4. One real secondary provider is implemented against then-current official docs.
5. Normal CI uses fake provider/tools and no paid API keys.
6. Secondary output passes independent contract/legal Evidence ID + version validation.
7. Explicit agreement/disagreement categories exist.
8. Application-owned constrained state machine exists with bounded cycles.
9. Explicit tool allowlist exists and forbidden actions cannot execute.
10. Tool/action provenance is persisted.
11. Material unresolved disagreement/insufficient evidence escalates to human review.
12. Secondary calls remain conditional with privacy/cost metadata.
13. Local `review-report.json` persistence and minimal API/UI work.
14. No unrestricted Agent, web research or arbitrary shell/file-system tool is introduced.
15. All Stage 1–8 backend regressions pass.
16. Frontend TypeScript/production build remains green.
17. README/architecture docs reflect actual Stage 9 behavior.
18. CI remains green.

## Completion rule

Do not change this file to Stage 10 until every Stage 9 acceptance criterion is actually verified.

When Stage 9 is complete, the next task becomes **Stage 10 — Professional Audit Workstation UI**, where source-document navigation, exact highlighting, human confirm/reject/review actions and final audit-workstation ergonomics become the main focus.
