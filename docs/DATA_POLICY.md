# Data Policy

Law-Rag is developed in a public GitHub repository. This document defines what may and may not enter version control.

## 1. Default assumption

Assume every committed file can be read by anyone on the internet.

Repository visibility may change later, but development must not depend on secrecy of the Git repository.

## 2. Allowed repository data

Allowed examples:

- source code;
- public documentation;
- configuration templates without secrets;
- public legal-source metadata explicitly approved for redistribution;
- fully fictional contracts created for testing;
- synthetic benchmark cases that do not derive from confidential source material;
- non-sensitive test images generated specifically for the project.

## 3. Prohibited repository data

Never commit:

- real contracts;
- customer/client contracts;
- employment contracts containing real identities;
- IDs, phone numbers, bank details, signatures, seals, addresses, or other personal/confidential information;
- merely pseudonymized contracts that remain re-identifiable from context;
- private legal benchmark datasets;
- professional reviewer labels tied to confidential source documents;
- `.env` files;
- API keys/tokens/passwords/cookies;
- raw upload directories;
- OCR output derived from private contracts;
- generated audit reports derived from private contracts;
- local vector indexes built from private data;
- logs containing private document excerpts;
- model caches.

## 4. Fictional fixtures

Public fixtures should be fictional by construction, not simply redacted copies of real contracts.

Prefer:

- invented company names;
- invented people;
- invented addresses;
- invented contract numbers;
- intentionally designed arithmetic/date/risk patterns;
- clearly marked synthetic sample text.

If a fixture starts from a real source, do not commit it unless the owner has explicitly confirmed that the transformed document is safe for public release and no confidential source text remains.

## 5. Local private test data

Private or professionally reviewed test data should live outside tracked repository paths or under an explicitly ignored local directory such as:

```text
data_private/
benchmark_private/
uploads/
runtime/
outputs/
logs/
```

The exact runtime paths may evolve, but they must remain ignored by Git.

## 6. API keys and model credentials

Secrets belong in a local `.env` file or another operating-system secret store.

The repository may contain `.env.example` with empty placeholders only.

Never print full API keys in logs or UI error messages.

Later UI configuration should mask secrets and avoid returning them through ordinary API responses.

## 7. External model APIs

Before sending contract content to an external model API, the application should make the data path explicit.

Long-term design goals:

- keep raw files local;
- send only necessary text/evidence to configured providers;
- support local-only processing paths where feasible;
- allow future provider-specific privacy controls;
- record which provider/model received which analysis request at a metadata level without logging sensitive payloads by default.

## 8. Logs

Production-style logs should prefer identifiers and event summaries over raw contract text.

Good:

```text
job=JOB-123 stage=ocr page=7 status=low_confidence
```

Avoid by default:

```text
job=JOB-123 full_contract_text="..."
```

Debug logging that contains document text must be opt-in, local, and stored only in ignored paths.

## 9. Human reviewer workflow

When a legal professional helps evaluate the system:

- use fictional data whenever possible;
- otherwise use data that has been appropriately de-identified for the intended test;
- keep the reviewer benchmark outside the public repo unless it is safe for public release;
- store reviewer labels separately from application logs;
- do not use private test cases as public examples without explicit approval.

## 10. Incident rule

If a secret or private document is accidentally committed:

1. stop further sharing;
2. rotate exposed credentials immediately if any secret is involved;
3. remove the material from the current tree;
4. treat Git history as potentially exposed and perform history cleanup when necessary;
5. document the incident without reproducing the sensitive content.

Deleting a file in a later commit is not sufficient protection for a secret that already entered public Git history.
