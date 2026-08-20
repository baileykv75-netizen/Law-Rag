# CURRENT_TASK.md

# Stage 15 — Official Legal Corpus Expansion + Versioning + Retrieval Tuning

## Status

```text
Stage 11A–11E   COMPLETE / validated release foundations
Stage 12A–12F   COMPLETE / RC2 VALIDATED
Stage 13A–13G   COMPLETE / ISSUE_V1 production migration validated
Stage 14.1–14.7 COMPLETE / OCR distribution + DOCX + packaged Windows validation

Stage 15        IN PROGRESS
                 15.1 Corpus Pack architecture COMPLETE
                 15.2 three-domain official corpus NEXT
                 15.3 corpus update + version management PENDING
                 15.4 domain-aware RAG PENDING
                 15.5 Windows baseline corpus packaging + final regression PENDING
```

Stage 13 audit topology and Stage 14 source/distribution architecture are closed. Stage 15 may improve legal corpus coverage, legal-version management and retrieval quality, but must not silently change the proven `ISSUE_V1` reasoning topology or the Stage 14 input/OCR boundary.

## Production baseline

```text
Source file
 -> Source Evidence
 -> Canonical Contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> issue-based Legal RAG
 -> one bounded DeepSeek primary request per AuditPlan Issue
 -> one bounded Kimi finding + coverage review per AuditPlan Issue
 -> deterministic Issue comparison
 -> append-only Issue human review
 -> architecture-aware Results / Workspace / Developer
```

Historical completed RC2 jobs remain readable as `LEGACY_RC2`; provenance conflicts fail closed as `CONFLICT`.

## Stage 14 — COMPLETE

Stage 14 delivered cross-format PDF/image/DOCX Evidence, local fixed Paddle OCR runtime/models, DOCX Pipeline integration and validated Windows onedir/portable RC distribution. Do not reopen that architecture in Stage 15 without new evidence.

Authoritative Stage 14 packaged Windows validation: `32245812422`.
Final Stage 14 closeout CI: Law-Rag CI #757 (`32249531744`) — SUCCESS.

## Stage 15 plan

Stage 15 is intentionally limited to five slices.

### 15.1 — Corpus Pack architecture — COMPLETE

Implemented on `stage15-1-corpus-pack-architecture`:

- canonical legal identity remains `Authority -> Version -> Article / Legal Evidence`;
- Corpus Pack is a grouping/distribution layer, not a second legal identity;
- pack membership is many-to-many, so one Authority/Version may belong to several domains without duplicating source text;
- `domain_tags` are open validated lowercase slugs, not a closed Python enum;
- pack authority references are corpus-root-relative POSIX paths and fail closed on absolute/traversal/backslash paths;
- duplicate authority/version identity inside one pack is rejected;
- `DRAFT` packs may be structurally defined before content exists; `READY` packs require at least one authority manifest;
- existing Stage 6 `LegalManifest` and `legal_data/seed/manifest.json` remain valid without DB/schema migration;
- no `legal.db` schema or retrieval behavior changed in 15.1.

Checked-in DRAFT pack skeletons:

```text
cn-intellectual-property-core
cn-enterprise-compliance-core
cn-labor-dispute-core
```

These skeletons do **not** claim legal coverage. Official authorities are populated only in 15.2.

### 15.1 validation

Law-Rag CI #758 (`32322954275`):

```text
backend pytest                      329 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

The new regression verifies future-domain extensibility, safe pack paths, READY/DRAFT semantics, many-to-many shared Authority/Version membership, duplicate identity rejection and legacy Stage 6 seed rebuild compatibility.

The remaining warning is the existing Starlette TestClient/httpx deprecation warning.

## 15.2 — NEXT: three-domain official corpus

Populate the first production Corpus Packs using authoritative public sources only:

```text
知识产权       cn-intellectual-property-core
企业合规       cn-enterprise-compliance-core
劳动用工与争议 cn-labor-dispute-core
```

15.2 must:

1. define an authoritative source registry suitable for the actual official domains used by these three packs;
2. add verified official Authority/Version source snapshots/manifests with URL, effective metadata, article count and SHA-256;
3. avoid duplicating shared laws across packs — shared Authority/Version manifests are referenced by multiple packs;
4. distinguish normative legal sources from reference-only material such as example contracts/cases;
5. keep incomplete coverage explicit and avoid claiming that absence from the selected corpus means no applicable law exists;
6. add deterministic import/identity tests before marking any pack READY.

Do not start update delivery, domain-aware retrieval or Windows corpus packaging in 15.2.

## Remaining Stage 15 boundaries

### 15.3 — Corpus update + version management

Preserve historical versions; detect additions/amendments/repeals deterministically; maintain a corpus version independent of the Law-Rag app version.

### 15.4 — Domain-aware RAG

```text
AuditPlan Issue
 -> domain / eligible Corpus Packs
 -> applicable Authority Version
 -> Exact Citation + BM25 + local BGE
 -> deterministic fusion
```

Expanded corpus must be benchmarked so more data does not silently reduce retrieval quality.

### 15.5 — Windows baseline corpus packaging + final regression

Ship a verified baseline snapshot of the three READY packs with the Windows product so legal retrieval works offline immediately, while preserving an independent future corpus-update path.

## Deferred after Stage 15

```text
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 15.1 is complete. Stage 15.2 — three-domain official corpus — is the only next implementation scope.**
