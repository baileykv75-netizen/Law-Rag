# CURRENT_TASK.md

# Stage 13 — Audit Architecture Refactor

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel
Stage 13B       COMPLETE — Audit Planner foundation
Stage 13C       COMPLETE — hierarchical long-contract planning + coverage
Stage 13D       COMPLETE — issue-based Legal RAG
Stage 13E       COMPLETE — DeepSeek issue-by-issue primary audit
Stage 13F       COMPLETE — Kimi finding + issue-coverage review
Stage 13G       COMPLETE — end-to-end regression + production migration
                13G.1 deterministic issue comparison/report COMPLETE
                13G.2 provider-free new-chain regression COMPLETE
                13G.3 production Pipeline migration COMPLETE
                13G.4 RC2 / Issue V1 compatibility boundary COMPLETE
                13G.5 Workspace migration COMPLETE
                13G.6 Human Review migration COMPLETE
                13G.7 Results + Home migration COMPLETE
                13G.8 Developer migration COMPLETE
                13G.9 final regression + Windows smoke COMPLETE

Stage 14       NEXT — OCR distribution + DOCX
```

Stage 13 is closed. Do not reopen Stage 13 or start later release/history work unless new evidence requires it. The next implementation task is Stage 14 only.

## Stage 13 final production architecture

New jobs use `ISSUE_V1`:

```text
canonical contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> issue-based Legal RAG
 -> DeepSeek one bounded primary request per AuditPlan Issue
 -> Kimi one bounded finding + coverage review per AuditPlan Issue
 -> deterministic Issue comparison / issue-review-report.json
 -> append-only Issue human review
 -> architecture-aware Results / Workspace / Developer
```

Historical completed RC2 jobs remain readable as `LEGACY_RC2`. New/legacy artifact conflict is fail-closed as `CONFLICT`. Explicit unfinished-RC2 migration preserves an integrity-checked legacy pipeline snapshot before switching authority.

## Stage 13G completion evidence

### Provider-free end-to-end regression

The checked-in Stage 13G regression uses fake Planner/DeepSeek/Kimi providers and forbids outbound HTTP. It proves exact ordered Issue identity across:

```text
AuditPlan
= Issue Legal Context
= Issue Primary Audit
= Issue Secondary Review
= Issue Comparison
```

It also verifies:

- planning coverage is explicit for every canonical object;
- Stage 13 reads do not recreate legacy Stage 8/9 reports;
- Workspace summary/detail are provider-free;
- Batch Results are architecture-aware and reflect fresh Human Review closure;
- stale upstream AuditPlan state invalidates the current Issue review report;
- Developer Stage 13 diagnostics are GET-only.

### Pipeline / provider controls

The production Pipeline now runs:

```text
INGEST 10
OCR 25
STRUCTURE 38
RULES 48
AUDIT_PLAN 58
ISSUE_LEGAL_CONTEXT 68
ISSUE_PRIMARY_AUDIT 82
ISSUE_SECONDARY_REVIEW 92
ISSUE_REVIEW_REPORT 100
```

When the provider is configured and `REQUIRE_APPROVAL` is active, the first cloud boundary occurs before the Audit Planner's first actual outbound request, after local rules at 48%. Planner, DeepSeek and Kimi calls retain per-request provider/cancel controls and per-Issue checkpoint/resume semantics.

### Human Review

Issue V1 decisions bind to `AuditPlan.issue_id` and the current `issue-review-report.json` fingerprint. Server-derived Contract/Legal Evidence snapshots are persisted with each append-only revision.

Only fresh final `CONFIRMED` or `REJECTED` revisions close mandatory review. `UNREVIEWED`, `NEEDS_MORE_REVIEW`, stale revisions and incomplete planning coverage remain outstanding.

Legacy finding/omission revisions remain readable without conversion.

### Final CI / Windows validation

Final Stage 13G code validation:

```text
backend pytest                         275 passed, 5 skipped
public deterministic quality gates    PASS
frontend production build             PASS
Windows release-bundle smoke          PASS
Windows PaddleOCR dependency smoke    PASS
Windows real local BGE semantic smoke PASS
```

The final Windows release-bundle smoke validates:

- Windows Credential Manager provider-secret round-trip;
- isolated exact-lock onedir build;
- deterministic portable RC ZIP packaging;
- `/`, `/results`, `/workspace`, `/developer` packaged routes;
- native PDF ingestion and PDFium rendering;
- private Stage 13/legacy job-artifact exclusion from the distributable;
- historical RC2 user-flow/restart compatibility;
- Stage 13 Audit Planner approval boundary plus cancel/resume using a synthetic configured key that is never approved/transmitted.

Four duplicate FastAPI Operation ID warnings discovered during final regression were traced to duplicate Audit Planner/Issue Legal Context router mounting and removed. The final backend suite has only the unrelated third-party Starlette TestClient/httpx deprecation warning.

## Global Kimi coverage-synthesis decision

**Do not add an additional global Kimi coverage-synthesis pass in Stage 13.**

Current evidence shows:

- Audit Planner explicitly covers every canonical object;
- every AuditPlan Issue is reviewed one-to-one by DeepSeek and Kimi;
- Kimi already performs per-Issue coverage review and can return `POSSIBLE_OMISSION` from supplied bounded evidence;
- incomplete planning coverage prevents review completion;
- Stage 13G regression has not demonstrated a systematic cross-Issue/global omission missed by the current topology.

Another global model call would add provider cost, latency, privacy surface and another reconciliation path without demonstrated benefit. Revisit only if later expert/benchmark evidence, especially Stage 16, shows systematic cross-Issue omissions.

## Deferred after Stage 13

```text
Stage 14  OCR distribution + DOCX
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF reports + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 13G is complete and closed. Stage 14 is NEXT.**

Do not implement Stage 14 in the same iteration that closed Stage 13G.
