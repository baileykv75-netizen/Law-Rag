# CURRENT_TASK.md

# Stage 13 — Audit Architecture Refactor

## Status

```text
Stage 11A–11E  COMPLETE / validated release foundations
Stage 12A–12F  COMPLETE / RC2 VALIDATED
Stage 13A       COMPLETE — provider boundary + pause/cancel control validated
Stage 13B       COMPLETE — Audit Planner foundation validated
Stage 13C       COMPLETE — hierarchical long-contract planning + explicit coverage validated
Stage 13D       COMPLETE — issue-based Legal RAG validated
Stage 13E       NEXT — DeepSeek issue-by-issue primary audit
Stage 13F       PENDING — Kimi finding + coverage review
Stage 13G       PENDING — end-to-end audit architecture regression
```

Stage 13 was reordered after reviewing the old Stage 8/9 architecture. The priority is to make review scope complete, evidence-bounded and auditable before returning to desktop tray/history work.

## Stage 13A — Provider boundary + pause/cancel

**Complete and retained.**

Every Planner/DeepSeek/Kimi request must respect persisted provider policy, cancellation semantics and the atomic outbound boundary documented in [`docs/PROVIDER_BOUNDARY.md`](docs/PROVIDER_BOUNDARY.md).

## Stage 13B — Audit Planner foundation

**Complete and validated.**

`audit-plan.json` is built from:

```text
Baseline checklist
+ deterministic Stage 5 / legacy-topic hints
+ LLM dynamic planning
= validated AuditPlan
```

Key guarantees remain:

- `UNKNOWN`/`MIXED` contract types are valid conservative outcomes;
- GENERAL/type-specific baseline coverage cannot be deleted by model output;
- Planner may cite only supplied canonical object IDs;
- Evidence IDs are derived by Law-Rag, never invented by the model;
- dynamic issues require review questions and Legal-RAG queries;
- historical Stage 8 topics are hints only, not the authoritative review scope;
- Planner calls cross the Stage 13A provider boundary.

See [`docs/AUDIT_PLANNER.md`](docs/AUDIT_PLANNER.md).

## Stage 13C — Hierarchical planning for long contracts

**Complete and validated.**

Long contracts automatically use bounded local Planner passes plus one global synthesis pass. Every canonical clause/block must be reviewed in full by a valid local pass, and `audit-plan.json` records explicit coverage metadata.

```text
planning_mode = DIRECT | HIERARCHICAL
planner_passes[]
coverage[]
coverage_complete
```

`REVIEWED_NO_SPECIFIC_ISSUE` means only that the Planner saw the complete canonical object but did not bind it to a specific issue. It is not a legal conclusion.

Current application bounds:

```text
direct Planner budget             60,000 canonical text/fact chars
hierarchical chunk target         18,000 canonical text chars
max canonical objects / chunk     24
max hierarchical provider passes  256 including GLOBAL
```

No partial/truncated plan is persisted as complete.

See [`docs/HIERARCHICAL_AUDIT_PLANNING.md`](docs/HIERARCHICAL_AUDIT_PLANNING.md).

## Stage 13D — Issue-based Legal RAG

**Complete and independently validated.**

### New authoritative retrieval entry point

Legal retrieval is now driven by every validated `AuditPlanIssue`:

```text
AuditPlanIssue
 -> retrieval_query 1
 -> retrieval_query 2
 -> ...
 -> existing version-aware Stage 7 retrieval engine
 -> de-duplicated Legal Evidence
 -> issue-legal-context.json
```

The old eight Stage 8 topic rules no longer define which planned issues are eligible for the new RAG path. They may survive only as deterministic hints that helped create the AuditPlan.

### Existing Stage 7 retrieval mechanics retained

13D deliberately reuses the validated retrieval engine for:

- deterministic exact lookup;
- FTS5 trigram lexical retrieval;
- optional semantic retrieval;
- RRF fusion;
- legal-version resolution by explicit `as_of` date;
- Legal Evidence IDs;
- `CURATED_EXCERPT` coverage warnings.

No duplicate retrieval engine was introduced.

### Persisted issue legal context

Output:

```text
runtime/jobs/<job-id>/issue-legal-context.json
```

Each issue package preserves:

- issue ID/topic/priority/source provenance;
- review questions;
- contract object IDs and contract Evidence IDs;
- every retrieval query and complete `RetrievalResponse`;
- de-duplicated Legal Evidence candidates;
- query indexes that matched each Legal Evidence ID;
- exact authority/version/article metadata;
- retrieval warnings and support state.

Support states are descriptive retrieval states, not legal conclusions:

```text
EVIDENCE_FOUND
EVIDENCE_FOUND_WITH_LIMITATIONS
NO_MATCH_IN_LOCAL_CORPUS
VERSION_REVIEW_REQUIRED
```

`NO_MATCH_IN_LOCAL_CORPUS` explicitly cannot mean that no applicable legal rule exists.

### Freshness and evidence lineage

The artifact binds itself to:

```text
audit_plan_fingerprint
contract_source_fingerprint
contract_content_fingerprint
legal_source_fingerprint
retrieval_index_fingerprint
artifact_fingerprint
```

Changing the AuditPlan, legal corpus, or retrieval-index configuration makes the persisted issue legal context stale instead of silently reusing old evidence.

### Resource bound

The complete planned query set is preserved unless the build fails closed.

```text
MAX_TOTAL_RETRIEVAL_QUERIES = 2000
```

Law-Rag does not silently omit planned issues/queries to fit this bound.

### Local-only execution

Stage 13D is local-only. It does not call DeepSeek, Kimi, or another external provider. The external provider boundary remains relevant to Planner/primary/secondary model stages, not to local Legal RAG.

### API

```text
POST /api/documents/<job-id>/issue-legal-context
GET  /api/documents/<job-id>/issue-legal-context
```

POST requires an explicit legal `as_of` date. GET is read-only with freshness validation and never reruns retrieval.

### Integration repair discovered in 13D

During integration, `audit_planner_api.py` was found to exist without being mounted in the main FastAPI router. Stage 13D repaired this by mounting both the Planner and issue-legal-context routers through the existing pipeline router and added an OpenAPI regression proving both routes are reachable.

### Validation completed

Provider-free tests prove:

- a dynamic AuditPlan topic outside the historical eight-topic router can independently trigger Legal RAG;
- multiple queries can retrieve the same Legal Evidence ID and are de-duplicated without losing query provenance;
- Civil Code Article 585 remains pinned to the applicable stored version;
- contract Evidence IDs survive from AuditPlan to issue legal context;
- no-hit results are explicitly non-negative legal claims;
- historical `as_of` dates preserve `NO_APPLICABLE_VERSION` / version-review semantics;
- changing the AuditPlan invalidates old issue legal context;
- Planner and Stage 13D routes are mounted in FastAPI;
- existing Stage 7 retrieval quality gates and all backend/frontend regressions remain green.

CI run #467 passed the initial Issue-based Legal RAG integration. CI run #469 passed the strengthened legal/retrieval-index provenance checks together with backend regressions, public deterministic quality gates and frontend production build.

See [`docs/ISSUE_BASED_LEGAL_RAG.md`](docs/ISSUE_BASED_LEGAL_RAG.md).

### Legacy production path boundary

Stage 13D intentionally does **not** switch the existing Stage 8 production primary-audit path yet. The new `issue-legal-context.json` becomes authoritative input for Stage 13E. The old production path is retired only after 13E–13G validation.

## Stage 13E — DeepSeek issue-by-issue primary audit

**Status: next; implement this stage only.**

Goal:

```text
AuditPlanIssue
+ contract Evidence / related canonical context
+ Stage 13D Legal Evidence package
 -> DeepSeek primary issue audit
 -> explicit terminal issue state
```

Required terminal states should distinguish at least:

```text
SUPPORTED_FINDING
NO_MATERIAL_RISK_FOUND
INSUFFICIENT_EVIDENCE
REVIEW_REQUIRED
```

Requirements:

- every AuditPlan issue must receive one terminal primary-audit result;
- no issue may disappear merely because RAG returned zero candidates;
- `NO_MATCH_IN_LOCAL_CORPUS` cannot be converted into a confident `NO_MATERIAL_RISK_FOUND` legal conclusion without sufficient evidence;
- contract Evidence IDs and Legal Evidence IDs in model output must be validated against the supplied issue package;
- the model may not invent laws/articles/Evidence IDs;
- related clauses/global facts may be supplied deterministically without reopening the old hard-coded topic gate;
- each external DeepSeek request must cross Stage 13A provider/cancel control;
- long plans require bounded issue scheduling and observable provider usage;
- fake/provider-free regression providers remain test-only;
- do not start Kimi coverage review (13F) in the same iteration.

## Stage 13F — Kimi finding + coverage review

Pending. Kimi must review both primary findings and coverage of the complete AuditPlan.

## Stage 13G — End-to-end audit architecture regression

Pending. Validate Planner coverage, issue-based retrieval, primary audit, secondary coverage review, provider boundary, cancellation/restart semantics and packaged Windows behavior before retiring the legacy Stage 8/9 path.

## Deferred roadmap after Stage 13G

```text
Stage 14  OCR distribution + DOCX
Stage 15  official legal corpus expansion + update/versioning + retrieval tuning
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF reports + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 13D is closed.**

The next explicit implementation task is **Stage 13E DeepSeek issue-by-issue primary audit**. Do not start Stage 13F or later work in the same iteration.
