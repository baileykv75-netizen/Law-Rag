# Stage 18.2 — Authoritative DOCX / PDF Audit Report Export

## Purpose

Stage 18.2 adds a local report-export surface for the production `ISSUE_V1` audit chain. Export is a read-only presentation step over already-persisted authoritative artifacts. It does **not** run OCR, legal retrieval, DeepSeek, Kimi, or another provider.

The report is intended to preserve review traceability rather than flatten the audit into an unsupported global score.

## Authoritative input chain

```text
Canonical Contract / Contract Evidence
 -> AuditPlan Issue
 -> Issue Legal Context
 -> DeepSeek Issue Primary Audit
 -> Kimi Issue Secondary Review
 -> Deterministic Issue Review Comparison
 -> latest append-only Human Review decision (when present)
 -> AuditReportDocument
 -> DOCX / PDF
```

Before rendering, the builder requires exact Issue-ID coverage across:

- `audit-plan.json`
- `issue-legal-context.json`
- `issue-primary-audit.json`
- `issue-secondary-review.json`
- `issue-review-report.json`

Duplicate, missing, or extra Issue identities fail closed. Export is available only when the validated ISSUE_V1 Workspace state is `COMPLETE` or `HUMAN_REVIEW_REQUIRED`.

## Human-review semantics

`HUMAN_REVIEW_REQUIRED` does not block creation of a working report. This supports professional review and handoff. However, when mandatory human decisions remain outstanding, both report formats visibly state that the document requires human review and is not a final legal opinion.

Export never converts the absence of an Issue, a model agreement, or a deterministic comparison into a claim of legal correctness.

## Report contents

Each Issue keeps the following chain together:

```text
Issue identity / priority / why-review / questions
 -> Contract Evidence IDs and available source quote/page/anchor data
 -> local Legal Evidence Authority + Version + Article + effective boundary
 -> Primary state/severity/reasoning/suggestion/evidence sufficiency
 -> Secondary finding/coverage assessment/reasoning/suggestion
 -> deterministic comparison state/reasons/possible omission
 -> latest human decision, revision, timestamp, stale state, reviewer note
```

The report also includes:

- source filename and document kind;
- `as_of` date;
- contract type and planning mode;
- explicit canonical-object planning coverage;
- provider/model identities already recorded in the audit artifacts;
- uncertainty and warnings;
- source-artifact fingerprints;
- deterministic `report_content_fingerprint`.

## Formats

### DOCX

Rendered locally with `python-docx`. The output is editable for professional handoff while retaining the evidence chain and report fingerprint.

### PDF

Rendered locally with ReportLab. Chinese text uses ReportLab's built-in `STSong-Light` CID font mapping, so the repository does not distribute or expose external font files.

DOCX and PDF consume the same validated `AuditReportDocument`; format rendering cannot silently change the audit truth model.

## Storage and privacy

Generated files live only under:

```text
runtime/exports/<job_id>/
```

This path is part of the Stage 18.1 managed Job-private runtime encryption boundary on EFS-capable Windows systems.

Stage 18.2 also extends Stage 17 safe Job cleanup so `exports/<job_id>` moves through the **same crash-recoverable tombstone transaction** as `jobs/`, `uploads/`, and `rendered/`. A deleted Job therefore does not leave a private report behind.

The shared legal corpus under `runtime/legal/` remains outside Job cleanup and is never deleted with a report.

Symlinked export roots or Job export directories are rejected rather than followed.

## Integrity metadata

Each exported file gets:

- exported-file SHA-256;
- deterministic report-content fingerprint;
- a small local JSON manifest containing export identity/hash metadata only.

The HTTP response exposes:

```text
X-Law-Rag-Report-SHA256
X-Law-Rag-Report-Content-Fingerprint
```

The manifest deliberately does not duplicate contract text, legal article text, API keys, or model raw responses.

## Local API

```http
POST /api/documents/{job_id}/report-export/docx
POST /api/documents/{job_id}/report-export/pdf
```

The routes return downloadable local files. They do not cross the provider boundary.

## Workspace UX

The ISSUE_V1 Workspace exposes:

```text
导出 DOCX
导出 PDF
```

The controls are enabled only for `COMPLETE` or `HUMAN_REVIEW_REQUIRED`. The UI states explicitly that export is local and does not trigger a model call. If mandatory human review remains, the UI and the generated report both preserve that pending state.

## Validation boundary

Provider-free tests cover:

- openable DOCX and PDF generation with Chinese contract/legal content;
- exported-file hashes and hash-only manifest;
- API attachment headers;
- export-root symlink fail-closed behavior;
- duplicate/mismatched Issue coverage rejection;
- rejection of incomplete Workspace state before authoritative artifact reads;
- report storage included in Job storage accounting;
- report deletion through the existing tombstone transaction;
- shared legal corpus preservation.

Exact Windows frozen-package dependency validation for `python-docx` and ReportLab is reserved for Stage 18.5, where the release lock and PyInstaller closure will be updated and tested together rather than changing the proven release environment piecemeal.
