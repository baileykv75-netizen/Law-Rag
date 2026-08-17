# Law-Rag 0.8.0-rc2 — Release Candidate Notes

## Purpose

RC2 validates the simplified normal-user workflow requested after the first real Windows RC test. It remains a **release candidate for local evaluation**, not a claim of production legal accuracy or complete Chinese-law coverage.

## User-facing changes since RC1

### Simplified intake

The normal home page is now focused on:

```text
configure providers once
  -> drag one or more contracts
  -> watch real progress
  -> review batch results
  -> open detailed evidence only where needed
```

Legacy Stage-by-Stage controls remain under `/developer` for troubleshooting.

### Automatic background audit pipeline

After a successful upload, the application owns the normal processing sequence:

```text
OCR when required
 -> canonical structure
 -> deterministic rules
 -> legal retrieval + DeepSeek primary review
 -> Kimi secondary review
 -> deterministic comparison
 -> bounded Agent evidence follow-up
 -> review report
```

Polling is read-only and never triggers provider calls. Valid completed artifacts are reused during retry.

### 500 MiB streamed intake and bounded batches

- exact per-file limit: 500 MiB;
- fixed 1 MiB local write chunks;
- disk-space preflight with safety reserve;
- partial-file cleanup on upload failure;
- multiple independent Jobs per batch;
- fixed worker/resource concurrency instead of unbounded OCR/provider fan-out.

### Guided DeepSeek/Kimi setup

The Windows UI provides password-style first-run fields for DeepSeek and Kimi/Moonshot.

- secrets are saved as Generic Credentials in Windows Credential Manager;
- saved values are never returned to or repopulated in the browser;
- environment variables remain available for development/CI and take precedence;
- connection testing is explicit and sends only a fixed tiny non-contract message;
- local-only skip remains supported.

### Batch result landing

A persistent `/results?batch=<id>` page summarizes every Job in a batch and prioritizes:

- human-review-required cases;
- material model disagreement / more-evidence conditions;
- critical/high/medium findings;
- possible omissions.

This ordering is not a legal-validity or correctness score. Detailed findings still open in the existing evidence-oriented workstation.

Batch manifests store only Job IDs/timestamps and rebuild summaries from canonical Job artifacts. Empty batches do not replace the latest useful batch pointer.

### Restart/recovery behavior

Process-local background workers cannot survive an application exit. RC2 therefore fails closed:

- intentionally waiting/completed Jobs remain unchanged;
- transient `QUEUED`, `WAITING_WORKER`, or `RUNNING` states left by the previous process become explicit `APPLICATION_RESTARTED_RETRY_REQUIRED` failures;
- no external model work is silently resumed on application launch;
- the user can explicitly continue/retry from the batch results page;
- already completed artifacts remain available for reuse.

## Windows validation

The final extracted ZIP is required to pass:

- protected Credential Manager synthetic-secret round trip;
- provider-configuration non-leak checks;
- local-only onboarding persistence;
- native PDF + packaged PDFium rendering;
- a 64 MiB synthetic PDF upload, proving the packaged path exceeds the old 50 MiB limit;
- persistent two-Job batch registration;
- provider-free automatic pipeline reaching the missing-provider boundary;
- simulated interrupted-work reconciliation after process restart;
- explicit retry back to the safe provider boundary;
- `/results` recovery after restart;
- private/runtime file scan;
- deterministic RC manifest/SHA and fresh-directory extraction smoke.

Normal CI remains free of paid DeepSeek/Kimi calls.

## Important limitations still present

1. **OCR is not bundled in the base RC.** PaddleOCR/PaddlePaddle and OCR weights remain optional, so image-only/scanned contracts are not yet zero-setup.
2. **The bundled legal corpus is intentionally small.** It is a verified `CURATED_EXCERPT`, not a complete Chinese-law database. A no-hit result is never evidence that no relevant rule exists.
3. **Real legal quality is not established by the public synthetic benchmark.** Private/expert-labeled contract evaluation is still required before production reliance.
4. **No graphical storage/history cleanup yet.** Large uploaded contracts remain under the local `runtime/` tree until the user manages that data outside the app.
5. **No dedicated tray/quit control yet.** The normal console is hidden; closing the browser does not terminate the backend process.
6. **No DOCX intake or professional report export yet.** RC2 intake remains PDF/JPG/PNG and review is primarily in the local workstation.
7. **No installer/code signing/auto-update yet.** The chosen distribution remains the inspectable portable onedir ZIP.
8. **Runtime contract files are local but not application-encrypted at rest.** Deployment should rely on appropriate Windows account/device protections until a dedicated encryption policy is designed.

These limitations should drive any post-Stage-12 roadmap rather than being hidden behind the fact that the RC packages and runs successfully.
