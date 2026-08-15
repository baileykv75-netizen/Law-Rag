# CURRENT_TASK.md

# Stage 10 — Professional Audit Workstation UI

## Goal

Turn the validated Stage 1–9 pipeline into one coherent professional contract-review workspace.

Stage 10 is primarily a **review ergonomics and human-decision layer**, not another reasoning/model stage. The user should be able to open one completed job and review the source document, canonical evidence, deterministic rules, DeepSeek findings, Kimi review, model comparison, Agent action trace and legal authority without jumping between separate technical panels.

Target interaction:

```text
completed job
    ↓
┌──────────────────────────────────────────────────────────────┐
│ source document/page │ audit findings │ evidence + law      │
│                      │                │ human decision      │
└──────────────────────────────────────────────────────────────┘
    ↓
click finding/evidence
    ↓
source page and exact span/bbox highlighted
    ↓
review legal authority/version + dual-model disagreement
    ↓
human: confirm / reject / needs-more-review + note
```

Chat is secondary. The primary product surface is an evidence-linked audit workstation.

## Hard boundaries inherited from Stages 1–9

1. Do not re-run extraction, OCR, legal retrieval or models just because the workstation opens.
2. The workstation consumes persisted validated artifacts; it does not reinterpret the raw PDF with an LLM.
3. Stage 5 deterministic results remain immutable machine outputs.
4. Stage 8 DeepSeek and Stage 9 Kimi findings remain distinct records; UI may compare them but must not merge away disagreement.
5. `review-report.json` final state and Agent trace remain visible.
6. Human decisions are an additional layer; they do not rewrite source evidence or model reports.
7. Legal Evidence must show authority, article, version/effective date, source and coverage state.
8. `HUMAN_REVIEW_REQUIRED` must never be styled as a completed/approved legal result.
9. No hidden model/API call may occur from navigation, filtering, highlighting or opening a job.
10. Real/private artifacts remain local and outside Git.

## Delivery strategy

Implement in small verifiable sub-phases:

```text
10A — job workspace shell + artifact summary/loading
10B — source document/page viewer + exact Evidence navigation/highlighting
10C — unified findings/comparison/legal-evidence panels
10D — human decision schema/persistence + review controls
10E — history/filters/keyboard/accessibility polish + final regression/docs
```

Do not redesign everything in one uncontrolled rewrite.

## 10A — Workspace shell

Create a dedicated job-centric workspace route/view instead of adding more standalone cards to the existing development page.

Minimum layout should support desktop-first three-pane review:

```text
left:   source document / pages
center: audit findings + filters
right:  evidence, legal basis, comparison, human decision
```

Requirements:

- load by one `job_id`;
- show processing completeness/status across Stages 2–9;
- show filename/document kind/page count;
- show whether OCR was used and relevant source uncertainty;
- show whether primary/secondary reports exist;
- show final Stage 9 review state;
- missing artifacts produce explicit partial/incomplete states rather than blank panels;
- no external model call during workspace load.

Prefer a dedicated frontend component hierarchy rather than expanding the legacy monolithic `App.tsx`.

## 10A — Job summary API

Add one read-only aggregation endpoint if useful, for example:

```text
GET /api/documents/<job-id>/workspace
```

It may summarize available local artifacts and stable IDs, but should not duplicate entire large files unnecessarily.

No model call or OCR/retrieval mutation is allowed in this GET.

## 10B — Source viewer

The user must be able to see the original source associated with a finding.

Support at least:

- PDFs;
- JPG/JPEG/PNG source documents;
- page navigation;
- jump to page from a SourceSpan/Evidence ID;
- zoom;
- source method indicator (`native_pdf_text` / `ocr`);
- bbox/polygon highlight where coordinates exist;
- native-text page/span indication where only offsets exist.

If a new PDF/browser rendering dependency is required, verify its current license, Windows/browser suitability and bundle implications before adding it; record the decision in `docs/DECISIONS.md`.

Do not expose arbitrary local filesystem paths to the browser. Add bounded source/page endpoints when necessary.

## 10B — Evidence navigation

Clicking any of these should resolve to source evidence:

- deterministic rule result;
- DeepSeek finding;
- Kimi review;
- comparison row;
- possible omission;
- Agent action input/output evidence;
- canonical clause/fact mention;
- Legal Evidence citation.

For contract evidence, the UI should show:

- Evidence ID;
- page;
- source method;
- quote/text snippet;
- confidence if OCR-derived;
- exact bbox/polygon when available;
- canonical object(s) using it.

If an Evidence ID cannot be resolved, show an explicit integrity error instead of silently doing nothing.

## 10C — Unified finding model for presentation

Build a presentation/view model that joins persisted artifacts **without modifying them**.

For each primary finding show at least:

- primary finding title/category/state/severity;
- evidence sufficiency;
- contract Evidence IDs;
- Legal Evidence IDs;
- Kimi assessment and severity;
- deterministic comparison state;
- severity distance;
- contract-evidence overlap;
- legal-basis overlap;
- material disagreement reasons;
- Agent follow-up trace where relevant;
- final human-review requirement.

Also show validated Kimi possible omissions as separate review items; do not silently promote them to accepted primary findings.

## 10C — Filters and triage

Provide practical filters such as:

- severity;
- primary finding state;
- agreement / minor disagreement / material disagreement;
- `HUMAN_REVIEW_REQUIRED`;
- evidence sufficiency;
- OCR/source uncertainty;
- possible omission;
- deterministic rule failures/reviews.

Default view should prioritize items needing attention rather than burying them among passes.

## 10C — Legal authority panel

When a finding cites Legal Evidence, show canonical Stage 6 data:

- authority title;
- article token/number;
- exact article text;
- version ID;
- effective date / end date if any;
- source URL/provenance;
- `FULL_TEXT` / `CURATED_EXCERPT` coverage;
- `as_of` applicability.

Do not display retrieval fusion score as a legal confidence percentage.

## 10D — Human decision schema

Add a separate versioned local human-review artifact, target:

```text
runtime/jobs/<job-id>/human-review.json
```

Suggested per-item states:

```text
UNREVIEWED
CONFIRMED
REJECTED
NEEDS_MORE_REVIEW
```

Record at least:

- decision ID/schema version;
- job ID;
- target finding/omission ID;
- decision state;
- reviewer note;
- timestamp;
- referenced Evidence IDs/Legal Evidence IDs at decision time;
- review-report/context fingerprint so stale decisions can be detected;
- revision history rather than destructive overwrite.

Do not treat a human click as modifying `ai-audit.json`, `secondary-review.json`, rule results or source evidence.

## 10D — Human review APIs

Possible bounded APIs:

```text
GET  /api/documents/<job-id>/human-review
POST /api/documents/<job-id>/human-review/decisions
```

Writes affect only the local human-review artifact.

No external model call is allowed from these actions.

## 10D — Stale-decision protection

If `review-report.json` or its source fingerprints change after a human decision:

- preserve the old decision in history;
- mark it stale/outdated;
- require explicit re-review;
- do not silently carry approval to a changed audit context.

## 10E — Processing/history view

Expose a compact audit trail of local artifacts/stages:

```text
ingested
OCR/native evidence
canonical structure
deterministic rules
legal retrieval
DeepSeek primary
Kimi secondary
comparison/Agent
human decisions
```

Show only safe metadata such as timestamps/status/provider/model/fingerprints where useful. Do not expose secrets, authorization headers or arbitrary filesystem paths.

## 10E — Accessibility and ergonomics

At minimum:

- keyboard-operable finding list/page navigation;
- clear focus states;
- readable long Chinese contract text;
- resizable/usable panes on common laptop widths;
- no horizontal-layout collapse that makes evidence unreadable;
- responsive fallback for narrower screens;
- explicit loading/error/empty states;
- avoid modal overload;
- preserve selected finding/page while opening evidence details where practical.

## Test strategy

Normal CI remains local/fake-provider only.

Cover at least:

- workspace loads a complete job without any external provider call;
- workspace handles missing Stage 8/9 artifacts explicitly;
- contract Evidence ID resolves to correct page/span;
- OCR bbox highlight metadata is returned correctly;
- unknown Evidence ID fails explicitly;
- Legal Evidence detail rechecks/version-displays `as_of` metadata;
- primary finding correctly joins to its Kimi review/comparison;
- possible omissions remain distinct;
- filters produce deterministic visible sets;
- human decision create/load/history works;
- human decision cannot mutate source/model/rule artifacts;
- stale review fingerprint marks old human decision stale;
- API cannot request arbitrary filesystem paths;
- source navigation GETs never trigger a model call;
- all Stage 1–9 backend regressions remain green;
- frontend TypeScript/production build remains green.

## Out of scope

Do not add in Stage 10:

- a new reasoning model;
- a third-model vote;
- autonomous web legal research;
- automatic legal-corpus crawling;
- multi-user SaaS/auth/roles;
- cloud document storage;
- final benchmark claims;
- Windows installer/release packaging;
- automatic final legal approval;
- a full rich-text contract editor.

## Acceptance criteria

Stage 10 is complete only when all are true:

1. A dedicated job-centric professional workspace exists.
2. Workspace loading is read-only with respect to model/OCR/retrieval pipeline execution.
3. Source PDF/image can be viewed by page.
4. Contract Evidence IDs can navigate to exact page and available bbox/span metadata.
5. Unified finding view joins primary, Kimi, comparison and Agent trace without rewriting source artifacts.
6. Legal Evidence panel displays authoritative version/provenance/coverage metadata.
7. Review/triage filters work.
8. Versioned local `human-review.json` exists with revision history.
9. Human decisions support confirm/reject/needs-review and optional note.
10. Stale fingerprint/context invalidates previous decision status without deleting history.
11. Human actions cannot mutate source/model/rule/legal artifacts.
12. No hidden external model call occurs from workspace navigation/review.
13. Missing/integrity-error states are explicit.
14. Core keyboard/accessibility/responsive behavior is usable.
15. All Stage 1–9 backend regressions pass.
16. Frontend TypeScript/production build remains green.
17. README/architecture docs reflect actual Stage 10 behavior.
18. CI remains green.

## Completion rule

Do not change this file to Stage 11 until every Stage 10 acceptance criterion is verified.

When Stage 10 is complete, the next task becomes **Stage 11 — Benchmark, hardening, and Windows release**.
