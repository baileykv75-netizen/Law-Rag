# Stage 9 — Universal Secondary Review and Constrained Agent

## Purpose

Stage 9 adds a reliability-first second opinion without turning Law-Rag into an unrestricted multi-agent system.

Every contract with a valid Stage 8 primary report follows the same model-call topology:

```text
DeepSeek primary audit — one contract-level call
        ↓
validated ai-audit.json
        ↓
Kimi K3 secondary review — one contract-level call
        ↓
validated secondary-review.json
        ↓
deterministic field comparison
        ↓
agreement / minor disagreement
or material disagreement / evidence uncertainty
        ↓
maximum two local allowlisted evidence actions
        ↓
review-report.json
```

There is no per-finding Kimi call and no automatic third-model vote.

## Kimi secondary provider

Default production secondary provider:

```text
provider = kimi
model = kimi-k3
base_url = https://api.moonshot.cn/v1
credential = MOONSHOT_API_KEY
response_format = json_object
reasoning_effort = max
```

Keys remain local. The health endpoint does not make a paid/network request. Hidden `reasoning_content` is not persisted.

The secondary prompt treats the primary report, contract text, legal text, filenames and rule explanations as untrusted data. Kimi must review every supplied primary finding exactly once and may cite only supplied canonical Evidence IDs and Legal Evidence IDs.

## Validation before comparison

Kimi output is rejected before comparison if it contains, among other cases:

- an unknown primary finding ID;
- an invented contract Evidence ID;
- an invented Legal Evidence ID;
- a Legal Evidence ID outside the bounded Stage 8 context;
- a legal version not applicable on `as_of`;
- an unsupported possible omission;
- malformed structured output.

The same Stage 8 context must be reproducible. If contract/legal/retrieval artifacts changed and the context fingerprint no longer matches the primary report, Stage 9 refuses to compare old and new evidence worlds.

## Deterministic comparison engine

Natural-language reasoning summaries are not similarity-scored. Comparison uses structured fields only.

### Risk state

Primary and secondary enums are mapped through a deterministic truth table. Examples:

```text
SUPPORTED_FINDING + SUPPORTED
  -> AGREE_SUPPORTED

NO_FINDING + NOT_SUPPORTED
  -> AGREE_NO_FINDING

SUPPORTED_FINDING + NOT_SUPPORTED
  -> DISAGREE_RISK_EXISTS

SUPPORTED_FINDING + INSUFFICIENT_EVIDENCE
  -> DISAGREE_EVIDENCE_SUFFICIENCY
```

### Severity

Ordinal rank:

```text
INFO=0, LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4
```

```text
distance 0 -> AGREE
distance 1 -> MINOR_DISAGREEMENT
distance >= 2 -> MATERIAL_DISAGREEMENT
```

### Contract and legal evidence

Evidence IDs are compared as sets:

```text
same set       -> AGREE
shared subset  -> PARTIAL_OVERLAP
both nonempty, no shared IDs -> DISJOINT
one side only  -> PRIMARY_ONLY / SECONDARY_ONLY
```

Partial overlap is recorded but is not automatically a material disagreement. If both models affirm a risk but rely on completely disjoint contract evidence or completely disjoint legal authority, the comparison becomes material.

### Possible omissions

Kimi may identify a possible primary omission only from evidence already supplied in the bounded context. A validated omission becomes a material follow-up item; it does not silently become a new accepted finding.

## Overall comparison states

```text
AGREEMENT
MINOR_DISAGREEMENT
AGREEMENT_WITH_REVIEW
REQUIRES_MORE_EVIDENCE
MATERIAL_DISAGREEMENT
```

Only structured, validated fields determine these states. Kimi's own prose/disagreement labels are informative data, not the final comparison authority.

## Constrained Agent policy

The application, not a model, owns the Stage 9C state machine and action budget.

Maximum follow-up cycles:

```text
2
```

Allowlisted tool names:

```text
inspect_contract_evidence
get_clause_context
inspect_legal_evidence
retrieve_more_legal
resolve_contract_reference
request_ocr_retry
```

Arbitrary shell commands, unrestricted filesystem operations, web research, source editing, legal-store mutation and open-ended retries are not available.

### Implemented local tools

`inspect_contract_evidence`
: Returns only canonical objects/source spans for exact known Evidence IDs. Unknown IDs fail closed.

`get_clause_context`
: Requires an exact canonical clause ID; may return the target, parent, neighboring and child clauses. It does not guess a clause ID from prose.

`inspect_legal_evidence`
: Loads exact canonical Legal Evidence and rechecks the applicable legal version on `as_of`.

`retrieve_more_legal`
: Reuses the local Stage 7 retrieval system with explicit `as_of`, bounded query length and no web search/corpus mutation.

`resolve_contract_reference`
: Resolves only a reference already present in canonical contract structure.

`request_ocr_retry`
: Currently validates whether the cited evidence is OCR-derived. Actual retry execution is deliberately reported `UNAVAILABLE` until a bounded retry path is configured; the system never silently re-OCRs the whole document.

Every action records tool/version, cycle, reason, normalized arguments, input/output evidence, result state, error details and whether an external provider call/private-data transmission occurred. Current Stage 9C tools are local-only.

## State-machine policy

```text
validated primary + validated secondary
        ↓
COMPARE
        ├─ agreement -> DUAL_MODEL_AGREEMENT
        ├─ one-step severity difference -> MINOR_DISAGREEMENT
        └─ material/evidence uncertainty
                ↓
             PLAN
                ↓
        max two local actions
                ↓
        HUMAN_REVIEW_REQUIRED
```

Local tools gather evidence; they do not reinterpret or overwrite the two validated model conclusions. Without an explicit bounded re-review design, newly gathered evidence cannot magically make one model 'win'. Material unresolved disagreement therefore ends in human review.

## Runtime artifacts

```text
runtime/jobs/<job-id>/ai-audit.json
runtime/jobs/<job-id>/secondary-review.json
runtime/jobs/<job-id>/review-report.json
```

`review-report.json` contains primary/secondary metadata, validated model results, deterministic comparison, possible omissions, local Agent action trace, final state and warnings.

## API boundaries

```text
GET  /api/ai/secondary/health?provider=kimi
POST /api/documents/<job-id>/secondary-review
GET  /api/documents/<job-id>/secondary-review
POST /api/documents/<job-id>/review-report
GET  /api/documents/<job-id>/review-report
```

The first POST can make the one Kimi external call. The `review-report` POST is local-only and does not make a model call.

## UI boundary

The Stage 9 panel explicitly separates:

1. `运行 Kimi 二审（1次外部调用）`
2. `生成双模型比较报告（仅本地）`

It shows per-finding state/severity/evidence comparison, Agent action trace and final human-review state without presenting model agreement as legal correctness.

## Validation

Normal CI uses fake providers and local fixtures; it does not require API keys or spend model credits. Tests cover:

- exactly one contract-level second call even with multiple primary findings;
- complete primary-finding coverage by Kimi;
- invented/stale evidence rejection;
- prompt-injection-as-data boundary;
- state/severity/evidence-set comparison;
- possible omission handling;
- two-cycle Agent budget and forbidden tool rejection;
- local contract/legal/retrieval tools;
- explicit unavailable OCR retry;
- application-owned state machine;
- review-report persistence;
- API mounting and frontend production build.

A real Kimi smoke exists as an explicit opt-in test using configured local secrets; it is not part of ordinary CI.
