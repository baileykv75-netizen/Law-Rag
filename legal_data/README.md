# Law-Rag legal data

This directory contains checked-in schemas, deterministic import inputs, and carefully curated public legal material. Generated databases, downloaded live snapshots, indexes, and import reports belong under ignored `runtime/legal/` paths instead.

## Trust model

Legal evidence is not an anonymous text chunk. Every usable article must retain:

- authority identity and title;
- authority class and issuing body;
- version identity and status;
- effective interval;
- official source references;
- source snapshot SHA-256;
- exact article token/text and article SHA-256;
- stable `legal:<authority>:<version>:<article>` Evidence ID;
- schema/importer provenance.

If source/version identity is uncertain, Law-Rag should reject or expose ambiguity instead of guessing.

## Corpus Packs

Stage 15 adds `legal_data/packs/<pack-id>/pack.json` as a classification/distribution layer above canonical Authority/Version identity.

A Corpus Pack references ordinary Law-Rag authority manifests; it does not duplicate legal text or create a second Legal Evidence identity. The same Authority/Version may be referenced by multiple packs when it belongs to multiple legal domains.

Initial Stage 15 packs are:

```text
cn-intellectual-property-core
cn-enterprise-compliance-core
cn-labor-dispute-core
```

They are checked in as `DRAFT` during Stage 15.1 and intentionally contain no claimed legal coverage. Stage 15.2 populates verified official sources before any pack may be marked `READY`.

Domain tags are open lowercase ASCII slugs rather than a closed code enum, so future packs such as construction, finance or consumer law can be added without changing canonical legal identity.

See `docs/CORPUS_PACKS.md` for pack schema, path-safety and membership rules.

## Stage 6 seed scope

The checked-in Stage 6 seed is intentionally small. It currently contains two **CURATED_EXCERPT** records:

1. `中华人民共和国民法典` — 8 contract-core articles: 469, 496, 497, 502, 509, 577, 585, 586.
2. `最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释` — 7 selected articles: 1, 3, 9, 10, 16, 65, 69.

These excerpts are useful for validating the legal-evidence architecture. They are **not complete copies of either authority**.

Therefore:

> absence of an article or proposition from this seed must never be interpreted as evidence that the authority contains no such rule.

Stage 7 retrieval results must keep coverage metadata visible so a partial corpus cannot create false-negative legal conclusions.

## Official-source policy

Real records may use only verified authoritative public sources. Manifests record source URLs, effective dates, verification notes, expected source hashes, and expected article counts. Search-result snippets, commercial law databases, blogs, copied legal sites, and model memory are not sources of record.

## Rebuild

From Windows repository root after `setup-dev.bat`:

```text
rebuild-legal-seed.bat
```

Equivalent developer command from `backend/`:

```text
python -m app.legal.cli rebuild --manifest ../legal_data/seed/manifest.json
```

A successful rebuild creates:

```text
runtime/legal/legal.db
runtime/legal/import_reports/last-import-report.json
```

Both are local runtime artifacts and ignored by Git.
