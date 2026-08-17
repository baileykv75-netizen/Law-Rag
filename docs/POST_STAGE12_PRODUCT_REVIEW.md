# Post-Stage-12 End-to-End Product Review

## Review scope

This review follows the normal Windows user path from launching the portable application through evidence-level human review. It separates **workflow/packaging validation** from **legal-quality readiness**. Passing RC2 means the software path is mechanically coherent and recoverable; it does not establish production legal accuracy.

## Current normal-user flow

```text
Law-Rag.exe
  -> local FastAPI + bundled React UI on 127.0.0.1
  -> first-run DeepSeek / Kimi setup or explicit local-only skip
  -> drag/drop one or more PDF/JPG/PNG files
  -> 500 MiB guarded streamed local intake
  -> persistent batch + independent Job IDs
  -> bounded background scheduler
       -> OCR only when required and available
       -> canonical contract
       -> deterministic rules
       -> versioned legal retrieval/context
       -> DeepSeek primary review
       -> Kimi independent secondary review
       -> deterministic comparison
       -> bounded local Agent evidence follow-up
       -> review-report.json
  -> persistent batch result landing
       -> human-review / material-disagreement / serious-risk priority
  -> detailed /workspace evidence review
       -> source page / Contract Evidence / Legal Evidence
       -> separate DeepSeek + Kimi opinions
       -> deterministic comparison / Agent trace
       -> append-only human decision history
```

Restart behavior is fail-closed: a prior-process `QUEUED`, `WAITING_WORKER`, or `RUNNING` pipeline cannot truthfully still be active after the process exits. On the next desktop launch it becomes `APPLICATION_RESTARTED_RETRY_REQUIRED`; no provider work auto-resumes, and the user must explicitly continue/retry. Completed artifacts are preserved for reuse.

## What is now coherent

### Desktop/product flow

- Normal users see provider setup, intake, progress, results and detailed review rather than internal Stage controls.
- Manual development controls remain available under `/developer` without dominating the product surface.
- API keys are protected with Windows Credential Manager and never returned to the browser.
- Batch intake supports independent failure/retry semantics and a 500 MiB exact per-file ceiling.
- Background execution has explicit fixed resource limits instead of unbounded OCR/provider fan-out.
- Progress is derived from actual upload bytes and persisted stage state.
- Batch summaries rebuild from canonical Job artifacts rather than persisting a second copy of legal conclusions.
- The latest useful batch survives browser/application restart; empty batches cannot hide it.
- Interrupted work is visible and explicitly resumable without hidden provider calls.
- Detailed evidence/human-review semantics from Stage 10 remain intact.

### Release mechanics

RC2 is a reproducible portable Windows x64 onedir ZIP with:

- exact Python release lock;
- locked frontend build;
- bundled public legal + lexical retrieval databases;
- machine-readable release metadata;
- third-party notices;
- private-data scan;
- package diagnostics;
- final ZIP SHA/manifest;
- fresh-directory extraction smoke;
- packaged Credential Manager, >50 MiB upload, batch persistence, provider-boundary and restart/retry smoke.

## Remaining gaps

The gaps below are ordered by impact on the user's stated law-firm/contract-audit use case, not by implementation convenience.

## P0 — Required before serious law-firm production reliance

### P0-1 — OCR is not bundled in the base RC

**Current state:** PDF/JPG/PNG intake accepts image/scanned material, but the base portable RC intentionally does not bundle PaddlePaddle/PaddleOCR or OCR weights. OCR-required Jobs stop at `WAITING_OPTIONAL_COMPONENT` rather than silently auditing unusable text.

**Why this matters:** scanned contracts and photographed contract pages are common in the intended use case. A zero-setup native-text PDF path alone is insufficient.

**Recommended next work:** create a separately validated OCR-enabled Windows distribution or optional OCR pack, define weight/cache/download/offline behavior, then benchmark Chinese scan quality using public/synthetic + private expert-reviewed samples.

### P0-2 — Bundled legal corpus is far too small for general contract review

**Current state:** the verified public base bundle contains only 2 authorities / 2 versions / 15 selected articles and explicitly marks them `CURATED_EXCERPT`.

**Why this matters:** architecture and provenance are strong, but a no-hit result on this corpus says almost nothing about whether relevant Chinese law exists.

**Recommended next work:** expand official laws, administrative regulations, judicial interpretations and version history through the existing manifest/import/version model; add update/coverage reporting without weakening provenance.

### P0-3 — Real legal audit quality has not been established

**Current state:** public evaluation proves framework behavior and retrieval mechanics on small public/synthetic cases. It is not an expert-labeled real-contract accuracy benchmark.

**Why this matters:** packaging success and model agreement cannot establish legal reliability.

**Recommended next work:** build a private/de-identified expert benchmark using the existing Stage 11 schema, including OCR, structure, Evidence localization, citation validity, finding precision/recall/F1, high-risk recall, secondary omission detection and human-review integrity. Report task-level metrics only; never one vague “legal accuracy” number.

### P0-4 — No explicit cancel/pause before provider transmission

**Current state:** when providers are configured, a successfully uploaded Job automatically proceeds through the background pipeline. The UI discloses that bounded evidence will be sent to DeepSeek/Kimi, but there is no cancel/pause state machine yet.

**Why this matters:** an accidental upload can move toward external provider transmission. For sensitive law-firm use, disclosure alone is weaker than explicit operational control.

**Recommended next work:** add a per-batch cloud-processing control and application-owned pause/cancel semantics, especially a deterministic provider-boundary gate. Cancellation must be state-machine work, not best-effort thread killing.

## P1 — High-value desktop/privacy/operational gaps

### P1-1 — No graceful quit / tray lifecycle

The console is intentionally hidden, but closing the browser does not stop the backend. RC2 currently requires Task Manager (or an existing command-line process) to terminate Law-Rag completely.

**Recommendation:** add a Windows tray icon or explicit authenticated loopback-only `Exit Law-Rag` desktop action with clean shutdown. This is more valuable than an installer right now.

### P1-2 — No full batch history / storage management

Only the latest useful batch has a normal recovery shortcut. With files up to 500 MiB, `runtime/` can grow quickly.

**Recommendation:** add batch history, created date, disk usage, archive/delete actions, and explicit confirmation. Never auto-delete contract/evidence history as “cleanup”.

### P1-3 — Contract/runtime files are plaintext at rest

API keys are protected, but uploaded contracts and audit artifacts are ordinary local files under `runtime/`.

**Recommendation:** for personal/internal evaluation, document Windows account/device encryption requirements (for example BitLocker policy). Before broader law-firm deployment, decide whether app-level encryption is required and design key recovery/rotation intentionally rather than adding ad-hoc encryption.

### P1-4 — No DOCX intake

Law firms frequently receive editable Word contracts. Current normal intake supports PDF/JPG/PNG only.

**Recommendation:** add a deterministic DOCX parser preserving paragraphs/tables/source locations before considering conversion through Office automation.

### P1-5 — No professional report/export deliverable

The workstation is strong for interactive review, but there is no polished PDF/DOCX audit report or annotated client deliverable.

**Recommendation:** export only persisted validated findings/Evidence/human decisions; do not add a new LLM synthesis layer just to make a report.

## P2 — Useful later, not blockers for the current personal RC

- code signing / SmartScreen reputation / enterprise deployment;
- installer and auto-update policy;
- bundled semantic BGE stack (Exact + BM25 currently remains a legitimate fallback);
- advanced provider model/base-URL UI for future provider changes;
- batch-level token/usage/cost visibility and optional budget guard;
- better downstream disk/RAM estimation for unusually large OCR/render workloads;
- broader documentation cleanup, including synchronizing older top-level README sections with the Stage 12 normal-user flow;
- explicit opt-in real-provider end-to-end UAT checklist (normal CI should remain provider-free).

## Recommended next roadmap

Do **not** prioritize an installer next. The current portable ZIP already proves distribution mechanics. The highest-value roadmap is:

```text
Stage 13A  OCR distribution + scan reliability
Stage 13B  legal corpus expansion + update/coverage workflow
Stage 13C  private expert benchmark / real legal quality gates
Stage 13D  provider-boundary pause/cancel + explicit cloud-processing control
Stage 13E  desktop operations: tray/quit + history/storage manager
Stage 13F  DOCX + validated report export
```

If only one item is selected next, choose **OCR distribution + scan reliability**, because it is the clearest mismatch between the current base RC and real-world scanned/image contract intake.

## Overall assessment

For **native-text PDFs and personal/local evaluation**, the product flow is now coherent: protected first-run provider setup, simple multi-file intake, guarded storage, bounded background processing, persistent batch results, evidence-first detailed review, human decision history and fail-closed restart/retry behavior all connect cleanly.

The primary remaining risk is no longer the Windows shell or the basic UI. It is **coverage and trustworthiness of the legal analysis inputs/measurement**: OCR coverage, legal corpus breadth and expert-validated audit quality, followed by stronger cloud-transmission control and desktop data lifecycle management.
