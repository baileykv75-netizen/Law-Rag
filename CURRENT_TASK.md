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
Stage 18.3      NEXT / cost and resource controls
Stage 18.4      PENDING / advanced provider settings
Stage 18.5      PENDING / Windows packaged regression + exact release-lock closeout
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

Implementation/code validation head:

```text
73a3c5427c322c75df0d1a3aa26f950d1639a761
Law-Rag Stage 18 CI #21
run 32470253271
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

The final documentation/status head must also pass Stage 18 CI before it becomes the frozen Stage 18.2 baseline.

## Next engineering scope — Stage 18.3

Implement bounded cost/resource controls without changing the existing provider approval/cancellation truth model.

Required principles:

```text
no budget configured -> existing behavior unchanged
provider-call and token budgets -> deterministic per-Job limits
unknown provider usage -> never silently treated as zero
budget check -> immediately before the real provider boundary
usage record -> after a completed provider call
primary + secondary -> shared Job budget
checkpoint resume -> no double counting reused provider calls
local-only / blocked calls -> consume no provider budget
optional monetary estimate -> only from user-configured pricing, never hardcoded as provider truth
```

Reuse the existing persisted pipeline control and provider-call checkpoints. Do not create a second execution pipeline.

## Remaining sequence

```text
18.3 cost/resource controls
18.4 advanced provider settings
18.5 Windows packaged regression + exact DOCX/PDF dependency closure
 -> Stage 19 installer / signing semantics / safe updates / final docs/package
 -> final acceptance only then:
      real private expert evidence
      explicit paid/network DeepSeek + Kimi ISSUE_V1 UAT
      Stage16 --require-complete-evidence
      final packaged Windows acceptance smoke
```

## PR / merge boundary

All stacked Draft PRs remain validation carriers. Do not merge, retarget to `main`, mark production-ready, or publish a release without separate explicit user authorization.
