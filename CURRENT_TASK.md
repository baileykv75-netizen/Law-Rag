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
                 15.3 corpus update + version management NEXT
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
- 16 catalog entries were verified on 2026-08-20.
- 15 entries are representable as complete Authority/Version snapshots.
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

### Implemented infrastructure

- Stage 15 registry-aware validation is wired into the Stage 6 importer without changing legacy seed behavior.
- FULL_TEXT freezing requires an exact contiguous Article 1..N sequence.
- Snapshot SHA-256 is pinned over normalized UTF-8 canonical legal text.
- Supplemental official TEXT carriers must be registry-approved and cannot create/replace PRIMARY provenance.
- Freeze output is deterministic and changed content cannot silently overwrite an existing Authority/Version snapshot.
- Touching version intervals derive deterministic supersedes/superseded-by links.
- Authority metadata stays stable across versions; version-specific promulgation instruments remain version provenance rather than splitting one law into multiple Authority identities.
- Stage 15 CI now supports `push`, `pull_request` and manual dispatch so PR-triggered validation is observable through the connected GitHub tooling.

### Frozen corpus — COMPLETE

Knowledge-property pack:

```text
Patent Law                         82
Copyright Law                      67
Trademark Law 2019                 73
Trademark Law 2026/2027            87  NOT_YET_EFFECTIVE until 2027-01-01
Anti-Unfair Competition Law        41  shared with enterprise pack
--------------------------------------
Pack membership articles          350
Authorities / Versions            4 / 5
```

Enterprise-compliance pack:

```text
Company Law                       266
Anti-Unfair Competition Law        41  shared with IP pack
Anti-Monopoly Law                  70
Data Security Law                  55
Personal Information Protection    74
Cybersecurity Law                  81
--------------------------------------
Pack membership articles          587
Authorities / Versions            6 / 6
```

Labor-dispute pack:

```text
Labor Law                         107
Labor Contract Law                 98
Labor Dispute Mediation/Arbitration 54
Social Insurance Law               98
Labor Dispute Interpretation (II)  21
--------------------------------------
Pack membership articles          378
Authorities / Versions            5 / 5
```

Three-pack union after deduplicating the shared Anti-Unfair Competition Authority/Version:

```text
14 Authorities
15 Versions
1274 unique Articles
14 EFFECTIVE versions
1 NOT_YET_EFFECTIVE version (Trademark Law effective-2027-01-01)
0 excerpt-only versions
```

All 15 non-BLOCKED versions have checked-in `snapshot.txt` + `manifest.json` with official provenance, expected article count and pinned SHA-256.

### Deterministic validation — COMPLETE

Stage 15 tests cover:

- actual manifest import/rebuild for the frozen corpus;
- repeat import -> `NO_CHANGE` identity stability;
- Article counts and terminal-article evidence;
- Trademark 2019 -> 2027 transition semantics;
- Cybersecurity 2025 amendment effective 2026-01-01 even though Article 81 retains the original 2017 commencement sentence;
- Anti-Monopoly 2022 amendment effective 2022-08-01 even though Article 70 retains the original 2008 commencement sentence;
- Labor Contract, Labor and Social Insurance current amended-version dates independent of historical commencement text retained in terminal articles;
- Labor Dispute Interpretation (I) remains BLOCKED and is not imported;
- three-pack union deduplicates the shared Anti-Unfair Competition manifest and expects `14 Authorities / 15 Versions / 1274 Articles`;
- checked-in Pack status is `READY` only after repository-level CI validation.

Pack manifest references and release status:

```text
cn-intellectual-property-core   5 manifests / READY
cn-enterprise-compliance-core   6 manifests / READY
cn-labor-dispute-core           5 manifests / READY
```

### Authoritative Stage 15.2B validation

Validation PR: Draft PR #11, `stage15-2b-fulltext-snapshots` -> `stage15-2a-official-source-inventory`.
The PR exists only to expose PR-triggered CI evidence and must not be merged as part of Stage 15.2B closeout without separate authorization.

DRAFT-candidate validation: Stage 15 CI run #52 (`32356799261`) — SUCCESS.

```text
backend pytest                      391 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

Final READY-candidate validation: Stage 15 CI run #63 (`32357240734`) — SUCCESS.

```text
backend pytest                      391 passed, 5 skipped, 1 third-party warning
public deterministic quality gates PASS
frontend production build          PASS
```

Run #63 validates the three Pack files in `READY` state, complete three-domain import/re-import behavior, the 1274-Article deduplicated union, version applicability rules, source-role policy, and the existing public deterministic regression gates.

## Remaining Stage 15 boundaries

### 15.3 — Corpus update + version management — NEXT

Preserve historical versions; detect additions/amendments/repeals deterministically; maintain corpus version independent of application version.
Do not begin implementation until Stage 15.3 is explicitly started as the next bounded stage.

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

Ship a verified baseline snapshot of the three READY packs with the Windows product for offline legal retrieval, while preserving an independent future corpus-update path.

## Deferred after Stage 15

```text
Stage 16  expert benchmark + regression corpus + real-provider UAT
Stage 17  tray/graceful quit + history + storage management
Stage 18  runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19  installer + code signing + safe updates + final documentation
```

## Current implementation boundary

**Stage 15.2B is COMPLETE. The three official Corpus Packs are READY with 15 non-BLOCKED full-text Authority/Version snapshots, 14 canonical Authorities, 15 Versions and 1274 deduplicated Articles. Stage 15.3 is the next bounded stage; do not begin 15.3/15.4/15.5 work without explicitly advancing the stage. Draft PR #11 remains open only as validation evidence and is not authorized for merge.**
