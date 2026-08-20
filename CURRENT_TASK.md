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
                 15.2 three-domain official corpus COMPLETE
                   15.2A official source registry + vetted Authority/Version inventory COMPLETE
                   15.2B official full-text snapshots + hashes + manifests COMPLETE
                         15/15 non-BLOCKED Authority/Version snapshots FROZEN
                         14 Authorities / 15 Versions / 1274 unique Articles
                         three Pack manifest sets POPULATED / READY
                 15.3 corpus update + version management COMPLETE
                       immutable Corpus Release model IMPLEMENTED
                       deterministic update planner IMPLEMENTED
                       staged legal.db rebuild + atomic replacement IMPLEMENTED
                       baseline three-domain-core@1.0.0 CHECKED IN
                       authoritative Stage 15 CI PASS: run 32359854525
                 15.4 domain-aware RAG NEXT
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

Authoritative Stage 14 packaged Windows validation: `32245812422`.
Final Stage 14 closeout CI: Law-Rag CI #757 (`32249531744`) — SUCCESS.
Do not reopen Stage 14 architecture in Stage 15 without new evidence.

## 15.1 — Corpus Pack architecture — COMPLETE

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

Corpus Pack is only a grouping/distribution layer. Membership is many-to-many, shared Authority/Version text is not duplicated, pack paths are corpus-root-relative POSIX paths, duplicate identity in one pack is rejected, and Stage 6 `LegalManifest` / `legal.db` compatibility is preserved.

Authoritative validation: Law-Rag CI #762 (`32323430473`):

```text
backend pytest                      333 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

## 15.2A — Official source registry + vetted Authority/Version inventory — COMPLETE

- `legal_data/source_registry.json` is the explicit official-source allowlist and role policy.
- NPC/National Laws Database, China Government and SPC/SPC Gazette may serve authoritative provenance under their registered roles.
- CNIPA, CAC, MOHRSS, NCAC and SAMR may serve official TEXT/METADATA/CROSS_CHECK roles where registered, but may not be silently promoted to normative PRIMARY.
- 16 catalog entries were verified on 2026-08-20; 15 are representable as complete Authority/Version snapshots.
- Labor Dispute Interpretation (I) remains `BLOCKED` because paragraph-level partial repeal cannot be safely flattened into the current version-level validity model.
- 2025 Anti-Unfair Competition Law is one shared Authority/Version for the IP and enterprise-compliance packs.
- Trademark Law has two versions: 2019 current through 2026-12-31; the 2026 revision is frozen but remains `NOT_YET_EFFECTIVE` until 2027-01-01.
- Cybersecurity Law current corpus version is the 2025-amended text effective 2026-01-01.

Authoritative validation: Law-Rag CI #765 (`32325118255`):

```text
backend pytest                      344 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
Windows exact OCR dependency smoke PASS
```

## 15.2B — COMPLETE

The first official three-domain corpus is frozen and READY.

```text
cn-intellectual-property-core    4 Authorities / 5 Versions / 350 membership Articles
cn-enterprise-compliance-core    6 Authorities / 6 Versions / 587 membership Articles
cn-labor-dispute-core            5 Authorities / 5 Versions / 378 membership Articles
```

Deduplicated union:

```text
14 Authorities
15 Versions
1274 unique Articles
14 EFFECTIVE versions
1 NOT_YET_EFFECTIVE version (Trademark Law effective-2027-01-01)
0 excerpt-only versions
```

All 15 non-BLOCKED versions have checked-in `snapshot.txt` + `manifest.json` with official provenance, expected Article count and pinned SHA-256.

Stage 15.2B validation evidence:

```text
Draft PR #11: stage15-2b-fulltext-snapshots -> stage15-2a-official-source-inventory
Stage 15 CI run #52  32356799261  SUCCESS (DRAFT candidate)
Stage 15 CI run #63  32357240734  SUCCESS (READY candidate)
Stage 15 CI run #65  32357408594  SUCCESS (post-closeout document head)
```

Draft PR #11 remains validation evidence only and is not authorized for merge.

## 15.3 — Corpus update + version management — COMPLETE

### Goal achieved

Historical legal versions are preserved and corpus changes are now deterministic, reviewable and independently versioned from the application.

Version hierarchy is explicit:

```text
Application version
  != Corpus Release version
  != Corpus Pack version
  != Authority Version
```

The canonical legal identity remains unchanged:

```text
Authority -> Version -> Article / Legal Evidence
```

### Corpus Release layer

Implemented:

```text
backend/app/legal/corpus_release.py
backend/app/legal/corpus_release_cli.py
```

A Corpus Release is an immutable publication index over already-frozen Authority/Version manifests. It pins:

- `corpus_id`, independent `corpus_version`, release date and parent corpus version;
- selected READY Pack IDs, independent `pack_version`, domain tags and manifest membership;
- canonical Authority fingerprint;
- Version lifecycle dates/status/supersession links;
- frozen snapshot SHA-256 and expected Article count;
- canonical manifest path and Pack membership;
- deterministic release digest.

It does **not** duplicate legal body text.

Release validation fails closed for unsafe paths, malformed releases, duplicate identities, invalid Pack membership, Authority metadata drift, overlapping intervals, broken supersession links, invalid effective/repeal state, summary mismatch and digest mismatch.

Unrelated future DRAFT Packs do not block an existing release. Release construction can explicitly select the READY Pack set.

### Deterministic update planner

`plan_corpus_update(current, candidate)` classifies legal-corpus changes before publication.

Safe-forward classes include:

```text
AUTHORITY_ADDED
AMENDMENT_VERSION_ADDED
EFFECTIVE_ACTIVATED
SUPERSESSION_RECORDED
REPEAL_RECORDED
PACK_ADDED
PACK_VERSION_UPDATED
PACK_MEMBERSHIP_UPDATED
```

Fail-closed classes include:

```text
VERSION_REMOVED
SNAPSHOT_MUTATED
AUTHORITY_METADATA_MUTATED
VERSION_IDENTITY_MUTATED
PACK_REMOVED
PACK_VERSION_NOT_ADVANCED
PACK_VERSION_REGRESSED
CORPUS_PARENT_MISMATCH
CORPUS_VERSION_NOT_ADVANCED
EMPTY_RELEASE_UPDATE
```

Critical invariants:

- changed legal text under an existing `(authority_id, version_id)` is forbidden; a changed legal text requires a new Version identity;
- historical Authority/Version identities may not disappear from a later release;
- lifecycle data may advance but may not be silently rewritten or regressed;
- Pack membership/domain metadata changes require an independent `pack_version` bump;
- candidate Corpus Release must name the current release as `parent_corpus_version` and advance `corpus_version`;
- a no-op release cannot be disguised as a new corpus version.

### Safe legal.db publication

`rebuild_legal_store_from_release(...)` uses the existing Stage 6 importer rather than creating a competing legal-store implementation:

```text
validated Corpus Release
 -> revalidate referenced manifest metadata + snapshot SHA/count
 -> build sibling temporary legal.db
 -> verify Authority / Version / Article totals
 -> atomic os.replace() only after complete success
```

Any failure deletes the staged DB and leaves the current target DB untouched. Stage 6 single-manifest import semantics and schema remain unchanged.

### Baseline Corpus Release

Checked in:

```text
legal_data/releases/three-domain-core/1.0.0/release.json

corpus_id       three-domain-core
corpus_version  1.0.0
released_on     2026-08-20
parent          null
Pack count      3
Authorities     14
Versions        15
Articles        1274
release_digest  4009c06967cd2281089e85bdfda64388dd4ac8fc3b86125d971bfa1c0f642b4f
```

The shared Anti-Unfair Competition Authority/Version remains one identity with two Pack memberships. Trademark Law `effective-2027-01-01` remains `NOT_YET_EFFECTIVE` in the 2026-08-20 release.

Checked-in regression requires a fresh build from the live READY Pack + manifest state to match `three-domain-core@1.0.0` exactly, including release digest.

### Update operating procedure

Documented in:

```text
docs/STAGE15_CORPUS_RELEASES.md
```

Future legal update flow is now bounded:

```text
official-source verification
 -> freeze a new Authority Version when legal text changes
 -> close/supersede/repeal prior Version lifecycle where appropriate
 -> bump affected Corpus Pack version
 -> build candidate Corpus Release
 -> deterministic update plan
 -> staged legal.db rebuild
 -> full regression / quality gates
 -> publish immutable Corpus Release
```

### Authoritative Stage 15.3 validation

Validation PR:

```text
Draft PR #12
head: stage15-3-corpus-version-management
base: stage15-2b-fulltext-snapshots
```

PR #12 is a validation carrier only. It remains Draft and is **not authorized for merge**.

Authoritative PR-triggered Stage 15 CI:

```text
Run number   75
Run ID       32359854525
Head SHA     4bedf7c5953bcd4dc4657568d7a11afd8802231e
Conclusion   SUCCESS

backend pytest                      409 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

The backend job successfully executed both full `pytest -q` and the public deterministic quality-gate profile. The frontend job successfully completed locked dependency installation and the production build.

The passing regression set includes the checked-in Corpus Release baseline, real release-driven `legal.db` rebuild at `14 Authorities / 15 Versions / 1274 Articles`, Trademark applicability transition, update planning, historical-version preservation, snapshot/identity mutation blocking, Pack-version discipline and atomic-rebuild failure safety.

**Stage 15.3 is therefore COMPLETE.**

## Remaining Stage 15 boundaries

### 15.4 — Domain-aware RAG — NEXT

Target architecture:

```text
AuditPlan Issue
 -> domain / eligible Corpus Packs
 -> applicable Authority Version
 -> Exact Citation + BM25 + local BGE
 -> deterministic fusion
```

The expanded corpus must be benchmarked so additional data does not silently reduce retrieval quality. Stage 15.4 should build on Corpus Release `three-domain-core@1.0.0`; it must not bypass Authority/Version applicability or silently change ISSUE_V1 reasoning topology.

### 15.5 — Windows baseline corpus packaging + final regression — PENDING

Ship a verified baseline Corpus Release of the READY three-domain packs with the Windows product for offline legal retrieval, while preserving the independent future corpus-update path created in 15.3.

## Deferred after Stage 15

```text
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 15.1, 15.2 and 15.3 are COMPLETE. The verified baseline is `three-domain-core@1.0.0` with 3 READY Packs, 14 canonical Authorities, 15 Versions and 1274 unique Articles. Stage 15.4 is NEXT. Draft PR #12 remains open only as Stage 15.3 validation evidence and is not authorized for merge. Do not begin Stage 15.5 and do not merge validation PRs without separate authorization.**
