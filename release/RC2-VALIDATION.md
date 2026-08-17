# Law-Rag 0.8.0-rc2 validation

This file defines the final Stage 12F portable Windows RC2 acceptance boundary.

The clean Windows runner must build the current `main` source into the deterministic onedir ZIP and validate the **extracted final ZIP**, not only the pre-archive folder. The ZIP must also contain the RC2-updated `README-WINDOWS.md`; release documentation and executable behavior are treated as one acceptance surface.

Required checks:

- Windows Credential Manager synthetic secret write/read/resolve/delete;
- no synthetic secret returned by provider configuration APIs;
- first-run setup state and explicit local-only skip persistence;
- protected `API 设置` remains reachable on both intake and batch-result surfaces;
- base runtime diagnostics and private-data scan;
- native PDF ingestion and packaged PDFium rendering;
- 64 MiB synthetic PDF ingestion, proving the packaged path is above the retired 50 MiB ceiling;
- persistent batch creation and two independent Job registrations;
- packaged `/results?batch=...` SPA route;
- one provider-free background pipeline reaches `WAITING_CONFIGURATION` without a paid provider call;
- simulated interrupted `RUNNING` state is reconciled on restart to `APPLICATION_RESTARTED_RETRY_REQUIRED`;
- explicit retry resumes safely and stops again at the missing-provider boundary;
- provider setup completion and latest useful batch survive process restart;
- creating an empty batch cannot hide the previous useful batch;
- batch/result reads do not create phantom Job directories;
- deterministic RC manifest/SHA validation and fresh-directory extraction smoke;
- ordinary backend regressions, public deterministic quality gates and locked frontend build remain green.

Passing this file's checklist validates packaging and product-flow mechanics. It does **not** claim real-contract legal accuracy, full statutory coverage, real-provider audit quality, or bundled OCR readiness.
