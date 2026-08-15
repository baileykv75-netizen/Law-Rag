# Frontend

The Stage 1 frontend is a React + Vite + TypeScript local browser interface.

Its current responsibility is deliberately narrow: select or drag one supported test document, validate basic client-side constraints, send the file to the local FastAPI backend, and display the returned metadata/status.

Legal reasoning, OCR, retrieval, secret management, and audit-domain decisions belong in backend/application layers.

## Requirements

Vite 8 requires a compatible modern Node.js version. The project is intended to use Node.js 22 LTS for development.

## Run manually

```bat
cd frontend
npm install
npm run dev
```

The UI opens at `http://127.0.0.1:5173` and calls the backend at `http://127.0.0.1:8000` by default.

To override the backend URL for development, define:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Validation

```bat
npm run typecheck
npm run build
```

## Stage 1 UI behavior

- project/local-use notice;
- file picker and drag/drop;
- PDF/JPG/JPEG/PNG only;
- 50 MiB client-side size limit;
- selected filename and size;
- upload progress state;
- backend validation error display;
- returned filename, media type, byte size, job ID, and storage scope.

No OCR result, legal conclusion, or model output is shown in Stage 1 because those systems do not exist yet.
