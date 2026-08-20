# Stage 15 official corpus catalog

This directory is a **vetted import plan**, not the legal corpus itself.

`three-domain-core.json` records Authority/Version identity, applicability dates, target Corpus Packs and official provenance chains that have been checked closely enough to proceed to the snapshot step.

It deliberately does **not** contain:

- frozen full-text source snapshots;
- source SHA-256 values;
- parsed article counts;
- canonical Legal Evidence rows;
- a claim that any Corpus Pack is already complete or `READY`.

## Amendment decisions are not full-text snapshots

For an amended law, an official amendment decision may establish the amendment date, effective date and the requirement to republish the law. It must not be substituted for the republished consolidated text when `target_coverage` is `FULL_TEXT`.

Stage 15.2B must resolve an official consolidated/full-text source for each non-blocked catalog entry, freeze the exact text, compute SHA-256, verify article count and only then create a Stage 6-compatible import manifest.

If the complete current text cannot be resolved or if applicability is only partially representable, keep the entry unimported/blocked rather than fabricating complete coverage.

## Status meaning

```text
VETTED_FOR_SNAPSHOT
  Authority/Version identity and official provenance chain are vetted for the next source-freezing step.

PROMULGATED_NOT_YET_EFFECTIVE
  Officially enacted/published, but not applicable on catalog verified_on.

BLOCKED
  A known validity/provenance/modeling issue prevents a safe uniform full-text import.
```

The catalog is intentionally independent from later Stage 15.3 corpus-update delivery, Stage 15.4 domain-aware retrieval and Stage 15.5 Windows corpus packaging.
