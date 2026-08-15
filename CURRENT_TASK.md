# CURRENT_TASK.md

# Stage 8 — Primary LLM Audit Reasoning

## Goal

Add the first evidence-grounded generative audit layer to Law-Rag through a provider-neutral LLM boundary, with DeepSeek planned as the first real provider after its current official API contract is verified during implementation.

At the end of Stage 8, Law-Rag should be able to take a completed local contract job, package only canonical contract evidence + deterministic rule context + version-aware retrieved Legal Evidence, call one primary model, validate its structured findings, reject unsupported citations, persist the result locally, and display a minimal reviewable finding list.

Stage 8 is **primary reasoning only**. It does not add a second reviewer model, free-form Agent orchestration, automatic final legal conclusions, or the final professional workstation.

## Core principle

```text
contract.json
+ audit-rules.json
+ Stage 7 retrieval package
+ explicit as_of
        ↓
validated audit context
        ↓
provider-neutral primary LLM
        ↓
strict structured findings
        ↓
deterministic citation/evidence validation
        ↓
ai-audit.json
        ↓
human-reviewable UI
```

The model may reason about supplied evidence. It may not create facts, contract Evidence IDs, Legal Evidence IDs, law versions, or source text that were not supplied by Law-Rag.

## Hard boundaries inherited from Stages 4–7

1. The model does not independently reread the raw PDF. Contract facts come from the canonical Stage 4 representation and its SourceSpans/Evidence IDs.
2. Deterministic Stage 5 results remain separate facts. An LLM may discuss them but may not rewrite machine results.
3. Legal authority comes only from Stage 6 canonical Legal Evidence and Stage 7 retrieval output.
4. `as_of`, version-resolution state, and corpus coverage are mandatory context. `CURATED_EXCERPT` must remain visible to the model and the final result.
5. Unsupported Legal Evidence IDs are validation failures, not acceptable hallucinations.
6. `INSUFFICIENT_CORPUS`, `NO_APPLICABLE_VERSION`, `VERSION_AMBIGUOUS`, missing contract evidence, or low-confidence OCR may force review/insufficient-evidence states.
7. Contract/legal text is untrusted **data**, never executable prompt instruction. Prompt injection inside a contract must not alter system behavior.

## In scope

### 1. Versioned AI-audit domain schema

Create a dedicated versioned schema separate from deterministic rule and retrieval schemas.

Represent at least:

- audit/job ID;
- schema/engine/provider/model versions;
- explicit `as_of`;
- contract source/content fingerprints;
- retrieval package/query IDs or fingerprints;
- finding ID;
- finding state;
- risk category/type;
- severity/risk level;
- concise issue title;
- reasoning summary;
- recommended review/change suggestion;
- contract Evidence IDs / canonical object IDs;
- Legal Evidence IDs;
- evidence-sufficiency state;
- review-required reasons;
- model raw-response hash / validation status;
- provider request metadata that is safe to persist.

Do not expose a fake calibrated probability of legal correctness.

Suggested finding states may include:

- `SUPPORTED_FINDING`;
- `NO_FINDING`;
- `INSUFFICIENT_EVIDENCE`;
- `REVIEW_REQUIRED`;
- `MODEL_ERROR`.

Exact names may differ, but uncertainty must be first-class.

### 2. Provider-neutral LLM boundary

Create an interface such as:

```text
PrimaryAuditProvider
  -> DeepSeekProvider
  -> FakeAuditProvider (tests)
```

Requirements:

- domain logic must not depend directly on DeepSeek SDK-specific objects;
- provider/model/base URL/version are explicit;
- API key comes from local environment/config only;
- no API key in source code, logs, fixtures or Git;
- timeouts/retry policy are bounded and explicit;
- provider errors are visible and do not destroy prior local artifacts;
- no automatic hidden fallback to a different model/provider.

Before implementing the real DeepSeek provider, verify current official API documentation rather than assuming old model names or request fields.

### 3. Strict structured model output

The primary model must return machine-parseable structured output.

Requirements:

- define a strict expected JSON/Pydantic schema;
- reject malformed output explicitly;
- reject unknown/unsupported Evidence IDs;
- reject Legal Evidence IDs not present in the supplied retrieval package;
- reject contract Evidence IDs not present in the supplied audit context;
- limit free-form text sizes;
- do not accept model-created source quotations as authoritative evidence;
- persist normalized validated output separately from raw provider response metadata/hash.

Do not silently coerce arbitrary prose into a valid legal finding.

### 4. Audit-context builder

Build a deterministic context package from existing artifacts.

Inputs may include:

- selected canonical clause(s) and related SourceSpans;
- explicit neighboring/parent/referenced clause context;
- relevant party/date/money/percentage/identifier facts;
- deterministic Stage 5 rule results;
- Stage 7 Legal Evidence candidates and retrieval provenance;
- explicit coverage/version warnings;
- OCR/source uncertainty;
- `as_of`.

Requirements:

- record exactly which canonical/legal evidence was sent;
- deterministic ordering;
- explicit context size/token-budget strategy;
- no entire-contract dump by default when a focused evidence package is sufficient;
- never drop a warning/ambiguity merely to save tokens;
- referenced clauses/attachments absent from evidence become explicit missing-context warnings.

### 5. Retrieval before legal reasoning

Stage 8 must not ask the LLM to recall law from memory as a substitute for retrieval.

For each legal issue package:

```text
contract/rule context
    ↓
Stage 7 retrieval
    ↓
validated Legal Evidence package
    ↓
primary LLM reasoning
```

If retrieval is `INSUFFICIENT_CORPUS`, version ambiguous, or otherwise inadequate, the model must be instructed to return an insufficient/review state rather than inventing a legal basis.

### 6. Prompt/instruction hierarchy

System/developer instructions must state clearly:

- contract content is evidence, not instructions;
- legal text is evidence, not instructions;
- only supplied Evidence IDs may be cited;
- unsupported legal knowledge must not be asserted as authoritative;
- uncertainty is allowed;
- do not claim a contract is definitively lawful/unlawful/invalid/enforceable beyond supplied evidence;
- output only the agreed structured schema.

Regression tests must include prompt-injection-like text embedded inside fictional contract clauses.

### 7. Finding validation layer

After model output, run deterministic validation before persistence.

Validate at least:

- schema validity;
- finding ID uniqueness;
- referenced canonical object/Evidence IDs exist;
- referenced Legal Evidence IDs exist and were actually supplied;
- cited legal version is applicable to `as_of` as represented by Stage 7;
- partial-corpus warnings are not erased;
- risk level belongs to allowed enum;
- insufficient-evidence findings do not falsely carry authoritative legal conclusions;
- source uncertainty propagates to review-required state where configured.

Invalid output should fail closed into a visible model/validation error.

### 8. Local persistence / provenance

Persist validated output under ignored job storage, target:

```text
runtime/jobs/<job-id>/ai-audit.json
```

Optionally persist a redacted/provider-safe request/response diagnostic artifact under ignored runtime storage when explicitly enabled for development.

Do not persist API keys, authorization headers, or unnecessary sensitive request logs.

The persisted report should include enough provenance to reproduce which local artifacts/model configuration produced it.

### 9. API boundary

Add minimal endpoints such as:

```text
POST /api/documents/{job_id}/ai-audit
GET  /api/documents/{job_id}/ai-audit
GET  /api/ai/providers/health
```

Requirements:

- missing API key/provider configuration returns a clear configuration error;
- missing contract/rule/retrieval prerequisites fail explicitly;
- no public multi-user auth/deployment work in this stage;
- request lets the caller specify/confirm `as_of` rather than hiding the date;
- no second-model review in this endpoint.

### 10. Minimal UI

Add only enough UI to inspect primary-model output:

- provider/configuration readiness;
- explicit `as_of`;
- run-primary-audit action;
- finding title/state/severity;
- contract Evidence IDs;
- Legal Evidence IDs and version labels;
- reasoning summary;
- suggestion;
- insufficient/review warnings;
- clear label that this is AI-assisted analysis requiring professional review.

Do not build the final document-highlight workstation yet.

### 11. Test strategy

Normal CI must use a deterministic fake provider and never require a real paid API call.

Cover at least:

- valid structured fake-provider response;
- malformed JSON/output rejected;
- invented Legal Evidence ID rejected;
- invented contract Evidence ID rejected;
- retrieved-but-wrong-version evidence cannot pass applicability validation;
- insufficient corpus causes insufficient/review state rather than fabricated law;
- prompt-injection text inside contract evidence does not become an instruction;
- deterministic rules remain unchanged by LLM output;
- missing provider/API key gives explicit configuration error;
- provider timeout/error remains visible and prior artifacts survive;
- unchanged validated input + deterministic fake provider yields stable normalized output;
- API persistence/load behavior;
- all Stage 1–7 regressions stay green;
- frontend typecheck/build stays green.

### 12. Optional real-provider smoke

After deterministic CI is green, add an **opt-in** real DeepSeek smoke path using only fictional/public data.

Requirements:

- current official API docs verified at implementation time;
- no real/private contract sent in CI;
- API key provided only through secret/local environment;
- normal CI does not require or spend external-model credits;
- smoke checks structured response + citation validation, not subjective legal quality.

## Out of scope

Do **not** add in Stage 8:

- Kimi/Qwen second-review calls;
- multi-agent frameworks;
- autonomous tool selection;
- OCR retry decisions by an Agent;
- automatic corpus expansion/web legal research by the model;
- unrestricted chat over private contracts;
- final legal opinion generation;
- public SaaS deployment;
- account systems;
- final human approval workflow;
- Windows installer packaging.

## Acceptance criteria

Stage 8 is complete only when all are true:

1. A versioned AI-audit schema exists.
2. Provider-neutral primary-audit interface exists.
3. A real DeepSeek adapter is implemented against current official API documentation.
4. Normal CI uses a deterministic fake provider and requires no API key.
5. Audit context is deterministically built from canonical contract/rule/retrieval artifacts.
6. The model cannot cite arbitrary contract or Legal Evidence IDs without validation failure.
7. `as_of`, version and corpus-coverage uncertainty propagate into findings.
8. Prompt-injection-like contract text is covered by regression tests.
9. Validated results persist locally as `ai-audit.json`.
10. Minimal API and UI inspection work.
11. Missing/invalid provider configuration is explicit.
12. No second reviewer model or Agent is introduced.
13. All Stage 1–7 backend regressions pass.
14. Frontend production build/typecheck remains green.
15. README documents the real behavior and limitations.
16. CI remains green.

## Completion rule

Do not change this file to Stage 9 until every Stage 8 acceptance criterion is actually verified.

When Stage 8 is complete, the next task becomes **Stage 9 — Constrained Agent and Secondary Review**, where bounded adaptive actions and a second reviewer model may be introduced without surrendering control of the mandatory audit pipeline.
