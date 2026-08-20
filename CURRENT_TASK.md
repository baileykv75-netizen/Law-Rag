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
                   15.2B source targeting + deterministic freeze tooling COMPLETE;
                         exact official snapshots + hashes + manifests IN PROGRESS
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
- `DRAFT` packs may be structurally defined before content exists; `READY` packs require at least one authority manifest;
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

New deterministic regression covers official source host/role policy, future-version transition semantics, shared Authority/Version membership, current Cybersecurity Law identity, explicit labor partial-repeal blocking, unknown-pack rejection, non-official-source rejection and Stage 6 identity non-duplication.

The remaining warning is the existing Starlette TestClient/httpx deprecation warning.

### 15.2B — IN PROGRESS: official full-text snapshots + hashes + manifests

Implemented on `stage15-2b-fulltext-snapshots` so far:

- Stage 6 importer has an optional registry-aware source-validation path; legacy Stage 6 seed behavior remains unchanged when no registry is supplied;
- registry-aware imports validate source host, role and PRIMARY eligibility before database mutation;
- `app.legal.fulltext_snapshot` adds a fail-closed FULL_TEXT gate that requires contiguous article ordinals `1..N`, safe relative snapshot paths, vetted source roles and pinned normalized SHA-256;
- three checked-in snapshot-target sets map every non-blocked Authority/Version to one exact full-text source and expected article count;
- CNIPA, CAC and MOHRSS may serve as official `TEXT` carriers under explicit registry policy but may not create or replace `PRIMARY` normative provenance;
- supplemental Stage 15.2B sources are restricted to `TEXT`; a new PRIMARY source must be vetted through the Authority/Version inventory first;
- Cybersecurity Law 2025 amendment uses NPC PRIMARY provenance plus CAC full-text carriage, expected 81 articles;
- Labor Contract Law 2012 amendment uses NPC PRIMARY provenance plus MOHRSS consolidated full-text carriage, expected 98 articles;
- all 15 non-blocked Authority/Version targets are now `READY_FOR_FREEZE` at the source-selection layer;
- Labor Dispute Interpretation (I) remains outside the snapshot target sets because its paragraph-level partial repeal remains a legal-version modeling block;
- `app.legal.fulltext_snapshot_cli` freezes an already-obtained exact official UTF-8 text into normalized `snapshot.txt` + one-record Stage 6 `manifest.json`;
- the freezer is idempotent for identical normalized input and refuses to overwrite a different frozen snapshot/manifest under the same target directory;
- deterministic regression tests cover importer source policy, target completeness, supplemental TEXT restrictions, contiguous article validation, Stage 6 manifest generation and freeze idempotency;
- `docs/STAGE15_FULLTEXT_SNAPSHOTS.md` documents the trust chain and offline freeze workflow.

Current snapshot-target counts:

```text
IP pack          5 targets READY_FOR_FREEZE
Enterprise pack  6 targets READY_FOR_FREEZE
Labor pack       5 non-blocked targets READY_FOR_FREEZE
                 1 catalog entry BLOCKED and intentionally excluded

Unique non-blocked Authority/Version identities across all packs: 15
```

The shared 2025 Anti-Unfair Competition Law appears in both IP and enterprise target sets but remains one canonical Authority/Version identity.

#### Still required before 15.2B can be complete

For each of the 15 non-blocked identities:

1. obtain the exact official full-text UTF-8 source outside model/search-snippet reconstruction;
2. run the deterministic freezer and check in `snapshot.txt` + `manifest.json`;
3. verify pinned source SHA-256 and expected article count;
4. import the complete manifest set through the registry-aware Stage 6 importer;
5. repeat the import/rebuild and prove Authority/Version/Article identities remain deterministic and non-duplicated;
6. verify the 2026 Trademark Law remains `NOT_YET_EFFECTIVE` before 2027-01-01;
7. only after those checks populate Pack `authority_manifest_paths` and consider each Pack for `READY`.

No exact official full-text snapshot files have been claimed as frozen on this branch yet. Search snippets, model-reconstructed text and amendment decisions must not be substituted for the exact consolidated source bytes.

There is not yet a new authoritative full-branch CI result recorded for the current 15.2B head; do not treat the newly added regression tests as passed merely because they are checked in.

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

**Stage 15.2B remains the only implementation scope. Source targeting, source-role hardening and deterministic freeze tooling are in place; exact official snapshots, hashes, manifests, repeat-import proof and Pack READY transition are still pending.**
