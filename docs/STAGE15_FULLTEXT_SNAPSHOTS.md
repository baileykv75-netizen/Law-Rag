# Stage 15.2B — Official Full-Text Snapshot Freezing

Stage 15.2B turns the vetted Authority/Version inventory from Stage 15.2A into deterministic, checked-in `FULL_TEXT` corpus inputs. This step must fail closed: a known law title or amendment decision is not enough to claim full-text coverage.

## Trust chain

The legal identity remains:

```text
authority -> authority version -> article / Legal Evidence ID
```

The source chain is deliberately split by role:

- `PRIMARY` establishes normative provenance and must come from a source approved for primary legal authority in `legal_data/source_registry.json`;
- `TEXT` may carry the complete republished text when an official department publishes a consolidated copy, but it cannot create or replace PRIMARY provenance;
- `METADATA` and `CROSS_CHECK` are not accepted as the bytes used for a `FULL_TEXT` snapshot.

Stage 15.2B may add one supplemental official `TEXT` carrier in a snapshot target when that carrier was discovered after the Stage 15.2A inventory. Supplemental sources are validated by the same registry and are copied into the final Stage 6 manifest. A supplemental `PRIMARY` is rejected.

Examples currently used by the first three packs:

- CNIPA may carry complete patent/trademark text as `TEXT`, while NPC/government provenance remains PRIMARY;
- CAC may carry the republished 2025-amended Cybersecurity Law as `TEXT`, while the NPC amendment decision remains PRIMARY provenance;
- MOHRSS may carry the consolidated 2012-amended Labor Contract Law as `TEXT`, while the NPC amendment decision remains PRIMARY provenance.

## Snapshot target sets

The checked-in target sets are:

```text
legal_data/catalog/cn-intellectual-property-core.snapshot-targets.json
legal_data/catalog/cn-enterprise-compliance-core.snapshot-targets.json
legal_data/catalog/cn-labor-dispute-core.snapshot-targets.json
```

Every non-`BLOCKED` catalog entry assigned to a pack must appear exactly once in that pack's target set. As of the 2026-08-20 verification pass, all 15 non-blocked Authority/Version targets are `READY_FOR_FREEZE`.

`spc-labor-dispute-interpretation-1:effective-2021-01-01` remains outside the target set because its paragraph-level partial repeal cannot be represented safely by the current version-level applicability model.

## Deterministic full-text gate

`app.legal.fulltext_snapshot.build_full_text_manifest_record()` accepts a snapshot only when:

1. the catalog entry is not `BLOCKED` and targets `FULL_TEXT`;
2. the selected source is a vetted `PRIMARY`/`TEXT` catalog source or an explicit registry-approved supplemental `TEXT` source;
3. the source path is a safe relative POSIX path;
4. every parsed article has a numeric ordinal;
5. article ordinals are exactly contiguous from `1` through the pinned expected count;
6. the normalized UTF-8 bytes produce a pinned SHA-256.

The resulting object is the existing Stage 6 `ManifestRecord`; Stage 15 does not introduce a second legal identity or a replacement database schema.

## Offline freeze command

The model/runtime does not reconstruct a law from search snippets. Obtain the exact official plain-text source first, then run the deterministic freezer from `backend/`:

```text
python -m app.legal.fulltext_snapshot_cli \
  --target-set ../legal_data/catalog/cn-intellectual-property-core.snapshot-targets.json \
  --authority-id prc-patent-law \
  --version-id effective-2021-06-01 \
  --source-file <path-to-exact-official-utf8-text> \
  --output-dir ../legal_data/authorities/prc-patent-law/effective-2021-06-01
```

The command writes:

```text
snapshot.txt
manifest.json
```

It normalizes newline encoding, validates the complete article sequence, computes SHA-256, and emits a one-record Stage 6-compatible manifest. Re-running with byte-equivalent normalized input is idempotent. If either frozen output already exists with different content, the command refuses to overwrite it.

## What this does not do

The freeze command deliberately does **not**:

- scrape or trust a live website at application runtime;
- extract legal text from search-result snippets;
- treat an amendment decision as the complete consolidated law;
- silently overwrite an existing frozen Authority/Version;
- mark a Corpus Pack `READY` before actual snapshots/manifests have been frozen and import-tested;
- implement corpus update polling (15.3), domain-aware retrieval (15.4), or Windows corpus packaging (15.5).
