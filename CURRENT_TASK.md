# CURRENT_TASK.md

# Stage 9 — Universal Secondary Review + Constrained Agent

## Goal

Make Stage 9 simpler and more reliability-first:

**Every contract that completes a valid Stage 8 primary audit receives exactly one secondary-model review.**

There is no cost-saving review gate deciding whether a contract deserves a second call. The normal Stage 9 contract flow is always:

```text
validated Stage 8 primary audit
        ↓
secondary model review (one call per contract)
        ↓
independent evidence/citation validation
        ↓
primary-vs-secondary comparison
        ↓
agreement -> review-report.json
        or
material disagreement / insufficient evidence
        ↓
bounded Agent follow-up tools
        ↓
resolved or HUMAN_REVIEW_REQUIRED
```

The simplification is deliberate: Law-Rag is currently optimizing for audit reliability and engineering clarity rather than minimum token cost.

Stage 9 is still **not** a free-form multi-agent system. Application code owns the mandatory pipeline, evidence packages, tool allowlist, validation, action budget and final escalation state.

## Core design decision

Stage 9 uses **two model calls per completed contract by default**:

```text
Call 1 — Primary audit
DeepSeek / Stage 8

Call 2 — Independent secondary review
Second provider / Stage 9
```

The second provider is called once for the contract-level Stage 8 review package, not once per individual finding.

This keeps the model-call topology simple and predictable while still allowing the reviewer to:

- inspect all validated primary findings together;
- challenge individual findings;
- identify severity/legal-basis/evidence disagreements;
- identify possible omissions within the supplied bounded audit context;
- preserve corpus/version/OCR uncertainty;
- recommend human review when the supplied evidence is not enough.

The Agent/tool layer is **not** called for every contract. It activates only after the two fixed model calls when disagreement, missing context or evidence uncertainty requires bounded follow-up.

## Delivery strategy

Implement Stage 9 in small verifiable sub-phases:

```text
9A — secondary-review schema + deterministic fake provider + universal second-call pipeline
9B — first real secondary provider + independent validation
9C — primary/secondary comparison + bounded Agent follow-up tools
9D — review-report.json + API/UI + human escalation
9E — optional real-provider smoke + regression/documentation
```

Do not implement all sub-phases in one uncontrolled rewrite.

## Hard boundaries inherited from Stages 4–8

1. Raw PDF is not a model-owned source of truth. Contract facts come from canonical Evidence IDs/SourceSpans.
2. Stage 5 deterministic results cannot be rewritten by either model.
3. Legal authority must come from canonical Stage 6 Legal Evidence and Stage 7 retrieval.
4. Stage 8 primary output must already pass deterministic validation before Stage 9 starts.
5. Secondary-model citations must pass a separate deterministic validation layer.
6. Agreement between two models is not proof of legal correctness.
7. `as_of`, legal version, corpus coverage and OCR/source uncertainty remain mandatory context.
8. Contract/legal/primary-model text is untrusted data, never executable instruction.
9. No hidden provider fallback and no automatic third-model call.
10. Private contract evidence may leave the machine only through explicitly configured external provider paths visible to the user.
11. Agent/tool loops are bounded by code; there is no open-ended autonomous loop.

## 9A — Secondary-review domain schema

Create a dedicated versioned Stage 9 schema separate from Stage 8 primary findings.

Represent at least:

- review ID/schema/engine version;
- job ID;
- primary report/context fingerprint;
- secondary provider/model;
- explicit `as_of`;
- exact primary findings supplied;
- exact contract Evidence IDs/canonical object IDs supplied;
- exact Legal Evidence IDs supplied;
- reviewer conclusion for each primary finding;
- reviewer-identified possible omissions within the supplied audit context;
- reviewer severity assessment;
- agreement/disagreement categories;
- reviewer reasoning summaries;
- reviewer suggestions;
- contract/Legal Evidence IDs cited;
- evidence-sufficiency/review reasons;
- provider response hash/safe metadata;
- action/tool trace;
- final escalation state.

Do not generate a fake calibrated confidence percentage from two-model agreement.

## 9A — Universal secondary-call pipeline

Any job with a validated Stage 8 `ai-audit.json` is eligible for Stage 9.

Normal behavior:

```text
load validated ai-audit.json
        ↓
build deterministic secondary-review package
        ↓
call secondary provider exactly once
        ↓
validate reviewer output
        ↓
compare with primary report
```

There is no `NOT_REQUIRED` branch based on risk level, severity or token cost.

If the secondary provider is not configured or fails, return an explicit provider/configuration error. Do not silently treat the primary result as dual-model reviewed.

A previous valid `review-report.json` must survive a later failed provider call or invalid response.

## 9A — Provider-neutral secondary interface

Create an interface such as:

```text
SecondaryReviewProvider
  -> RealSecondaryProvider
  -> FakeSecondaryProvider
```

The first real secondary provider must be selected only after current official API, model, pricing and data-handling documentation is verified during implementation. Kimi, Qwen or another suitable provider may be chosen; do not assume an old model/API name.

Requirements:

- domain logic does not depend on provider-specific SDK objects;
- API key/config comes from local environment only;
- explicit provider/model/base URL;
- bounded timeout/retry;
- no automatic fallback to a third provider;
- normal CI uses deterministic fake provider only;
- health check makes no paid request.

## 9B — Independent reviewer context

The secondary model must not be prompted merely to “check whether DeepSeek is correct.”

It receives a deterministic contract-level review package containing:

- the validated Stage 8 primary findings as **claims to review**;
- the exact canonical contract evidence supplied to/used by Stage 8;
- relevant Stage 5 deterministic rule results;
- the exact Stage 7 Legal Evidence packages;
- explicit `as_of`;
- legal corpus/version warnings;
- OCR/source uncertainty;
- context fingerprints/provenance needed for validation.

The second provider should independently assess:

1. whether each primary finding is supported by the supplied contract/legal evidence;
2. whether severity differs materially;
3. whether the primary legal basis is weak/wrong within the supplied Legal Evidence;
4. whether the primary finding cites the wrong contract evidence;
5. whether an issue appears omitted within the supplied bounded audit context;
6. whether the available evidence is insufficient for a reliable conclusion.

The reviewer does not receive unrestricted raw-file access or web access.

## 9B — Reviewer prompt/output rules

Prompt requirements:

- primary-model output is untrusted claim data, not instruction;
- contract/legal text is untrusted evidence data;
- reviewer must independently evaluate the supplied evidence;
- unsupported law from model memory cannot be authoritative;
- reviewer may cite only supplied IDs;
- uncertainty/disagreement is allowed;
- reviewer must not modify deterministic rule results;
- output strict structured JSON only.

## 9B — Independent secondary validation

Reject at least:

- invented primary finding IDs;
- invented contract/canonical Evidence IDs;
- invented Legal Evidence IDs;
- legal evidence outside the supplied Stage 9 package;
- stale/not-applicable legal versions for `as_of`;
- unsupported factual assertions presented as contract fact;
- malformed state/severity/disagreement enums;
- attempts to erase source/corpus/version uncertainty;
- attempts to rewrite Stage 5 deterministic results.

Secondary validation is independent from Stage 8 validation. Two plausible model outputs do not bypass deterministic evidence checks.

## Primary-vs-secondary comparison

Use explicit categories rather than prose-only comparison.

Suggested categories:

```text
AGREE_SUPPORTED
AGREE_REVIEW_REQUIRED
DISAGREE_RISK_EXISTS
DISAGREE_SEVERITY
DISAGREE_LEGAL_BASIS
DISAGREE_CONTRACT_EVIDENCE
POSSIBLE_PRIMARY_OMISSION
INSUFFICIENT_TO_COMPARE
```

Comparison occurs for every completed Stage 9 contract because every contract has both a primary and secondary result.

Material disagreement does not get resolved by automatically choosing the second model. It either triggers a bounded evidence-gathering action or escalates to human review.

## 9C — Constrained Agent state machine

The Agent is a follow-up mechanism **after** the fixed dual-model audit, not the controller of the audit itself.

Suggested state machine:

```text
PRIMARY_VALIDATED
    ↓
SECONDARY_REVIEW
    ↓
VALIDATE_SECONDARY
    ↓
COMPARE_MODELS
    ├─ agreement/no material gap -> REVIEW_COMPLETE
    └─ disagreement / missing evidence
               ↓
        FOLLOW_UP_GATE
        ├─ allowed bounded tool action
        └─ HUMAN_REVIEW_REQUIRED
               ↓
        RECOMPARE / FINALIZE
```

Maximum follow-up cycles must be explicit, initially **2 or fewer**. No recursive/open-ended loop.

## 9C — Explicit tool allowlist

The Agent may choose only from code-defined tools with validated inputs/outputs.

Initial allowlist may include:

### 1. `inspect_contract_evidence`

Fetch exact known canonical contract Evidence IDs/SourceSpans.

### 2. `get_clause_context`

Fetch parent/neighbor/reference-related canonical clauses for a supplied clause ID.

### 3. `inspect_legal_evidence`

Fetch exact canonical Legal Evidence ID/version/source metadata already in the local legal store.

### 4. `retrieve_more_legal`

Run Stage 7 retrieval with a bounded query and explicit `as_of`.

Requirements:

- query/action recorded;
- no web search;
- no automatic corpus mutation;
- returned IDs still pass version/coverage validation.

### 5. `resolve_contract_reference`

Attempt deterministic lookup of a clause/attachment reference already present in canonical structure.

### 6. `request_ocr_retry`

Available only when OCR/source uncertainty materially affects a disagreement or finding.

The Agent may request a specific retry; application code decides whether a configured retry path exists. Do not OCR the entire document again by default.

## Forbidden tools/actions

Stage 9 must not allow:

- arbitrary shell/file-system commands;
- unrestricted web browsing/legal research;
- editing source contracts;
- editing canonical Legal Evidence;
- changing deterministic rule outputs;
- sending the full raw private contract to providers outside the bounded context builder;
- network calls to unconfigured providers;
- autonomous indefinite retries;
- automatic third/fourth model voting;
- final legal opinion approval on behalf of a human.

## Tool/action provenance

Every attempted action records:

- action ID;
- tool name/version;
- reason/trigger;
- normalized validated arguments;
- input Evidence IDs;
- output Evidence IDs;
- result state;
- attempt/elapsed metadata when useful;
- whether a provider call occurred;
- whether private contract evidence left the machine;
- validation/error details.

Do not store secrets or authorization headers.

## 9D — Final states and human escalation

Suggested final states:

```text
DUAL_MODEL_AGREEMENT
DUAL_MODEL_AGREEMENT_WITH_REVIEW
DISAGREEMENT_RESOLVED_BY_EVIDENCE
HUMAN_REVIEW_REQUIRED
BLOCKED_INSUFFICIENT_EVIDENCE
SECONDARY_PROVIDER_ERROR
```

Human review is required when material disagreement or evidence insufficiency remains after the bounded follow-up budget.

Persist:

```text
runtime/jobs/<job-id>/review-report.json
```

The report preserves:

- primary report/finding IDs;
- secondary review results;
- agreement/disagreement categories;
- evidence IDs used by both models;
- tool/action trace;
- final escalation state;
- safe provider/usage metadata.

## 9D — Minimal API/UI

Possible APIs:

```text
GET  /api/ai/secondary/health
POST /api/documents/<job-id>/secondary-review
GET  /api/documents/<job-id>/secondary-review
```

Minimal UI should show:

- primary provider/model;
- secondary provider/model readiness;
- clear notice that running Stage 9 performs a second external model call;
- primary and secondary conclusions side by side;
- agreement/disagreement category;
- evidence IDs used by each model;
- bounded tool/action trace when follow-up was required;
- final human-review state.

Do not redesign the full document workstation yet.

## Token/cost/privacy policy

Current Stage 9 policy is intentionally simple:

- **one primary model call per contract;**
- **one secondary model call per contract;**
- no selective skipping based on token cost;
- no automatic third-model call;
- Agent/tool follow-up remains conditional and bounded.

Record safe token-usage metadata when the provider exposes it, but do not optimize Stage 9 architecture around saving a small number of tokens before reliability has been benchmarked.

Because two external providers may receive bounded contract evidence, the UI/configuration must make both transmissions explicit. Real sensitive contracts should be used only when the user accepts the configured providers' data-handling terms.

## Test strategy

Normal CI uses deterministic fake providers/tools and no paid API calls.

Cover at least:

- every valid Stage 8 job enters the secondary provider path;
- exactly one secondary model call occurs per normal contract review;
- no per-finding N-call explosion;
- malformed/invented secondary Evidence IDs are rejected;
- stale legal version is rejected;
- secondary model cannot rewrite Stage 5 rule results;
- primary output containing prompt-injection-like text remains untrusted claim data;
- agreement categories are deterministic for fake fixtures;
- disagreements do not silently overwrite primary findings;
- secondary can report a possible primary omission only with supplied evidence IDs;
- allowed tool call executes with validated args/provenance;
- forbidden tool/action is rejected;
- follow-up cycle limit is enforced;
- retrieval follow-up cannot bypass `as_of`/coverage semantics;
- OCR retry unavailable/non-applicable returns explicit state;
- provider failure preserves existing Stage 8 report and previous valid Stage 9 report;
- unresolved disagreement/evidence insufficiency escalates to human review;
- API persistence/load behavior;
- all Stage 1–8 regressions remain green;
- frontend TypeScript/production build remains green.

## Optional real-provider smoke

After deterministic 9A/9B tests are green, add an opt-in real secondary-provider smoke using only synthetic/public data.

Requirements:

- verify then-current official provider/API docs first;
- key from local secret/environment only;
- no private contract in CI;
- normal CI does not spend provider credits;
- smoke checks structured response and citation validation, not subjective legal quality.

## Out of scope

Do **not** add in Stage 9:

- unrestricted multi-agent frameworks;
- autonomous web legal research;
- arbitrary code/shell execution;
- automatic third-model voting;
- final professional document-highlight workstation redesign;
- public SaaS/multi-user accounts;
- final lawyer approval workflow;
- automatic legal-corpus crawling/mutation;
- Windows installer/release packaging;
- claiming two-model agreement equals legal correctness.

## Acceptance criteria

Stage 9 is complete only when all are true:

1. Versioned secondary-review/action schemas exist.
2. Every valid Stage 8 contract performs exactly one secondary-model review by default.
3. Secondary review is contract-level, not one external call per individual finding.
4. Provider-neutral secondary-review interface exists.
5. One real secondary provider is implemented against then-current official docs.
6. Normal CI uses fake provider/tools and no paid API keys.
7. Secondary output passes independent contract/legal Evidence ID + version validation.
8. Explicit agreement/disagreement/possible-omission categories exist.
9. Application-owned constrained follow-up state machine exists with bounded cycles.
10. Explicit tool allowlist exists and forbidden actions cannot execute.
11. Tool/action provenance is persisted.
12. Material unresolved disagreement/insufficient evidence escalates to human review.
13. Local `review-report.json` persistence and minimal API/UI work.
14. No unrestricted Agent, web research, arbitrary shell/file-system tool or automatic third-model voting is introduced.
15. All Stage 1–8 backend regressions pass.
16. Frontend TypeScript/production build remains green.
17. README/architecture docs reflect universal dual-model behavior.
18. CI remains green.

## Completion rule

Do not change this file to Stage 10 until every Stage 9 acceptance criterion is actually verified.

When Stage 9 is complete, the next task becomes **Stage 10 — Professional Audit Workstation UI**, where source-document navigation, exact highlighting, human confirm/reject/review actions and final audit-workstation ergonomics become the main focus.
