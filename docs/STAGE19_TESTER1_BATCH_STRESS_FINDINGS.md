# Stage 19 tester1 batch-stress findings

Status: manual Windows batch-stress addendum for the living tester1 defect register. This file records the first 10-contract simultaneous intake run and must not be treated as legal-accuracy evidence.

## Test batch

- Build family: `0.8.0-rc3-tester1`
- Branch: `stage19-tester-license-gate`
- Test set: 10 fictional heterogeneous contracts generated for Law-Rag stress testing.
- Formats/types intentionally varied: native DOCX, native PDF, JPG photo OCR, low-quality scanned PDF, bilingual DOCX, and hybrid native+scanned PDF.
- Goal: expose queueing, OCR, persistence, provider and UI-state issues under concurrent intake.

## Observed first-run state

The first 10-contract simultaneous run did **not** fail because the source contracts were malformed. The observed states were mixed:

- `01_设备采购框架协议_原生DOCX.docx`: reached `等待下一次云端调用确认`; source warning only (`DOCX_FOOTER_PRESENT`).
- `02_SaaS订阅与数据服务协议_原生PDF.pdf`: FAILED with `Unexpected pipeline failure: AtomicWriteError.`
- `03_员工竞业限制补充协议_手机拍照版.jpg`: OCR running at the time of capture.
- `04_软件开发外包合同_原生DOCX.docx`: reached `等待下一次云端调用确认`; source warning only (`DOCX_FOOTER_PRESENT`).
- `05_商业物业租赁合同_原生PDF.pdf`: FAILED with `Unexpected pipeline failure: AtomicWriteError.`
- `06_个人信息处理与数据委托协议_双语DOCX.docx`: FAILED with `Unexpected pipeline failure: AtomicWriteError.` plus a footer source warning.
- `07_物流运输服务合同_低清扫描版.pdf`: waiting for backend/OCR processing capacity at the time of capture.
- `08_品牌特许经营协议_原生DOCX.docx`: frontend reported `无法读取后台审计状态（HTTP 422）` plus a footer source warning.
- `09_借款与连带保证合同_原生PDF.pdf`: FAILED with `Unexpected pipeline failure: AtomicWriteError.`
- `10_建设工程专业分包合同_混合PDF.pdf`: frontend reported `无法读取后台审计状态（HTTP 422）`.

Snapshot totals shown in the UI: 0/10 completed, 2 waiting/confirmation, 6 failed, with the remaining jobs processing/queued.

## F-16 — Windows concurrent pipeline persistence can fail under batch polling

- Severity: **P0/P1**
- Evidence: four unrelated contracts failed almost immediately with `AtomicWriteError` during a 10-contract concurrent run.
- Current persistence implementation (`safe_persistence.atomic_write_text`) creates a same-directory temporary file, flushes/fsyncs once, then calls `os.replace(temp_path, path)` exactly once. Any exception is immediately converted to `AtomicWriteError`; there is no retry/backoff for transient Windows sharing/permission errors.
- Current frontend polls every active job approximately every 800 ms. Ten active jobs therefore create repeated concurrent reads of persisted `pipeline.json` files while worker threads persist state transitions.
- Current pipeline has `PIPELINE_MAX_WORKERS = 4`, `LOCAL_STAGE_CONCURRENCY = 2`, `OCR_STAGE_CONCURRENCY = 1`, and `EXTERNAL_PROVIDER_CONCURRENCY = 2`, so batch operation is intentionally concurrent.
- Hypothesis requiring reproduction-level confirmation: on Windows, high-frequency readers and concurrent state transitions can transiently collide with `os.replace`/file sharing semantics. One failed replace currently escalates to a whole audit failure instead of a recoverable persistence contention.
- Impact: a valid contract can fail before legal audit begins purely because local state persistence briefly failed.
- Required next iteration:
  1. preserve atomic replace semantics;
  2. add bounded retry/backoff for transient `PermissionError` / sharing violations / retryable `OSError` around replace/fsync;
  3. serialize writes per destination path where needed;
  4. retain the underlying OS error code/message in advanced diagnostics instead of collapsing everything to `AtomicWriteError`;
  5. add Windows concurrency tests with simultaneous poll/read + repeated state writes;
  6. never mark a legal audit as terminally failed because of a single transient persistence contention.
- Status: **OPEN / newly confirmed by real batch stress**.

## F-17 — HTTP 422 while polling persisted pipeline state is likely a second symptom of persistence-state contention

- Severity: **P1**
- Evidence: two independent jobs (`08`, `10`) produced `无法读取后台审计状态（HTTP 422）` during the same batch in which four jobs produced `AtomicWriteError`.
- Backend behavior: GET `/api/documents/{job_id}/pipeline` returns 422 when `load_pipeline_report()` raises a generic `PipelineError`, including when persisted `pipeline.json` cannot be validated/read as a valid `PipelineReport`.
- Frontend behavior: one non-OK polling response is immediately converted into item state `error`; polling does not retry a transient 422/read race.
- Impact: a temporary local-state read problem is rendered as a failed contract task.
- Required next iteration:
  1. classify persisted-state read errors separately from legal/pipeline stage failures;
  2. retry transient read failures before changing the visible task to FAILED;
  3. preserve last-known-good pipeline state in the UI during a transient poll error;
  4. investigate whether 422s disappear after F-16 persistence hardening;
  5. add a deterministic concurrent read/write regression test on Windows.
- Status: **OPEN / correlated with F-16 until disproved**.

## F-18 — Source parsing warnings are visually over-prominent in batch view

- Severity: **P2**
- Evidence: DOCX items prominently display `DOCX_FOOTER_PRESENT: The document contains footer content that Stage 14.2 does not yet include in canonical contract text.`
- In this synthetic pack the footer contains only a test watermark, so this warning is not a contract failure and did not stop jobs `01` and `04` from reaching provider confirmation.
- Product risk: ordinary users can confuse a parser provenance warning with a legal or processing error. In a real contract, however, operative footer text could matter, so the warning should not simply be discarded.
- Desired UX: normal mode shows concise `检测到页脚内容，当前未纳入正文审计` with severity/impact explanation; advanced mode may show the internal code `DOCX_FOOTER_PRESENT`.
- Status: **OPEN / UX clarity**.

## Interpretation

This run is **not evidence that the 10 sample contracts are invalid or unsupported**. The heterogeneous batch successfully demonstrated that some jobs can reach provider confirmation and OCR queueing, while other unrelated jobs fail specifically around local persisted state. The failure pattern across unrelated PDF/DOCX samples strongly points to a concurrency/persistence robustness defect rather than contract-content-specific logic.

## Acceptance target for the next tester build

A rerun of the exact same 10-file pack should satisfy all of the following before batch robustness is considered improved:

1. zero terminal `AtomicWriteError` under normal concurrent intake;
2. zero one-shot polling failures promoted to task failure;
3. all source-valid jobs either progress, wait for explicit provider approval/configuration, or fail with a stage-specific reproducible reason;
4. OCR queueing remains bounded and visible rather than appearing frozen;
5. source warnings remain distinct from processing failures and legal-risk conclusions;
6. after provider robustness fixes, the batch reaches complete legal-audit results so recall/false-positive testing can finally begin.
