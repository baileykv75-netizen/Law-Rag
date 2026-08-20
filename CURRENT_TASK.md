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
                 15.2 three-domain official corpus IN PROGRESS
                   15.2A official source registry + vetted Authority/Version inventory COMPLETE
                   15.2B source targeting + freeze tooling COMPLETE
                         exact official snapshots + hashes + manifests IN PROGRESS
                         prc-patent-law/effective-2021-06-01 FROZEN / 82 articles
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

Stage 15 is intentionally limited to five top-level slices.

### 15.1 — Corpus Pack architecture — COMPLETE

Implemented on `stage15-1-corpus-pack-architecture`:

- canonical legal identity remains `Authority -> Version -> Article / Legal Evidence`;
- Corpus Pack is a grouping/distribution layer, not a second legal identity;
- pack membership is many-to-many, so one Authority/Version may belong to several domains without duplicating source text;
- `domain_tags` are open validated lowercase ASCII slugs, not a closed Python enum;
- pack authority references are corpus-root-relative POSIX paths and fail closed on absolute/drive-qualified/traversal/backslash paths;
- duplicate authority/version identity inside one pack is rejected;
- `DRAFT` packs may be structurally defined before content exists; `READY` packs require at least one valid authority manifest;
- existing Stage 6 `LegalManifest` and `legal_data/seed/manifest.json` remain valid without DB/schema migration;
- no `legal.db` schema or retrieval behavior changed in 15.1.

Checked-in DRAFT pack skeletons:

```text
cn-intellectual-property-core
cn-enterprise-compliance-core
cn-labor-dispute-core
```

### 15.1 validation

Authoritative code + decision head CI: Law-Rag CI #762 (`32323430473`):

```text
backend pytest                      333 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

## 15.2 — Three-domain official corpus — IN PROGRESS

Target packs:

```text
知识产权       cn-intellectual-property-core
企业合规       cn-enterprise-compliance-core
劳动用工与争议 cn-labor-dispute-core
```

15.2 must:

1. use authoritative public sources only;
2. add verified Authority/Version source snapshots/manifests with URL, effective metadata, article count and SHA-256;
3. avoid duplicating shared laws across packs;
4. distinguish normative legal sources from reference-only/cross-check material;
5. keep incomplete or partially representable coverage explicit;
6. add deterministic import/identity tests before marking any pack READY.

Do not start update delivery, domain-aware retrieval or Windows corpus packaging in 15.2.

### 15.2A — Official source registry + vetted Authority/Version inventory — COMPLETE

Implemented on `stage15-2a-official-source-inventory`:

- `legal_data/source_registry.json` defines an explicit official-source allowlist and allowed source roles;
- NPC/National Laws Database, China Government, SPC/SPC Gazette are eligible authoritative sources under explicit role policy;
- CNIPA is registered for official text/metadata cross-checking but cannot be silently promoted to PRIMARY normative source;
- `legal_data/catalog/three-domain-core.json` records 16 Authority/Version entries verified on 2026-08-20;
- 15 entries are non-blocked candidates for the full-text snapshot step;
- one entry — Labor Dispute Interpretation (I) — is explicitly `BLOCKED` because a paragraph-level partial repeal cannot be safely flattened into the current version-level validity model;
- the 2025 Anti-Unfair Competition Law is one shared Authority/Version identity assigned to both IP and enterprise-compliance packs;
- the current 2019 Trademark Law ends at 2027-01-01 and the promulgated 2026 revision is explicitly `NOT_YET_EFFECTIVE` until that date;
- the Cybersecurity Law catalog uses the 2025 amendment effective 2026-01-01 rather than treating the original 2016 text as the current 2026 version;
- amendment decisions are provenance/version evidence, not substitutes for a republished full-text snapshot when `FULL_TEXT` coverage is claimed;
- all three Corpus Packs remain `DRAFT` and empty in 15.2A.

### 15.2A validation

Authoritative code head CI: Law-Rag CI #765 (`32325118255`):

```text
backend pytest                      344 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

The remaining warning is the existing Starlette TestClient/httpx deprecation warning.

### 15.2B — IN PROGRESS: official full-text snapshots + hashes + manifests

Preparation completed on `stage15-2b-fulltext-snapshots`:

- Stage 15 registry-aware source validation is wired into the Stage 6 importer without changing legacy seed behavior;
- `FULL_TEXT` freezing validates a complete contiguous Article 1..N sequence before a manifest may claim complete coverage;
- all 15 non-blocked Authority/Version targets now have explicit `READY_FOR_FREEZE` source selection and expected article counts;
- supplemental official `TEXT` carriers are allowed only when registry-approved and can never replace/create PRIMARY provenance;
- CAC and MOHRSS are registered as TEXT/METADATA/CROSS_CHECK-only carriers for the Cybersecurity Law and Labor Contract Law respectively;
- the offline freeze command writes deterministic `snapshot.txt` + one-record Stage 6 `manifest.json`, refuses changed overwrite, and preserves the original Authority/Version identity;
- the partially repealed Labor Dispute Interpretation (I) remains outside the snapshot target sets.

Actually frozen production corpus data so far:

```text
legal_data/authorities/prc-patent-law/effective-2021-06-01/
  snapshot.txt   canonical official legal-text extraction, 82 contiguous articles
  manifest.json  FULL_TEXT, expected_article_count=82,
                 expected_source_sha256=3fd787a8394ee5af31040f5366ac696c6dae725850148699d06a9c3f725baf2d
```

The Patent Law snapshot is extracted from the complete CNIPA 2020-amended text whose page identifies China NPC as the information source. The catalog retains the NPC amendment decision as PRIMARY provenance and CNIPA as TEXT provenance.

Still required before 15.2B can be called complete:

1. freeze the remaining 14 non-blocked official Authority/Version snapshots;
2. run registry-aware import/rebuild over the actual frozen corpus;
3. repeat import and prove Authority/Version/Article identities and Legal Evidence IDs are stable;
4. confirm the 2026 Trademark Law remains `NOT_YET_EFFECTIVE` before 2027-01-01;
5. populate pack `authority_manifest_paths` only from validated frozen manifests;
6. mark packs READY only after complete pack-level deterministic validation;
7. record authoritative CI evidence for the final 15.2B head.

No source whose exact complete current text or applicability cannot be proven may be fabricated as `FULL_TEXT`.

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

**Stage 15.2B is still in progress. One of 15 non-blocked Authority/Version full-text snapshots is frozen. Continue only with exact official full-text snapshots, hashes, manifests, deterministic import validation and pack population; do not begin Stage 15.3/15.4/15.5 yet.**
