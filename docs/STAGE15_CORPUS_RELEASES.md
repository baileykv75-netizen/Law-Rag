# Stage 15.3 — Corpus Release and Version Management

## Purpose

Stage 15.2B froze the first official three-domain corpus. Stage 15.3 adds a release/update layer without changing the proven Stage 6 legal identity or importer semantics.

The version hierarchy is deliberately separated:

```text
Application version
  != Corpus Release version
  != Corpus Pack version
  != Authority Version
```

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

A Corpus Release is only an immutable publication index over already-frozen Authority/Version manifests. It does not duplicate legal text and it does not replace `snapshot.txt` or `manifest.json` as legal-source truth.

## Baseline release

The first checked-in release is:

```text
legal_data/releases/three-domain-core/1.0.0/release.json

corpus_id       three-domain-core
corpus_version  1.0.0
released_on     2026-08-20
packs           3
Authorities     14
Versions        15
Articles        1274
```

It contains the three Stage 15.2B READY packs and preserves the already-promulgated Trademark Law version effective on 2027-01-01 as `NOT_YET_EFFECTIVE`.

## What a release pins

Each Authority/Version reference pins:

- canonical `authority_id` and `version_id`;
- a SHA-256 fingerprint of stable Authority metadata;
- publication/effective/end/repeal lifecycle dates;
- supersedes/superseded-by links;
- coverage type;
- frozen source snapshot SHA-256;
- expected Article count;
- canonical Authority manifest path;
- Corpus Pack membership.

Each release also pins each included Pack's `pack_version`, domain tags and manifest membership. Release JSON is deterministically ordered and carries its own `release_digest`.

## Fail-closed invariants

Release validation rejects:

- unsafe or non-POSIX corpus paths;
- empty releases;
- malformed/non-advancing numeric dotted versions;
- duplicate Pack or Authority/Version identities;
- Pack membership that does not contain the referenced manifest path;
- Authority metadata drift under one `authority_id`;
- overlapping Authority Version intervals;
- touching version intervals without reciprocal supersession links;
- a future version incorrectly marked effective, or an effective version outside its release-date interval;
- a repealed version without matching repeal/end dates;
- release summary or release-digest mismatch.

Building a release re-reads the checked-in snapshots and re-verifies normalized SHA-256 plus exact contiguous Article `1..N` parsing. An unrelated future DRAFT Pack does not block an existing release; callers may explicitly select the READY Pack set.

## Deterministic update plan

`plan_corpus_update(current, candidate)` classifies changes before anything is applied.

Safe forward examples:

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

Blocking examples:

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

The critical rule is that legal text under an existing `(authority_id, version_id)` may never be silently replaced. A changed snapshot SHA requires a new legal Version identity. Historical versions may not disappear from a later release.

When Pack membership or domain metadata changes, that Pack's `pack_version` must advance independently of the overall Corpus Release version.

## Safe database publication

`rebuild_legal_store_from_release(...)` does not incrementally mutate the live legal database.

```text
validated Corpus Release
  -> revalidate referenced manifest metadata + snapshot SHA/count
  -> build a sibling temporary legal.db using the existing Stage 6 importer
  -> verify Authority / Version / Article totals
  -> atomic os.replace() only after the complete rebuild succeeds
```

Any validation/import failure deletes the staged database and leaves the existing target database untouched.

This preserves Stage 6 single-manifest behavior and keeps runtime independent of live legal websites.

## CLI

Run from `backend/`.

Build a release from selected READY Packs:

```bash
python -m app.legal.corpus_release_cli build \
  --corpus-id three-domain-core \
  --corpus-version 1.0.0 \
  --released-on 2026-08-20 \
  --pack-id cn-intellectual-property-core \
  --pack-id cn-enterprise-compliance-core \
  --pack-id cn-labor-dispute-core \
  --output ../legal_data/releases/three-domain-core/1.0.0/release.json
```

Plan a future update against the current release:

```bash
python -m app.legal.corpus_release_cli plan \
  --current ../legal_data/releases/three-domain-core/1.0.0/release.json \
  --candidate-version 1.1.0 \
  --released-on YYYY-MM-DD \
  --output update-plan.json
```

If no `--pack-id` values are passed to `plan`, the candidate uses the current release's Pack set. Adding a new Pack is therefore an explicit action rather than an accidental consequence of another DRAFT/READY Pack appearing in the repository.

Rebuild a legal database from a validated release:

```bash
python -m app.legal.corpus_release_cli rebuild \
  --release ../legal_data/releases/three-domain-core/1.0.0/release.json \
  --database ./data/legal.db
```

## Update procedure

For a future law addition/amendment/repeal:

1. Vet official source/version provenance under the existing source registry policy.
2. Freeze any new full-text Authority/Version using the Stage 15.2B snapshot gate.
3. Never overwrite an old Version's snapshot to represent a legal amendment.
4. Close/supersede/repeal the old Version lifecycle only with explicit provenance and add the new Version when required.
5. Advance affected `pack_version` values when Pack membership/domain metadata changes.
6. Build a candidate Corpus Release whose `parent_corpus_version` is the currently published release.
7. Run the deterministic update planner.
8. Reject `BLOCKED` plans; do not weaken identity, SHA, history or version assertions to force an update through.
9. Rebuild the legal store from the candidate release in the staged database path.
10. Run full repository regression/quality validation before publishing that candidate as the next release.

## Stage boundary

Stage 15.3 is responsible for corpus publication/update/version management only. Domain-aware retrieval routing and retrieval tuning remain Stage 15.4. Windows baseline corpus packaging remains Stage 15.5.
