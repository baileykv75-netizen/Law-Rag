# Job Architecture Compatibility

Stage 13G.4 defines the compatibility boundary between persisted RC2 audit jobs and the current issue-based audit architecture.

## Architectures

Law-Rag resolves one authoritative audit architecture per job:

```text
LEGACY_RC2
ISSUE_V1
CONFLICT
```

`LEGACY_RC2` means the Stage 8/9 report family remains authoritative:

```text
ai-audit.json
secondary-review.json
review-report.json
```

`ISSUE_V1` means the Stage 13 issue family is authoritative:

```text
audit-plan.json
issue-legal-context.json
issue-primary-audit.json
issue-secondary-review.json
issue-review-report.json
```

`CONFLICT` is fail-closed. Consumers must not guess which report family to use.

## Resolution precedence

The resolver is read-only and uses this order:

1. Reject a `pipeline.json` that mixes legacy and Issue V1 stage records.
2. Validate an explicit legacy migration record and its preserved pipeline snapshot.
3. Use the current production pipeline shape as the strongest authority signal.
4. If there is no pipeline, use audit artifact-family presence.
5. If no provider-era audit artifacts exist, default the job to the current `ISSUE_V1` architecture.

This allows an old upload that never reached Stage 8/9 to enter the current pipeline without inventing a legacy dependency.

## Historical artifacts after migration

An explicit migration does **not** delete or overwrite old Stage 8/9 reports. They remain local historical artifacts.

A migrated job has:

```text
pipeline.json                 current Issue V1 runtime
pipeline-legacy-rc2.json      exact preserved RC2 runtime snapshot
job-architecture.json         migration provenance + snapshot SHA-256
ai-audit.json                 historical only, if previously present
secondary-review.json         historical only, if previously present
review-report.json            historical only, if previously present
```

The current pipeline shape plus the migration record make `ISSUE_V1` authoritative. Future Workspace/Results consumers must use the architecture resolver rather than selecting whichever JSON happens to exist.

## Snapshot integrity

Before replacing an eligible unfinished RC2 pipeline, Law-Rag atomically preserves the exact `pipeline.json` bytes and records their SHA-256 in `job-architecture.json`.

Every later architecture resolution re-hashes `pipeline-legacy-rc2.json`.

Missing or modified snapshots force:

```text
architecture = CONFLICT
```

Law-Rag does not silently repair or recreate migration history.

## Explicit migration only

Eligible unfinished RC2 jobs can migrate through:

```text
POST /api/documents/<job-id>/pipeline/migrate-legacy
```

The safe default provider mode is:

```text
REQUIRE_APPROVAL
```

Migration preserves the RC2 `as_of` date and semantic-retrieval setting. Shared local artifacts such as OCR, canonical contract structure and deterministic rule results are reused only through their normal validation/freshness checks.

Completed RC2 jobs are never rewritten in place. They remain readable historical audits. A new current-architecture audit should be created if a completed legacy result needs to be rerun.

Transient/in-flight RC2 jobs are not migration eligible. They must first reach a safe recovered, waiting, failed or cancelled state.

## Read-only architecture API

```text
GET /api/documents/<job-id>/architecture
```

This endpoint never creates a migration record, never rewrites pipeline state and never calls a model provider.

The response exposes:

- authoritative architecture;
- resolution source;
- current pipeline architecture;
- legacy and Issue V1 artifact presence;
- whether the job was migrated;
- preserved legacy pipeline snapshot name;
- whether explicit migration is currently available;
- conflict/warning details.

## Stage 13G boundary

Stage 13G.4 provides the compatibility substrate only. Workspace, Batch Results and Human Review are migrated in subsequent Stage 13G slices so each consumer can switch through one shared architecture resolver instead of implementing separate legacy-detection heuristics.
