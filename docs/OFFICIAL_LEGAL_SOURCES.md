# Official Legal Sources and Stage 15.2A Inventory

Stage 15.2A establishes the provenance control plane for the first three production legal Corpus Packs. It does **not** yet import legal text into `legal.db`, and it does not mark any pack `READY`.

## 1. Trust boundary

`legal_data/source_registry.json` is an explicit allowlist of official source hosts and the roles each source may serve.

A registered host is **necessary but not sufficient** for a legal record to become source-of-record. Each Authority/Version still requires manual verification of title, version status, publication/effective dates, exact source document, article count and snapshot SHA-256 before import.

The initial registry includes:

- 国家法律法规数据库 — authoritative database;
- 中国人大网 — legislation, amendment decisions and presidential orders;
- 中国政府网 — central-government authoritative publication;
- 最高人民法院官网 / 最高人民法院公报 — judicial interpretations;
- 国家知识产权局 — official IP text/metadata cross-check only, not silently promoted to PRIMARY legal authority.

Commercial databases, blogs, search snippets, model memory and arbitrary mirrors are not registered legal sources.

## 2. Inventory is not Legal Evidence

`legal_data/catalog/three-domain-core.json` is a vetted import plan. Its entries are not yet canonical Legal Evidence and do not create `Authority -> Version -> Article` rows by themselves.

Catalog states:

```text
VETTED_FOR_SNAPSHOT
PROMULGATED_NOT_YET_EFFECTIVE
BLOCKED
```

`VETTED_FOR_SNAPSHOT` means the Authority/Version identity and official provenance chain are suitable for the next snapshot/hash step. It does not mean text integrity has already been frozen.

`PROMULGATED_NOT_YET_EFFECTIVE` preserves a law that has been enacted and published but is not yet applicable on the catalog verification date.

`BLOCKED` prevents a known semantic problem from being flattened into a misleading full-current-version claim.

## 3. First three-domain scope

### Intellectual property

- 中华人民共和国专利法 — current 2020 amendment / effective 2021-06-01;
- 中华人民共和国著作权法 — current 2020 amendment / effective 2021-06-01;
- 中华人民共和国商标法 — current 2019 amendment / effective 2019-11-01;
- 中华人民共和国商标法 — promulgated 2026 revision / effective 2027-01-01, explicitly not yet effective on 2026-08-20;
- 中华人民共和国反不正当竞争法 — current 2025 revision / effective 2025-10-15.

### Enterprise compliance

- 中华人民共和国公司法 — current 2023 revision / effective 2024-07-01;
- 中华人民共和国反不正当竞争法 — shared with the IP pack, not duplicated;
- 中华人民共和国反垄断法 — current 2022 amendment / effective 2022-08-01;
- 中华人民共和国数据安全法 — effective 2021-09-01;
- 中华人民共和国个人信息保护法 — effective 2021-11-01;
- 中华人民共和国网络安全法 — current 2025 amendment / effective 2026-01-01.

### Labor / employment disputes

- 中华人民共和国劳动法 — current 2018 amendment;
- 中华人民共和国劳动合同法 — current 2012 amendment / effective 2013-07-01;
- 中华人民共和国劳动争议调解仲裁法 — effective 2008-05-01;
- 中华人民共和国社会保险法 — current 2018 amendment;
- 最高人民法院关于审理劳动争议案件适用法律问题的解释（二） — 法释〔2025〕12号 / effective 2025-09-01.

The 2020 Labor Dispute Interpretation (I) is recorded separately as `BLOCKED`: Interpretation (II) expressly repealed paragraph 1 of Article 32 from 2025-09-01. The current Stage 6 `LegalVersion` model is version-level and cannot safely represent that paragraph-level partial repeal. Stage 15.2 therefore refuses to import Interpretation (I) as uniformly current `FULL_TEXT` rather than overstating validity.

## 4. Cross-pack identity rule

The 2025 Anti-Unfair Competition Law is one Authority/Version entry with two `pack_ids`:

```text
cn-intellectual-property-core
cn-enterprise-compliance-core
```

This is the intended Stage 15.1 many-to-many design: shared normative text is stored once and classified into multiple packs.

## 5. Version-transition rule

The Trademark Law is the first explicit future transition in the catalog:

```text
2019 version: effective 2019-11-01, end_date_exclusive 2027-01-01
2026 revision: NOT_YET_EFFECTIVE, effective 2027-01-01
```

As of 2026-08-20, retrieval must not treat the 2026 revision as current law. The catalog records it now so later snapshot/version work cannot accidentally miss an already-promulgated transition.

The Cybersecurity Law inventory likewise uses the 2025 amendment effective 2026-01-01 rather than silently retaining the original 2016 text as the current 2026 version.

## 6. Next 15.2 slice

15.2B will freeze actual official full-text snapshots for the non-blocked inventory entries, calculate source SHA-256 and expected article counts, create Stage 6-compatible Authority/Version manifests, and only then move eligible Corpus Packs toward `READY`.

15.2A deliberately does not implement:

- corpus update delivery/version polling (15.3);
- domain-aware RAG routing/tuning (15.4);
- Windows baseline corpus packaging (15.5).
