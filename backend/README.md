# Backend

The Stage 1 backend is a local FastAPI application. It currently provides only the application shell and document-ingestion boundary; OCR, legal retrieval, LLM calls, audit rules, and Agent behavior are intentionally absent.

## Endpoints

- `GET /api/health` — local service health check.
- `POST /api/documents` — accepts one `.pdf`, `.jpg`, `.jpeg`, or `.png` file and stores it under the ignored local runtime directory.

The ingestion endpoint returns a generated job/document ID, original filename, media type, byte size, status, and local-only storage scope.

## Stage 1 validation

The backend validates:

- supported file extension;
- declared MIME/media type when present;
- basic PDF/JPEG/PNG file signature;
- non-empty content;
- maximum file size of 50 MiB.

The original filename is never used as the storage path. A generated UUID directory and fixed `source.<ext>` filename are used instead.

## Local storage

Default runtime path from the repository root:

```text
runtime/uploads/<job-id>/source.<ext>
```

`runtime/` is ignored by Git and must remain local. Tests override this location with `LAW_RAG_RUNTIME_DIR` so test uploads do not contaminate the development runtime.

## Run manually

From the repository root after creating `.venv` and installing `backend/requirements.txt`:

```bat
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs are then available locally at `http://127.0.0.1:8000/docs`.

## Tests

```bat
cd backend
set PYTHONPATH=.
..\.venv\Scripts\python.exe -m pytest -q
```

Stage 1 tests cover health, supported PDF upload, unsupported extension rejection, and fake-PDF signature rejection.

Provider-specific SDK details must remain behind adapters in later stages rather than leaking through endpoint/domain code.
