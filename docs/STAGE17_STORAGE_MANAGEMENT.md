# Stage 17.3 — Safe Local Storage Management

## Purpose

Stage 17.3 adds explicit user-controlled cleanup for persisted Law-Rag Jobs while preserving the local-first evidence model and the shared legal corpus.

This stage does **not** add automatic retention deletion. A Job is removed only after a user explicitly selects a terminal Job and confirms the exact Job UUID.

## Deletion boundary

A cleanup transaction may move/delete only these Job-owned roots:

```text
runtime/jobs/<job_id>
runtime/uploads/<job_id>
runtime/rendered/<job_id>
```

The following shared roots are never members of the Job deletion transaction:

```text
runtime/legal/
runtime/batches/      # manifests are updated, not deleted wholesale
runtime/cleanup/      # transaction journal/tombstones
```

`runtime/legal/` contains the shared versioned legal/retrieval store and is intentionally outside the deletion path.

## Eligibility

Deletion is fail-closed. A new cleanup can begin only when:

- the Job is present in persisted local history;
- `pipeline.json` is a regular file and belongs to the requested Job;
- the Pipeline is terminal: `COMPLETE`, `FAILED`, or `CANCELLED`;
- history integrity is not `INVALID`;
- Job-owned roots are not symlinks;
- every existing batch manifest is parseable and filename/`batch_id` consistent;
- the request body repeats the same `confirm_job_id` as the path Job UUID.

Running, waiting, paused, cancel-requested, upload-only, or invalid Jobs are not deletable.

## Crash-safe transaction

Deletion is not a single recursive remove. The transaction is journaled under:

```text
runtime/cleanup/transactions/<cleanup_id>.json
runtime/cleanup/trash/<cleanup_id>/
```

Sequence:

1. Validate the live Job and bind authorization to the SHA-256 of its current `pipeline.json`.
2. Persist a `PREPARED` cleanup transaction.
3. Atomically move each Job-owned root into the transaction tombstone with `os.replace`.
4. Persist `ROOTS_MOVED`.
5. Remove the Job UUID from all batch manifests and repair `latest.json` if necessary.
6. Persist `REFERENCES_UPDATED`.
7. Remove the tombstone and transaction manifest.

All reference updates are idempotent. If the process stops after the destructive move, the next configured desktop server lifecycle replays remaining cleanup transactions **before** the tray/server begins serving requests.

The recovery path never re-authorizes a different Job and never follows symlinks.

## Storage visibility

`GET /api/batches/history/storage` reports:

- Job-owned bytes;
- batch-index bytes;
- shared legal-corpus bytes;
- cleanup journal/tombstone bytes;
- other runtime bytes;
- total runtime bytes;
- deletable vs protected Job counts.

This is a filesystem accounting view, not a quota or billing metric.

## API

```http
GET /api/batches/history/storage
DELETE /api/batches/history/jobs/{job_id}
Content-Type: application/json

{"confirm_job_id": "<same job UUID>"}
```

The delete response reports reclaimed Job-owned bytes and whether batch references/latest pointer required repair.

## UI

`/history` shows the storage breakdown and exposes `删除本机任务` only for Jobs already marked `can_delete=true`. The browser requires the user to type the full Job ID before sending the DELETE request. The backend independently repeats the same confirmation check.

No history read, storage summary, or cleanup operation invokes OCR, retrieval, DeepSeek, Kimi, or another external provider.
