# Legal Corpus Packs

Corpus Packs classify and distribute canonical Law-Rag legal Authority/Version sources without duplicating legal text.

Each pack lives at `legal_data/packs/<pack_id>/pack.json` and references authority manifests by corpus-root-relative POSIX paths.

Stage 15 starts with three extensible DRAFT packs:

- `cn-intellectual-property-core`
- `cn-enterprise-compliance-core`
- `cn-labor-dispute-core`

They intentionally contain no authority references in Stage 15.1. Official source content is added in Stage 15.2 after source/version verification.

A new future domain is added by a new pack manifest and domain slug; do not add a closed domain enum or duplicate shared authority text between packs.

See `docs/CORPUS_PACKS.md` for the architecture and validation rules.
