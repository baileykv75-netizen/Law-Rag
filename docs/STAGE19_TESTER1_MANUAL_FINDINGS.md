# Stage 19 tester1 manual findings

Status: living manual-test defect register. These findings come from real Windows tester runs and are intentionally separate from Stage 19 Final Acceptance. Public trusted release remains pending.

## Scope and rules

- Build family: `0.8.0-rc3-tester1`
- Branch: `stage19-tester-license-gate`
- Do not treat a system/task failure as a legal-risk conclusion.
- Do not erase failed jobs automatically; preserve checkpoints for diagnosis and retry.
- Do not merge or publish based on this document alone.

## Severity legend

- **P0**: blocks basic audit completion or risks incorrect trust/safety semantics.
- **P1**: major robustness / product-flow defect that materially harms testing or interpretation.
- **P2**: UX/performance defect; workflow remains usable with workaround.

## Findings

### F-01 — Results navigation can lose batch id

- Severity: P1
- Observed: global `结果` navigation went to bare `/results`, which produced `缺少批次编号。` even though a recent batch existed.
- Impact: user can believe results were lost.
- Desired: `/results` should resolve the current/recent batch or show a friendly empty state; never expose a developer-style missing-id error.
- Status: **OPEN / needs robust route-level fallback**.

### F-02 — License check blocks every full-page navigation

- Severity: P1
- Observed: returning to home/result/history repeatedly showed `正在检查本机测试许可证...`; if the local status request stalled, the page could remain there indefinitely.
- Root cause found: frontend status `fetch()` originally had no timeout and full-page navigation remounted the license gate.
- Change already attempted: session-level fast path + silent revalidation + 4s timeout.
- Desired: full blocking validation only on first launch/activation; subsequent in-session navigation should be immediate while backend API middleware remains authoritative.
- Status: **PATCHED; needs continued manual regression testing**.

### F-03 — Processing task incorrectly showed `继续 / 重试审计`

- Severity: P2
- Observed: a normal `PROCESSING · 48%` task also showed `继续 / 重试审计`.
- Impact: implies the worker has stopped when it has not.
- Desired: running tasks show progress plus pause/cancel only; retry only for FAILED; resume only for eligible paused/cancelled states.
- Status: **PATCHED; needs regression testing**.

### F-04 — Result/progress page exposes internal architecture language

- Severity: P2
- Observed examples: `ISSUE_V1 · Stage 13`, `AuditPlan Issue`, `Comparison`, `Legacy RC2`, developer-style state counters.
- Impact: page reads like an engineering console instead of a tester-facing legal-audit product.
- Desired: normal mode uses user language; internal architecture belongs in advanced mode/logs.
- Status: **OPEN**.

### F-05 — System/task failures were visually mixed with legal risks

- Severity: P1
- Observed: corrupt local jobs were counted under `优先关注`, creating the impression that a system error was the only contract risk found.
- Change already attempted: use `批次任务 / 需处理`, rename corrupt-job badge to `任务数据异常（非审计结论）`, explain that only completed jobs produce legal conclusions.
- Desired: system state and legal-risk state remain visually and statistically separate everywhere.
- Status: **PARTIALLY PATCHED; needs cleanup of orphan-job counting/removal**.

### F-06 — Orphan/corrupt local job persists after upgrade and pollutes the batch

- Severity: P1
- Observed: jobs such as `Job 1149c6fa` / earlier `Job af0e3890` displayed `本地文档元数据无法安全读取。` because persisted `document.json` / `evidence.json` could not be validated.
- Likely context: old tester build/runtime artifacts survived uninstall/reinstall as intended, but incomplete legacy job folders also survived.
- Impact: corrupt records are counted as batch jobs and repeatedly appear on result pages.
- Desired:
  - identify as an orphan/corrupt local task record, not a contract;
  - exclude it from legal-risk statistics;
  - offer `移除该任务记录` that removes only Law-Rag internal job metadata/artifacts, never the user's source file;
  - ideally quarantine incompatible legacy task records during upgrade.
- Status: **OPEN**.

### F-07 — OCR progress is too coarse and appears frozen

- Severity: P2
- Observed: a 3-page scanned PDF remains at `10%` for the entire OCR stage, then jumps to `25%` only when all pages complete.
- Current architecture: `10% ingest -> 25% OCR complete`; no persisted page-level progress.
- Impact: user cannot distinguish active OCR from a hang.
- Desired: show page-level status such as `正在识别第 2/3 页`, completed pages, elapsed time, and optional ETA.
- Status: **OPEN**.

### F-08 — OCR throughput is conservative / repeated model initialization

- Severity: P2
- Observed: short scans can feel slow.
- Current implementation details confirmed:
  - PP-OCRv6 medium detection + recognition;
  - CPU execution;
  - `enable_mkldnn=False` compatibility path;
  - `OCR_STAGE_CONCURRENCY = 1`;
  - page OCR is serial within a job;
  - provider/pipeline is lazily initialized per OCR job rather than process-wide shared engine.
- Desired follow-up:
  - process-wide reusable OCR engine after first initialization;
  - measured page-level timing;
  - adaptive OCR concurrency only after memory/CPU benchmarking;
  - do not weaken offline packaged-model guarantees.
- Status: **OPEN / performance iteration**.

### F-09 — DeepSeek Planner JSON truncated by token limit causes whole audit failure

- Severity: P0
- First observed: Planner failed with `DeepSeek Planner JSON output was truncated by the token limit.`
- Root cause found in original implementation: Planner used thinking/high reasoning with a 5000 completion-token budget; `finish_reason=length` raised immediately despite an apparent two-attempt network loop.
- Change already attempted:
  - compact recovery pass;
  - recovery `max_tokens=8000`;
  - disable thinking for compact pass;
  - cap/merge dynamic issues and bound text lengths;
  - strict schema validation.
- **New manual evidence after patch:** two separate contracts still failed with the user-facing message that Planner output was truncated **after automatic compact retry**.
- Impact: core audit cannot reach Legal RAG / DeepSeek issue review / Kimi review / final report even though OCR/structure/rules succeeded.
- Required next iteration: do not rely on one monolithic global JSON completion. Prefer architectural reduction such as bounded hierarchical/local planning with deterministic merge, smaller planner input/output contracts, per-chunk checkpoints, and/or issue batching. A larger token ceiling alone is not sufficient.
- Status: **OPEN / patch insufficient / highest-priority robustness defect**.

### F-10 — DeepSeek transient network disconnect is treated as hard audit failure too quickly

- Severity: P0/P1
- Observed: `Server disconnected without sending a response.` caused `处理失败` after only 2 network attempts.
- Current policy: `NETWORK_MAX_ATTEMPTS = 2`, ~1 second between attempts.
- Impact: an ordinary transient provider/network event becomes a failed contract audit.
- Desired:
  - classify connection reset/server disconnect/timeouts/429/5xx as recoverable provider-service errors;
  - exponential backoff with jitter and more bounded attempts;
  - preserve completed checkpoints;
  - after exhaustion, surface `外部服务暂时不可用` rather than generic audit failure;
  - allow explicit retry from the failed provider stage without rerunning OCR/structure/rules.
- Status: **OPEN**.

### F-11 — Provider success and audit success are not sufficiently separated in UI/state semantics

- Severity: P1
- Observed through F-09/F-10: API credentials can be valid while Planner still fails because of output truncation or network disconnect.
- Desired state model should distinguish at minimum:
  - credential/configuration failure;
  - transient network/provider-service failure;
  - rate limit/provider overload;
  - model output truncated;
  - model output schema invalid;
  - deterministic local processing failure;
  - complete legal-audit result.
- Status: **OPEN**.

### F-12 — Failure text still exposes provider/developer wording

- Severity: P2
- Observed: English provider exception text was shown directly in the result card (`Server disconnected without sending a response.`).
- Change already made for one token-truncation path, but coverage is incomplete.
- Desired: concise Chinese user message + optional expandable technical diagnostics in advanced mode.
- Status: **OPEN / partial**.

### F-13 — Need explicit checkpoint/resume observability

- Severity: P1
- Current backend reuses valid OCR/structure/rules/audit artifacts where possible, but UI does not clearly tell the user which stages are being reused on retry.
- Desired retry card example: `已保留 OCR、合同结构和确定性规则；将从审计规划继续`.
- Status: **OPEN**.

### F-14 — Batch statistics should exclude non-contract orphan records and separate failures from legal-risk counts

- Severity: P1
- Observed manual batches show totals such as 3 tasks with 0 completed and multiple `失败或系统异常`, including an orphan metadata job.
- Desired metrics:
  - valid contract tasks;
  - completed audits;
  - running/waiting;
  - provider/service failures;
  - local data-corruption/orphan records;
  - legal-risk summary only across COMPLETE audit results.
- Status: **OPEN**.

### F-15 — Manual diverse-sample regression suite needed

- Severity: process / P1
- Generated test pack contains 10 fictional samples covering procurement, SaaS/data, employment non-compete, software development, commercial lease, bilingual DPA, low-quality logistics scan, franchise, loan/guarantee, and hybrid native+scanned construction subcontract.
- Desired: turn representative cases into repeatable manual acceptance cases and eventually deterministic fixtures where appropriate. Do not use the expected-risk answer file as model input.
- Status: **ACTIVE TEST PLAN**.

## Current manual-test evidence snapshot (2026-08-24)

Latest observed batch contained:

- one orphan/corrupt local job with `本地文档元数据无法安全读取`;
- two valid contract jobs that both reached Planner but failed because output was still truncated after automatic compact retry;
- zero completed legal-audit results in that batch.

Therefore this batch **must not be interpreted as evidence about legal-risk recall/precision yet**. The embedded contractual risks have not reached a complete Legal RAG -> DeepSeek issue audit -> Kimi review -> comparison chain.

## Recommended next implementation order

1. **P0: redesign Planner to be bounded by construction** (chunk/local planning + deterministic/global merge or equivalent), then prove it with long/multi-risk contracts.
2. **P0/P1: robust provider retry/error classification** with exponential backoff, preserved checkpoints and user-safe failure states.
3. **P1: orphan/corrupt-job quarantine/removal and correct batch statistics**.
4. **P1: explicit resume/checkpoint UX**.
5. **P2: OCR page-level progress and measured performance improvements**.
6. **P2: remove engineering jargon from normal UI; keep it in advanced diagnostics**.
7. Re-run the diverse 10-contract pack and record: completion rate, elapsed time, OCR quality, provider retries, risk recall/false positives, and export integrity.
