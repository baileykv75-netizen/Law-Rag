# Backend

This directory will contain the local Python/FastAPI application.

Backend responsibilities include local HTTP endpoints, job creation, validation, application orchestration, local persistence access, and stable interfaces to document/OCR/RAG/rule/LLM components.

Provider-specific SDK details should remain behind adapters rather than leaking through endpoint/domain code.
