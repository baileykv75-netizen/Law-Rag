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
                         authoritative Stage 15 CI PASS: run 32357240734
                 15.3 corpus update + version management IN PROGRESS
                       Corpus Release schema / builder / loader IMPLEMENTED
                       deterministic update planner IMPLEMENTED
                       staged legal.db rebuild + atomic replacement IMPLEMENTED
                       baseline three-domain-core@1.0.0 CHECKED IN
                       final authoritative PR-triggered CI PENDING
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

- Registry-aware source validation is wired into the Stage 6 importer without changing legacy seed behavior.
- FULL_TEXT freezing requires an exact contiguous Article `1..N` sequence.
- Snapshot SHA-256 is pinned over normalized UTF-8 canonical legal text.
- Supplemental official TEXT carriers must be registry-approved and cannot create/replace PRIMARY provenance.
- Changed content cannot silently overwrite an existing Authority/Version snapshot.
- Authority metadata stays stable across versions; version-specific promulgation instruments remain version provenance.

Three READY Pack totals:

```text
cn-intellectual-property-core    4 Authorities / 5 Versions / 350 membership Articles
cn-enterprise-compliance-core    6 Authorities / 6 Versions / 587 membership Articles
cn-labor-dispute-core            5 Authorities / 5 Versions / 378 membership Articles
```

Deduplicated three-Pack union:

```text
14 Authorities
15 Versions
1274 unique Articles
14 EFFECTIVE versions
1 NOT_YET_EFFECTIVE version (Trademark Law effective-2027-01-01)
0 excerpt-only versions
```

All 15 non-BLOCKED versions have checked-in `snapshot.txt` + `manifest.json` with official provenance, expected Article count and pinned SHA-256.

Authoritative validation:

```text
Draft PR #11: stage15-2b-fulltext-snapshots -> stage15-2a-official-source-inventory
Stage 15 CI run #52  32356799261  SUCCESS (DRAFT candidate)
Stage 15 CI run #63  32357240734  SUCCESS (READY candidate)
Stage 15 CI run #65  32357408594  SUCCESS (post-closeout document head)

run #63 backend pytest                 391 passed, 5 skipped, 1 warning
run #63 public deterministic gates    PASS
run #63 frontend production build     PASS
```

Draft PR #11 remains validation evidence only and is not authorized for merge.

## 15.3 — Corpus update + version management — IN PROGRESS

### Goal

Preserve historical legal versions and make corpus changes deterministic, reviewable and independently versioned from the application.

Version hierarchy:

```text
Application version
  != Corpus Release version
  != Corpus Pack version
  != Authority Version
```

Stage 15.3 does not change the canonical legal identity:

```text
Authority -> Version -> Article / Legal Evidence
```

### Implemented release layer

New modules:

```text
backend/app/legal/corpus_release.py
backend/app/legal/corpus_release_cli.py
```

A Corpus Release is an immutable publication index over already-frozen Authority/Version manifests. It pins:

- `corpus_id`, independent `corpus_version`, release date and parent corpus version;
- included READY Pack IDs + `pack_version` + domain tags + manifest membership;
- Authority fingerprint;
- Version lifecycle dates/status/supersession links;
- frozen snapshot SHA-256 and expected Article count;
- canonical manifest path and Pack membership;
- deterministic release digest.

Release validation is fail-closed for unsafe paths, empty releases, malformed versions, duplicate identities, invalid Pack membership, Authority metadata drift, overlapping intervals, broken supersession links, invalid effective/repeal state, summary mismatch and digest mismatch.

An unrelated future DRAFT Pack does not block an existing release. Release building can explicitly select the READY Pack set.

### Deterministic update planner

`plan_corpus_update(current, candidate)` classifies additions/amendments/repeals before any database publication.

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

- changed legal text under an existing `(authority_id, version_id)` is forbidden; a new legal text requires a new Version identity;
- historical Authority/Version identities may not disappear from a later release;
- lifecycle data may advance but may not be silently rewritten/regressed;
- Pack membership/domain metadata changes require an independent `pack_version` bump;
- candidate Corpus Release must name the current release as `parent_corpus_version` and advance `corpus_version`.

### Safe legal.db publication

`rebuild_legal_store_from_release(...)`:

```text
validated Corpus Release
 -> revalidate referenced manifest metadata + snapshot SHA/count
 -> build sibling temporary legal.db using existing Stage 6 importer
 -> verify Authority / Version / Article totals
 -> atomic os.replace() only after the complete rebuild succeeds
```

Any failure removes the staged DB and leaves the existing target DB untouched. Stage 6 single-manifest importer behavior and schema remain unchanged.

### Checked-in baseline Corpus Release

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

The release contains metadata/indexes only; it does not duplicate legal body text. The shared Anti-Unfair Competition Authority/Version remains one identity with two Pack memberships. Trademark Law `effective-2027-01-01` remains `NOT_YET_EFFECTIVE` in this 2026-08-20 release.

A checked-in regression rebuilds the release from the live READY Pack + manifest state and requires exact equality with `three-domain-core@1.0.0`, including the pinned release digest.

Detailed operating procedure: `docs/STAGE15_CORPUS_RELEASES.md`.

### Stage 15.3 validation status

Implementation and deterministic regression fixtures are checked into branch:

```text
stage15-3-corpus-version-management
```

Push-triggered GitHub Actions are not exposed with readable Check Run logs through the connected GitHub interface used in this session, so no authoritative green CI claim is recorded yet for Stage 15.3.

Stage 15.3 MUST remain `IN PROGRESS` until a PR-triggered Stage 15 CI run is observable and proves:

1. full backend pytest PASS;
2. public deterministic quality gates PASS;
3. frontend production build PASS;
4. checked-in `three-domain-core@1.0.0` exactly matches a fresh deterministic release build;
5. real release-driven `legal.db` rebuild remains `14 Authorities / 15 Versions / 1274 Articles` and preserves 2026-12-31 -> Trademark 2019 / 2027-01-01 -> Trademark 2027 applicability;
6. update planner regressions preserve history and block identity/hash/version regressions.

Creating or merging a Stage 15.3 PR requires separate authorization. Do not mark 15.3 COMPLETE from push status alone.

## Remaining Stage 15 boundaries

### 15.4 — Domain-aware RAG — PENDING

```text
AuditPlan Issue
 -> domain / eligible Corpus Packs
 -> applicable Authority Version
 -> Exact Citation + BM25 + local BGE
 -> deterministic fusion
```

Expanded corpus must be benchmarked so more data does not silently reduce retrieval quality.

### 15.5 — Windows baseline corpus packaging + final regression — PENDING

Ship a verified baseline Corpus Release of the READY three-domain packs with the Windows product for offline legal retrieval, while preserving an independent future corpus-update path.

## Deferred after Stage 15

```text
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 15.2 is COMPLETE. Stage 15.3 implementation is in progress on `stage15-3-corpus-version-management`: the Corpus Release model, deterministic update planner, staged/atomic legal-store rebuild, baseline `three-domain-core@1.0.0`, regressions and operating documentation are checked in. Final authoritative PR-triggered CI is still required before 15.3 may be marked COMPLETE. Do not begin Stage 15.4/15.5 and do not create/merge a Stage 15.3 PR without separate authorization.**
