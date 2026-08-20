# Corpus Pack Architecture

Stage 15 introduces Corpus Packs as a grouping and distribution layer above the existing canonical legal identity model.

## 1. Identity stays authoritative

A Corpus Pack never replaces or changes the existing legal identity:

```text
authority -> authority version -> article / Legal Evidence ID
```

The same authority/version may legitimately belong to more than one pack. Pack membership is classification/distribution metadata, not a second legal identity.

## 2. Why pack membership is many-to-many

Examples such as the Anti-Unfair Competition Law may be relevant to both intellectual-property and enterprise-compliance review. Duplicating its source text into two domain folders would create two copies that could drift.

Law-Rag therefore uses:

```text
Corpus Pack A ----\
                  >---- one Authority/Version source manifest
Corpus Pack B ----/
```

A pack stores corpus-root-relative references to authority manifests. Legal source snapshots remain single-source-of-truth inputs.

## 3. Pack manifest

Canonical location:

```text
legal_data/packs/<pack_id>/pack.json
```

Schema 1.0.0 fields:

```text
pack_schema_version
pack_id
pack_version
display_name
jurisdiction
description
domain_tags
status
authority_manifest_paths
```

`domain_tags` are validated lowercase slugs rather than a Python enum. Adding a future domain such as `construction`, `finance` or `consumer` must not require a code/schema release merely to recognize the domain name.

Pack states:

```text
DRAFT  metadata may exist before official authorities are populated
READY  at least one authority manifest is required
```

Stage 15.1 checks in three DRAFT skeletons only:

```text
cn-intellectual-property-core
cn-enterprise-compliance-core
cn-labor-dispute-core
```

Their legal content is populated in Stage 15.2. DRAFT must never be presented as complete legal coverage.

## 4. Authority manifests

Pack references point to ordinary Law-Rag `LegalManifest` files. The existing Stage 6 `legal_data/seed/manifest.json` remains valid without migration.

Future official material may use a canonical layout such as:

```text
legal_data/
  authorities/
    <authority-id>/
      <version-id>/
        manifest.json
        source.txt
  packs/
    <pack-id>/
      pack.json
```

The exact authority folder layout may evolve, but pack references always resolve from the `legal_data` corpus root and must stay inside it.

## 5. Safety and determinism

The pack loader fails closed for:

- unsupported pack schema versions;
- malformed JSON/schema;
- absolute paths, path traversal or Windows-style backslash references;
- missing/malformed authority manifests;
- duplicate manifest paths;
- duplicate authority/version identities inside one pack;
- a READY pack with no authority manifest;
- pack directory name and `pack_id` mismatch;
- duplicate discovered `pack_id` values.

Different packs are explicitly allowed to reference the same authority/version.

## 6. Stage boundaries

Stage 15.1 does **not**:

- download or claim coverage for the three legal domains;
- change `legal.db` schema;
- change exact/BM25/BGE retrieval behavior;
- route AuditPlan Issues by domain;
- package the corpus into Windows releases.

Those are handled by Stage 15.2–15.5. This slice only freezes the extensible grouping architecture while preserving all Stage 6–14 behavior.
