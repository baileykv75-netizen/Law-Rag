# CURRENT_TASK.md

# Stage 15 — Official Legal Corpus Expansion + Versioning + Retrieval Tuning

## Status

```text
Stage 11A–11E   COMPLETE / validated release foundations
Stage 12A–12F   COMPLETE / RC2 VALIDATED
Stage 13A–13G   COMPLETE / ISSUE_V1 production migration validated
Stage 14.1–14.7 COMPLETE / OCR distribution + DOCX + packaged Windows validation
Stage 15.1–15.5 COMPLETE / official three-domain corpus + versioning + domain-aware RAG + Windows baseline validated

Stage 16        NEXT
                expert benchmark + regression corpus + real-provider UAT
```

Stage 15 is closed. Do not reopen Stage 13 ISSUE_V1 topology, Stage 14 source/OCR boundaries, or Stage 15 corpus identity/versioning rules without new evidence.

## Production baseline

```text
Source file
 -> Source Evidence
 -> Canonical Contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> issue-based Legal RAG
      -> deterministic Issue domain route
      -> READY Corpus Pack eligibility
      -> applicable Authority Version
      -> Exact Citation + BM25 + optional local BGE
      -> deterministic fusion
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

The validated source boundary remains PDF/JPG/JPEG/PNG/modern DOCX with local native-text-first processing and bundled fixed local OCR for OCR-required content.

## Stage 15.1 — Corpus Pack architecture — COMPLETE

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

Corpus Pack is only a grouping/distribution layer. Membership is many-to-many, shared Authority/Version text is not duplicated, pack paths are corpus-root-relative POSIX paths, duplicate identity in one pack is rejected, and Stage 6 `LegalManifest` / `legal.db` compatibility is preserved.

Authoritative validation: Law-Rag CI #762 (`32323430473`) — SUCCESS.

## Stage 15.2 — Official three-domain corpus — COMPLETE

Frozen READY baseline:

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
1 NOT_YET_EFFECTIVE version
```

All 15 non-BLOCKED versions have checked-in official-source `snapshot.txt` + `manifest.json` with pinned SHA-256 and Article count. Labor Dispute Interpretation (I) remains explicitly BLOCKED because the current version-level validity model cannot safely flatten its paragraph-level partial repeal.

## Stage 15.3 — Corpus update + version management — COMPLETE

Version hierarchy is explicit:

```text
Application version
  != Corpus Release version
  != Corpus Pack version
  != Authority Version
```

Implemented immutable Corpus Releases, deterministic update planning, fail-closed historical/version mutation checks, and staged `legal.db` rebuild with atomic replacement.

Baseline Corpus Release:

```text
legal_data/releases/three-domain-core/1.0.0/release.json
corpus_id       three-domain-core
corpus_version  1.0.0
released_on     2026-08-20
Pack count      3
Authorities     14
Versions        15
Articles        1274
release_digest  4009c06967cd2281089e85bdfda64388dd4ac8fc3b86125d971bfa1c0f642b4f
```

Authoritative Stage 15.3 validation: Law-Rag Stage 15 CI run `32359854525` — SUCCESS.

## Stage 15.4 — Domain-aware Legal RAG — COMPLETE

Stage 15.4 adds an auditable eligibility layer before the existing retrieval engine without creating a second RAG path or changing ISSUE_V1 reasoning topology.

```text
AuditPlan Issue
 -> deterministic domain route
 -> READY Corpus Pack domain tags
 -> eligible Authority allowlist
 -> as_of applicable Authority Version
 -> Exact Citation + FTS5/BM25 + optional local BGE
 -> deterministic weighted RRF fusion
 -> IssueLegalEvidencePackage
```

Current deterministic route states:

```text
INTELLECTUAL_PROPERTY
ENTERPRISE_COMPLIANCE
LABOR_DISPUTE
CROSS_DOMAIN
UNMAPPED
```

Broad fallback remains explicit when signals cannot safely narrow scope. Authority eligibility is enforced before Exact, lexical and semantic candidate ranking and checked again before final fusion. Existing `as_of` Authority-Version applicability remains authoritative.

`IssueLegalContext` persists routing provenance plus a deterministic routing catalog fingerprint so later Pack-routing changes make old context visibly stale.

Legacy Stage 6/7 development corpora remain compatible: when the selected Stage 15 scope has zero overlap with the installed legacy store, retrieval preserves the historical path with an explicit warning rather than silently returning no law.

Checked-in nine-case three-domain benchmark requires:

```text
scoped Recall@5 >= 0.90
scoped MRR      >= 0.80
scoped Recall@5 >= broad Recall@5
scoped MRR      >= broad MRR
all scoped candidates inside eligible Authorities
```

Authoritative validation:

```text
Draft PR #13
head: stage15-4-domain-aware-rag
base: stage15-3-corpus-version-management
Law-Rag Stage 15 CI run #96 (`32441338892`) — SUCCESS
backend pytest: 416 passed, 5 skipped, 1 third-party warning
public deterministic quality gates: PASS
frontend production build: PASS
```

PR #13 is a validation carrier only and remains Draft/Open/Unmerged unless separately authorized.

See `docs/STAGE15_DOMAIN_AWARE_RAG.md`.

## Stage 15.5 — Windows baseline corpus packaging + final regression — COMPLETE

The Windows product now ships the immutable `three-domain-core@1.0.0` baseline instead of the old curated seed:

```text
14 Authorities / 15 Versions / 1274 Articles
```

Packaged legal assets are immutable and hash-verified. On normal first launch the complete baseline is staged and atomically installed into writable runtime storage.

A complete existing runtime corpus is **never overwritten** by an application upgrade, preserving the independent Stage 15.3 corpus-update path. An incomplete runtime legal directory fails closed rather than mixing packaged and runtime corpus assets.

The release also exposes a non-mutating offline `--diagnose-corpus` retrieval smoke. Diagnostic execution must not rewrite the packaged baseline bytes.

Authoritative validation on head `355a003c67bdf4d9424e105d54e48779bca98c42`:

```text
Law-Rag Stage 15 CI run #117 (`32444333939`) — SUCCESS
backend pytest: 422 passed, 5 skipped, 1 third-party warning
public deterministic quality gates: PASS
frontend production build: PASS

Law-Rag Stage 15.5 Windows Baseline CI run #6 (`32444333963`) — SUCCESS
exact Windows release-lock onedir build: PASS
frozen baseline + writable runtime install verification: PASS
packaged PDF/OCR/HTTP/privacy smoke: PASS
deterministic portable RC ZIP + manifest: PASS
fresh-extracted Stage 12–14 regression smokes: PASS
inspectable onedir + portable RC artifact upload: PASS
```

Validation PR:

```text
Draft PR #14
head: stage15-5-windows-baseline-corpus
base: stage15-4-domain-aware-rag
```

PR #14 remains a validation carrier only. Do not merge it without separate authorization.

## Stage 15 closeout invariants

The next stage must preserve all of the following:

- canonical legal identity is still `Authority -> Version -> Article / Legal Evidence`;
- Corpus Pack is eligibility/grouping metadata, never a second legal identity;
- Corpus Release, Pack version and Authority Version remain independently versioned;
- legal text mutation under an existing Authority/Version identity is forbidden;
- historical versions are preserved;
- applicability remains deterministic and `as_of`-aware;
- domain routing narrows eligible Authorities but does not claim that an unmapped Issue has no applicable law;
- retrieval remains Exact + lexical/BM25 + optional local BGE + deterministic fusion;
- Issue V1 Planner/DeepSeek/Kimi/comparison/Human Review topology remains unchanged;
- Windows bundled baseline is immutable while runtime corpus storage is writable and upgrade-preserving;
- provider calls remain explicit, bounded and approval-aware;
- private contracts, credentials, runtime jobs, private benchmark labels and model caches stay out of Git/release public assets.

## Next boundary — Stage 16

Stage 16 owns **expert benchmark + regression corpus + real-provider UAT**.

Stage 16 may measure and harden product quality across the proven architecture, including retrieval, issue coverage, legal citation correctness, cross-provider behavior and end-to-end review quality. It must distinguish deterministic/public regression evidence from private expert labels and real-provider UAT evidence.

Stage 16 must not silently become Stage 17 tray/history work, Stage 18 encryption/report export/provider-settings work, or Stage 19 installer/signing/update infrastructure.

## Deferred after Stage 16

```text
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 15.1–15.5 are COMPLETE and validated. The product baseline is `three-domain-core@1.0.0` with 3 READY Packs, 14 canonical Authorities, 15 Versions and 1274 unique Articles; Issue-level domain-aware retrieval and Windows baseline distribution are both validated. Stage 16 is NEXT. Draft PR #13/#14 remain open only as stacked validation evidence and are not authorized for merge. Do not begin Stage 17+ or merge validation PRs without separate authorization.**
