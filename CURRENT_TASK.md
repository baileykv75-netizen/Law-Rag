# CURRENT_TASK.md

# Stage 1 — Local Application Shell

## Goal

Create the smallest reliable local application shell for Law-Rag.

At the end of this stage, a user should be able to run the project locally on Windows, open the local web interface, select a supported test file, send it to the backend, and see basic file metadata returned.

This stage deliberately does **not** implement OCR, legal RAG, LLM calls, audit reasoning, or Agent behavior.

## Why this stage comes first

The project must prove the local runtime boundary before adding heavyweight document/AI dependencies. A stable application shell gives later OCR/RAG work a clear place to live and exposes Windows setup problems early.

## In scope

### Frontend

Create a minimal local browser UI using React + Vite (TypeScript preferred).

Required UI behavior:

- display project name `Law-Rag`;
- display a short local/research-use notice;
- provide a file picker / drag-and-drop area;
- accept only `.pdf`, `.jpg`, `.jpeg`, `.png` at this stage;
- show the selected file name and size;
- provide an upload/start button;
- show success or failure state returned by the backend.

No elaborate visual design is required. Clean and functional is sufficient.

### Backend

Create a Python FastAPI application.

Required endpoints:

- health endpoint;
- file-ingestion endpoint for one test file;
- basic structured response containing at least file name, media type, byte size, and generated local document/job identifier.

The backend must validate file type and reject unsupported formats visibly.

### Local storage

Uploaded development files must go into an ignored local runtime directory, never into tracked repository paths.

The first implementation may use a simple per-job filesystem directory.

### Startup

Provide a developer-friendly Windows startup path.

Minimum acceptable result:

- documented frontend/backend start commands;
- preferably a root-level `start-dev.bat` that starts both development services or clearly tells the user what to do when one fails.

Do not package an `.exe` yet.

### Tests

Add minimal automated backend tests for:

- health endpoint;
- supported upload;
- unsupported file rejection.

If frontend test infrastructure would create disproportionate complexity at this stage, manual UI verification plus lint/typecheck is acceptable.

## Out of scope

Do **not** add any of the following in Stage 1:

- PaddleOCR;
- PDF text extraction;
- page rendering;
- document layout analysis;
- clause parsing;
- legal corpus;
- embeddings;
- vector database;
- DeepSeek/Kimi/Qwen API calls;
- Agent framework;
- audit rules;
- login/authentication;
- public deployment;
- Windows `.exe` packaging;
- real contract fixtures.

If implementation work reaches one of these areas, stop and leave it for the appropriate later stage.

## Recommended initial directory layout

```text
frontend/
backend/
runtime/              # ignored local data
fixtures/             # fictional public test fixtures only
tests/                # may be backend-local or root-level; choose one coherent convention
```

The exact structure may evolve, but must remain consistent with `ARCHITECTURE.md`.

## Acceptance criteria

Stage 1 is complete only when all of the following are true:

1. A fresh developer checkout has documented setup instructions.
2. Backend health endpoint returns success.
3. Frontend opens locally in a browser.
4. User can choose a PDF/JPG/JPEG/PNG file.
5. Supported test file reaches the backend and returns structured metadata.
6. Unsupported file type is rejected with a clear message.
7. Uploaded file is stored only under an ignored local runtime path.
8. No API key is required.
9. No real contract or private data is committed.
10. Backend automated tests pass.
11. Frontend build/typecheck/lint (as configured) passes.
12. `README.md` contains verified Stage 1 run instructions before the stage is declared complete.

## Completion rule

Do not change this file to Stage 2 until the acceptance criteria above are actually verified.

When Stage 1 is complete, the next task should become **Stage 2 — Document ingestion and native PDF text path**, still without prematurely implementing full OCR audit logic.
