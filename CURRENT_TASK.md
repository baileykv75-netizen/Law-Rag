# CURRENT_TASK.md

# Stage 12 — User-facing Workflow Simplification

## Status

```text
Stage 11A  COMPLETE — versioned benchmark schema + public synthetic evaluator
Stage 11B  COMPLETE — layered metrics + deterministic public quality gates
Stage 11C  COMPLETE — runtime/startup/data-integrity hardening
Stage 11D  COMPLETE — reproducible Windows onedir bundle
Stage 11E  RC1 VALIDATED — portable distribution path proven
Stage 12A  COMPLETE — minimal intake home + multi-file queue
Stage 12B  COMPLETE — persisted automatic background pipeline
Stage 12C  COMPLETE — guarded 500 MiB streaming + bounded scheduling
Stage 12D  COMPLETE — guided providers + Windows Credential Manager
Stage 12E  COMPLETE — persistent batch result landing + recovery
Stage 12F  COMPLETE / RC2 VALIDATED — final extracted Windows ZIP passed Stage 12 user-flow smoke
```

**Stage 12 is closed. Do not start another feature stage implicitly.**

The post-stage product review is recorded in [`docs/POST_STAGE12_PRODUCT_REVIEW.md`](docs/POST_STAGE12_PRODUCT_REVIEW.md). Future work should be selected from that review according to product value rather than continuing feature accumulation automatically.

## Validated normal-user flow

```text
Law-Rag.exe
  -> first-run DeepSeek / Kimi protected setup or explicit local-only skip
  -> drag one or more PDF/JPG/PNG contracts
  -> exact 500 MiB guarded streamed local intake
  -> persistent batch + independent Job IDs
  -> bounded background pipeline
       -> OCR only when required/available
       -> canonical structure
       -> deterministic rules
       -> legal retrieval + DeepSeek primary
       -> Kimi secondary
       -> deterministic comparison
       -> bounded local Agent evidence follow-up
       -> review report
  -> persistent /results batch landing
  -> risk/human-review priority
  -> /workspace evidence-level detailed review
  -> append-only human decision history
```

## Stage 12 hard boundaries retained

1. The Stage 10 workstation remains the detailed evidence/review surface rather than the home page.
2. `/developer` preserves manual troubleshooting controls but is not the normal product entry.
3. Progress comes only from upload bytes and persisted pipeline state.
4. One failed file never cancels unrelated batch Jobs.
5. The 500 MiB path stays streamed to disk; no whole-file in-memory upload validation.
6. OCR/provider concurrency remains bounded.
7. API keys are never committed, bundled, returned to the browser, written to ordinary runtime JSON, or echoed by diagnostics.
8. Windows desktop secrets use Generic Credentials in Windows Credential Manager; environment variables remain a development/CI override.
9. External DeepSeek/Kimi transmission remains disclosed; no hidden provider calls.
10. Batch manifests store Job IDs/timestamps only and never duplicate contract text as a second result truth.
11. Batch priority is not a legal-validity/correctness score.
12. Restart handling fails closed: prior-process transient work requires explicit retry and never silently resumes provider calls.
13. Public/default CI remains provider-free.
14. `CURATED_EXCERPT` remains explicit; absence from the bundled corpus is never treated as absence of law.

## 12E result/recovery acceptance

Validated behavior:

- every active intake session gets a versioned local batch manifest;
- only a batch that owns a persisted Job becomes the latest useful batch, so an empty new batch cannot hide previous work;
- result summaries are rebuilt from canonical Job artifacts rather than persisted as another legal conclusion store;
- batch/result reads are non-mutating and do not create phantom Job directories;
- `/results?batch=<id>` shows complete, processing, waiting, failed and invalid Jobs;
- deterministic ordering prioritizes human-review-required cases, material disagreement/more-evidence conditions, serious/high/medium risk and possible omissions;
- no aggregate “legal accuracy” score is generated;
- complete Jobs link to `/workspace?job=<id>`;
- API settings are reachable from both intake and result surfaces;
- persisted incomplete/interrupted Jobs can be explicitly started/retried from the result page;
- latest useful batch survives application restart.

## 12F RC2 acceptance

RC2 identity:

```text
version: 0.8.0-rc2
target: Windows x64
distribution: portable PyInstaller onedir ZIP
publication_state: NOT_PUBLISHED
```

Final clean-runner validation used the **extracted final ZIP** and passed:

- Windows Credential Manager synthetic write/read/resolve/delete;
- provider configuration response secret non-leak checks;
- first-run local-only skip persistence;
- updated RC2 bundled Windows guide checks;
- private/runtime data scan of the release bundle;
- deterministic synthetic native-text PDF recognized as `NATIVE_TEXT_USABLE`;
- native PDF ingestion + packaged PDFium page rendering;
- 64 MiB synthetic PDF upload, proving the packaged path exceeds the retired 50 MiB ceiling;
- two independent Jobs registered to one persistent batch;
- packaged `/results?batch=...` route;
- provider-free automatic pipeline progressing through structure/rules and stopping at `WAITING_CONFIGURATION / DEEPSEEK_NOT_CONFIGURED` before any paid model call;
- simulated prior-process `RUNNING` state converted on restart to `APPLICATION_RESTARTED_RETRY_REQUIRED`;
- explicit retry safely returning to the missing-provider boundary;
- setup state/latest batch persistence across process restart;
- RC ZIP SHA/manifest verification and fresh-directory extraction smoke;
- backend regressions, public deterministic quality gates and locked frontend build green.

RC2 validation proves product-flow and packaging mechanics. It does **not** establish real-contract legal accuracy, comprehensive Chinese-law coverage, real-provider audit quality or zero-setup scanned-contract OCR.

## Post-Stage-12 priorities

See [`docs/POST_STAGE12_PRODUCT_REVIEW.md`](docs/POST_STAGE12_PRODUCT_REVIEW.md).

Highest-priority gaps identified there:

```text
P0-1  OCR distribution + scan reliability
P0-2  legal corpus expansion / update coverage
P0-3  private expert-labeled real legal benchmark
P0-4  explicit provider-boundary pause/cancel control

P1    tray/graceful quit, batch history/storage cleanup,
      at-rest privacy policy, DOCX intake, professional export
```

Installer work remains lower priority than those product/quality gaps.

## Current implementation boundary

**No active feature stage.**

Before editing product code again, select one post-Stage-12 priority explicitly. The recommended next item is **OCR distribution + scan reliability** because scanned/image contracts are a direct intended use case while PaddleOCR is still optional and not bundled in the base RC2.
