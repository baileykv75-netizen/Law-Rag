# Runtime, Startup, and Data-Integrity Hardening

Stage 11C hardens the existing local application before Windows release bundling. It does not add a new reasoning model, automatic repair path, or installer.

## 1. Safety rule

Runtime diagnosis follows this order:

```text
detect problem
  -> preserve existing data
  -> expose an explicit state
  -> suggest an operator action
  -> repair/rebuild only after an explicit command
```

Health/integrity inspection never calls DeepSeek/Kimi, downloads OCR/embedding weights, rebuilds legal/retrieval databases, rewrites job artifacts, or deletes stale/corrupt files.

## 2. Runtime health

Run on Windows:

```text
diagnose-runtime.bat
```

Or from `backend/`:

```text
python -m app.runtime_health_cli
python -m app.runtime_health_cli --json
```

API:

```text
GET /api/runtime/health
```

The report uses explicit states:

```text
OK
OPTIONAL_NOT_CONFIGURED
MISSING
STALE
CORRUPT
MISCONFIGURED
UNAVAILABLE
ACTION_REQUIRED
```

Checks include:

- Python >= 3.11;
- native PDF prerequisites (`pypdf`, `pypdfium2`);
- runtime path existence/creatability/writability preflight;
- `legal.db` SQLite read-only `PRAGMA quick_check`, schema and article count;
- `retrieval.db` read-only integrity/schema checks plus legal-source fingerprint staleness;
- optional PaddleOCR module presence;
- optional sentence-transformers semantic-runtime presence;
- DeepSeek/Kimi configuration presence and base-URL shape without returning secret values.

Optional components do not block the base application when their documented fallback exists. In particular:

```text
PaddleOCR missing
  -> scanned/image OCR unavailable
  -> native PDF workflows can still run

sentence-transformers/BGE missing
  -> semantic channel unavailable
  -> Exact + BM25 remain supported

DeepSeek/Kimi key missing
  -> external audit/review call unavailable
  -> local upload/extraction/rules/legal review surfaces remain available
```

`os.access()` writability is a best-effort preflight only. Actual writes still handle filesystem failures explicitly.

## 3. Startup behavior

`start-dev.bat` now:

1. checks the existing Python venv and frontend `node_modules`;
2. runs the non-mutating runtime diagnostics;
3. blocks startup only when the **base runtime** is not ready;
4. refuses a duplicate start if local ports `8000` or `5173` are already listening;
5. starts the backend/frontend only after those checks pass.

`setup-dev.bat` verifies both the PATH Python and existing `.venv` are Python 3.11+ before reporting setup success.

Retrieval build scripts resolve the configured legal database through the same backend storage resolver, so `LAW_RAG_LEGAL_DB` / custom runtime locations are not defeated by a hard-coded `runtime\\legal\\legal.db` precheck.

## 4. Database integrity

`legal.db` and `retrieval.db` diagnostics open SQLite using read-only URI mode and run `PRAGMA quick_check`.

A missing/corrupt/stale store is reported but never automatically deleted or rebuilt.

Existing rebuild behavior is already replacement-safe:

- Stage 6 legal rebuild constructs a temporary database and replaces the target only after validation succeeds;
- Stage 7 retrieval rebuild writes a dedicated `.rebuild.tmp` SQLite database, commits it, and calls `os.replace()` only after the build succeeds.

## 5. Critical job-artifact integrity

API:

```text
GET /api/runtime/jobs/<job-id>/integrity
```

The inspector checks, without mutation:

```text
source.*
contract.json
audit-rules.json
ai-audit.json
secondary-review.json
review-report.json
human-review.json
```

For each present JSON artifact it verifies:

- JSON is parseable;
- the owning Pydantic schema accepts it;
- embedded `job_id` matches the requested job when the schema contains a job ID.

It also validates available cross-artifact links:

```text
contract source fingerprint
  -> deterministic rule report

rule contract-content fingerprint
  -> DeepSeek primary report

DeepSeek context fingerprint + as_of
  -> Kimi secondary report

DeepSeek/Kimi provider/model/context identities
  -> review-report.json

review-report fingerprint
  -> human-review revisions
```

A human-review revision referring to an older review-report fingerprint is reported as `STALE`, not deleted or rewritten.

Missing later-stage artifacts can be normal for an incomplete job; missing is distinct from corruption.

## 6. Atomic artifact persistence

Critical Stage 4/5 writers that previously called `Path.write_text()` directly now resolve to an atomic artifact path. The shared writer:

```text
serialize first
  -> create one temp file in destination directory
  -> write
  -> flush + fsync
  -> os.replace(temp, target)
```

If replacement fails, the prior target remains untouched and temporary residue is cleaned best-effort.

Stage 8/9 audit/review artifacts already used temp-file + replace semantics and retain those boundaries.

## 7. Diagnostic privacy/logging

Runtime diagnostics never return:

- API key values;
- Authorization headers;
- contract/OCR text payloads;
- hidden DeepSeek/Kimi reasoning content;
- private benchmark contents.

Corrupt JSON diagnostics intentionally return safe file/state information instead of embedding raw Pydantic input values or private file contents in the error message.

## 8. Regression coverage

Stage 11C regressions cover at least:

- first-run/missing stores without directory mutation;
- healthy read-only legal/retrieval inspection;
- corrupt SQLite stores without overwrite;
- stale retrieval fingerprint without automatic rebuild;
- malformed provider base URL without network calls;
- secret non-disclosure;
- missing native-PDF dependency blocks base startup;
- missing OCR/BGE dependencies remain nonfatal;
- corrupt critical JSON remains explicit and byte-preserved;
- wrong job ID is rejected;
- missing original source is action-required;
- unknown-job integrity GET returns 404 without creating directories;
- simulated atomic replace failure preserves the previous valid artifact and leaves no temp residue.

Stage 11B public quality gates and Stage 1–10 regressions remain required throughout hardening.
