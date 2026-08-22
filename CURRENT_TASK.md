# Law-Rag — Current Delivery State

## Status

```text
Stage 11–15     COMPLETE / benchmark, ISSUE_V1 production, OCR/DOCX Windows release, three-domain corpus
Stage 16.1–16.5 ENGINEERING COMPLETE / evaluation, expert/UAT capture mechanics, release evidence matrix
Stage 16 external acceptance
                PENDING / PRIVATE_EXPERT + REAL_PROVIDER_UAT intentionally deferred to final acceptance
Stage 17.1–17.4 COMPLETE / tray, graceful quit, history, safe storage cleanup, packaged Windows validation
Stage 18.1      COMPLETE / truthful Windows EFS Job-private runtime encryption
Stage 18.2      COMPLETE / authoritative local DOCX/PDF ISSUE_V1 audit report export
Stage 18.3      COMPLETE / truthful per-Job provider call/token/estimated-cost controls
Stage 18.4      COMPLETE / advanced non-secret provider runtime settings
Stage 18.5      COMPLETE / Windows packaged regression + exact release-lock closeout
Stage 19        PENDING / installer, signing semantics, safe updates, final documentation/package
Final acceptance PENDING / private expert evidence + explicit paid/network provider UAT + complete-evidence gate
```

The user explicitly requires real DeepSeek/Kimi paid/network UAT to run only at the final acceptance boundary after Stage 19 engineering. Missing external evidence must remain visible as `PENDING`; it must never be fabricated or relabeled as completed evidence.

## Authoritative production architecture

```text
PDF / JPG / JPEG / PNG / DOCX
 -> Source Evidence
 -> Canonical Contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> deterministic Issue domain route
 -> READY Corpus Pack eligibility
 -> applicable Authority Version for as_of
 -> Exact Citation + FTS5/BM25 + optional local BGE
 -> deterministic retrieval fusion
 -> one bounded DeepSeek primary request per AuditPlan Issue
 -> one bounded Kimi finding + coverage review per Issue
 -> deterministic Issue comparison
 -> append-only human review
 -> architecture-aware Results / Workspace / Developer
 -> local authoritative DOCX/PDF export
```

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

Do not introduce a third-model vote, unrestricted browsing, arbitrary agent shell/filesystem access, cloud OCR as the default path, or a second contract-analysis pipeline.

## Frozen legal baseline

```text
Corpus Release  three-domain-core@1.0.0
READY Packs     3
Authorities     14
Versions        15
Unique Articles 1274
```

Stage 15 closeout:

```text
head                              2ea5b936723133ddf5eb8829534c0e1530c60f85
Law-Rag Stage 15 CI #123          32456205510 SUCCESS
Stage 15.5 Windows Baseline CI #9 32456205586 SUCCESS
```

## Stage 16 evidence boundary

Stage 16 keeps these evidence classes separate:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

Provider-free engineering is complete. Current evidence matrix intentionally remains:

```text
engineering_ready         true
stage16_evidence_complete false
PUBLIC_REGRESSION         PASS
PRIVATE_EXPERT            PENDING
REAL_PROVIDER_UAT         PENDING
```

No `overall_accuracy` or `legal_accuracy` claim is permitted.

## Stage 17 — COMPLETE

Frozen packaged-Windows head:

```text
1f0dc470ba6813563e8c6875a56701048a3d241e
```

Validation:

```text
Law-Rag Stage 17.4 Windows Validation #1
run 32467443733
SUCCESS
```

The actual frozen `Law-Rag.exe` and the extracted deterministic portable RC both passed:

- frozen three-domain legal baseline;
- PDF/OCR/HTTP/privacy regressions;
- system-tray dependency/lifecycle checks;
- persistent history and storage visibility;
- explicit UUID-confirmed safe Job deletion;
- `runtime/legal` hash preservation;
- batch/latest repair;
- cleanup tombstone crash/restart recovery;
- prior Stage 12–14 packaged regressions.

## Stage 18.1 — COMPLETE

Branch:

```text
stage18-1-runtime-encryption
```

Draft PR #24 is a stacked validation carrier and must remain unmerged without separate authorization.

Frozen head:

```text
b4a91e636a8efe71bbb6ef634f19db1697395187
```

Implementation:

```text
managed Job-private roots:
  jobs / uploads / rendered / batches / cleanup / exports

shared runtime/legal:
  explicitly NOT managed by the EFS layer

policy:
  OFF / AUTO / REQUIRED
```

AUTO truthfully enables Windows EFS where supported and reports `UNSUPPORTED`/`DEGRADED` otherwise. REQUIRED fails closed before the local server is exposed if protection cannot be verified. Symlink traversal is rejected. API keys remain separately protected by Windows Credential Manager.

Validation:

```text
Law-Rag Stage 18 CI #3
run 32468642381
SUCCESS
backend 497 passed, 5 skipped
frontend PASS
```

## Stage 18.2 — COMPLETE

Branch:

```text
stage18-2-report-export
```

Draft PR #25 is a stacked validation carrier and must remain unmerged without separate authorization.

Frozen head:

```text
ab40e603e3a433aa34c7185e4827e2cc8f0cd1b8
```

Authoritative report pipeline:

```text
validated ISSUE_V1 Workspace
 + Canonical Contract / Contract Evidence
 + AuditPlan
 + Issue Legal Context
 + DeepSeek primary artifact
 + Kimi secondary artifact
 + deterministic Issue comparison
 + latest append-only Human Review decision
 -> AuditReportDocument
 -> DOCX / PDF
```

Key guarantees:

- export invokes no OCR, retrieval, DeepSeek, Kimi, or other provider;
- DOCX and PDF consume the same validated report model;
- duplicate, missing, or extra Issue identities fail closed;
- only `COMPLETE` or `HUMAN_REVIEW_REQUIRED` ISSUE_V1 states are exportable;
- outstanding mandatory human review remains explicitly visible in the UI and report;
- report preserves Contract Evidence and legal Authority/Version/Article traceability;
- report content gets a deterministic fingerprint and each output gets SHA-256;
- generated files live under `runtime/exports/<job_id>`;
- export paths reject symlinks;
- `exports/<job_id>` participates in the existing crash-recoverable Job cleanup transaction;
- shared `runtime/legal` remains outside Job cleanup.

Final validation:

```text
Law-Rag Stage 18 CI #25
run 32470517835
SUCCESS
backend 505 passed, 5 skipped, 1 third-party warning
frontend PASS
Stage 16 public gates/regression/suite PASS
release evidence matrix PASS
runtime encryption truthfulness PASS
```

Detailed design:

```text
docs/STAGE18_REPORT_EXPORT.md
```

## Stage 18.3 — COMPLETE

Branch:

```text
stage18-3-cost-resource-controls
```

Draft PR #26 is a stacked validation carrier and must remain unmerged without separate authorization.

Frozen head:

```text
46696119d2d5b31d8521aaa8b04f86280cce5f14
```

Resource control model:

```text
existing provider approval / LOCAL_ONLY / cancellation gate
 -> per-Job Stage 18.3 budget gate
 -> durable provider-call ledger reservation
 -> bounded DeepSeek/Kimi request
 -> provider return
 -> existing Stage 13E/F validation + checkpoint
 -> ledger/checkpoint usage reconciliation
```

Key guarantees:

- no budget configured means existing provider behavior is unchanged;
- `max_provider_calls` is a hard pre-request per-Job limit;
- provider calls rejected by `LOCAL_ONLY`, missing approval, cancellation, or an exhausted budget consume no new call slot;
- `max_total_tokens` is truthfully a continuation limit based on provider-reported usage, not a fabricated pre-request token guarantee;
- unknown token usage under a token limit blocks later provider calls instead of being counted as zero;
- `max_estimated_cost` uses only user-configured provider prices plus provider-reported prompt/completion tokens;
- no DeepSeek/Kimi vendor price is hardcoded or fetched and the displayed number is not represented as an invoice;
- missing price/usage under an enabled cost limit fails closed for later calls;
- live requests are durably recorded before the external boundary and crash-surviving pending calls remain visible/conservative;
- existing Primary/Secondary checkpoints reconcile usage without double-counting resumed/reused Issue calls;
- historical opaque checkpoint hash identifiers are deterministically SHA-256-derived only when imported; live ledger checkpoint fingerprints remain strict 64-character lowercase SHA-256 values;
- local GET/PUT budget APIs never trigger provider work;
- `resource-budget.json` and Job-directory symlink traversal fail closed;
- Issue V1 Workspace shows calls, known tokens, estimated cost, unknown usage and remaining configured allowances;
- Workspace budget editing defaults to unlimited/blank and explicitly labels prices as user estimates.

Final validation:

```text
Law-Rag Stage 18 CI #66
run 32549341109
SUCCESS
frontend PASS
backend PASS
Stage 16 public gates/regression/suite PASS
release evidence matrix PASS
runtime encryption truthfulness PASS
```

Implementation-bearing CI #50 (`32549130409`) recorded `519 passed, 5 skipped, 1 third-party warning` before status-only closeout commits.

Detailed design:

```text
docs/STAGE18_RESOURCE_BUDGET.md
```

No paid/network DeepSeek or Kimi call was executed by Stage 18.3 engineering or CI.

## Stage 18.4 — COMPLETE

Branch:

```text
stage18-4-advanced-provider-settings
```

Draft PR #27 is a stacked validation carrier and must remain unmerged without separate authorization.

Validated implementation head:

```text
ab00a6f2810d3c40e4a30aae6870d05c5ed13192
```

Runtime configuration boundary:

```text
API Key
 -> development environment secret OR Windows Credential Manager

non-secret provider runtime options
 -> runtime/config/provider-runtime.json
 -> model / API root / request timeout / connect timeout / bounded HTTP attempts / retry backoff
```

Key guarantees:

- DeepSeek remains the Stage 13E Issue V1 primary provider and Kimi remains the Stage 13F independent Issue/coverage reviewer;
- no generic arbitrary-provider execution surface was introduced;
- API keys never enter `provider-runtime.json`, Job artifacts, browser storage, logs or reports;
- runtime precedence is explicit: SAVED > legacy model/base-URL environment compatibility > DEFAULT;
- newly saved model identities must come from the server-reported provider-specific supported list;
- provider endpoints require HTTPS except loopback-only HTTP for local development;
- embedded credentials, query strings, fragments and direct `/chat/completions` paths are rejected;
- a custom endpoint requires explicit user confirmation because it becomes the receiver of bounded contract/legal evidence;
- request timeout, connect timeout, HTTP attempts and retry backoff are bounded;
- Stage 18.3 call accounting remains one logical Issue-level provider execution; transient HTTP retries are not misreported as multiple logical budget calls;
- prompt text, evidence scope, output schema, provider roles and application-owned max output-token ceilings are not user-editable;
- Stage 13E/13F production adapters plus legacy Stage 8/9 compatibility adapters resolve from the same runtime source;
- GET/PUT/DELETE runtime settings operations are local-only and never test a provider;
- explicit connection testing remains a separate opt-in network action with fixed non-contract probe text;
- the API Settings UI displays the actual resolved model, endpoint and runtime source beside the API Key controls;
- after advanced settings save/reset, the parent Provider overview refreshes immediately so the displayed endpoint equals the endpoint used by the next explicit connection test;
- symlinked runtime configuration fails closed;
- persisted configuration is complete for both providers and fingerprint-validated using canonical Pydantic JSON.

Implementation validation:

```text
Law-Rag Stage 18 CI #96
run 32550053935
SUCCESS
backend 541 passed, 5 skipped, 1 third-party warning
frontend PASS
Stage 16 public deterministic quality gates PASS
Stage 16.2 public regression 10/10 PASS
Stage 16b evaluation suite 3/3 PASS
release evidence matrix engineering_ready=true
runtime encryption truthfulness PASS
```

Detailed design:

```text
docs/STAGE18_PROVIDER_SETTINGS.md
```

No paid/network DeepSeek or Kimi call was executed by Stage 18.4 engineering or CI.

## Stage 18.5 — COMPLETE

Branch:

```text
stage18-5-windows-release-lock
```

Draft PR #28 is a stacked validation carrier and must remain unmerged without separate authorization.

Validated release-lock implementation head:

```text
8512c13e1c7efafd0975ec85b1f4d4ee6d2f6a25
```

Release-lock scope:

```text
exact Windows CPython 3.12.10 dependency lock
 -> frozen onedir Law-Rag.exe build
 -> Stage 15.5 corpus baseline
 -> packaged PDF/OCR/HTTP/privacy regression
 -> Stage 17 tray/history/storage lifecycle regression
 -> Stage 18.1 EFS truthfulness
 -> Stage 18.2 DOCX/PDF renderer dependency + runtime execution
 -> Stage 18.3 local resource-budget persistence/API
 -> Stage 18.4 provider-settings persistence/API + Credential Manager boundary
 -> deterministic portable RC ZIP + manifest
 -> extracted-RC Stage 12–14 regression
 -> extracted-RC Stage 17 + Stage 18 regression
 -> exact executable/dependency/RC evidence hashes
```

Stage 18.5 found and fixed one real Windows-only production defect in the Stage 18.2 atomic renderer path: the temporary output was reopened read-only (`rb`) before `os.fsync()`. Linux tolerated that descriptor usage, while the packaged Windows executable failed with `OSError: [Errno 9] Bad file descriptor`. The production path now reopens the temporary file as `r+b` before `fsync`, and a cross-platform regression test requires the descriptor to be writable so Linux CI can catch any future reintroduction.

No smoke assertion was weakened to hide the defect. The same authoritative DOCX/PDF renderer path is exercised in the packaged executable.

Exact implementation validation:

```text
Law-Rag Stage 18 CI #114
run 32551622588
SUCCESS
backend 543 passed, 5 skipped, 1 third-party warning
frontend PASS
Stage 16 public deterministic quality gates PASS
Stage 16.2 public regression 10/10 PASS
Stage 16b evaluation suite PASS
release evidence matrix PASS
runtime encryption truthfulness PASS

Law-Rag Stage 18.5 Windows Release Lock #4
run 32551622552
SUCCESS on exact head 8512c13e1c7efafd0975ec85b1f4d4ee6d2f6a25
```

The Windows release-lock run passed all exact packaged steps:

- exact PR-head checkout and pinned Windows release lock;
- frozen three-domain corpus baseline;
- packaged PDF/OCR/HTTP/privacy path;
- Stage 17 tray/history/storage cleanup and restart recovery;
- Stage 18.1–18.4 smoke against the frozen onedir executable;
- deterministic portable RC ZIP and manifest;
- existing Stage 12–14 regressions against the extracted RC;
- Stage 17 and Stage 18 regressions against the extracted portable RC;
- exact release-evidence recording and inspectable artifact upload.

One first attempt on the same exact head failed in the legacy extracted-RC regression window after an asynchronous pipeline artifact changed during a snapshot assertion. No code, package content, or assertion was changed in response. An unchanged rerun of the same commit passed the entire Step 12 and full workflow, while the prior release-lock candidate had also passed the same extracted-RC chain. This is retained as a non-deterministic test-timing observation rather than misclassified as a second product defect.

Stage 18.5 remained provider-free: no paid/network DeepSeek or Kimi request, no provider connectivity probe, and no private expert/contract evidence was used.

## Remaining sequence

```text
Stage 19 installer / signing semantics / safe updates / final docs/package
 -> final acceptance only then:
      real private expert evidence
      explicit paid/network DeepSeek + Kimi ISSUE_V1 UAT
      Stage16 --require-complete-evidence
      final packaged Windows acceptance smoke
```

## PR / merge boundary

All stacked Draft PRs remain validation carriers. Do not merge, retarget to `main`, mark production-ready, or publish a release without separate explicit user authorization.