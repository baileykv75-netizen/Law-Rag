# Tools

This directory will contain replaceable tool adapters used by the application and later by the constrained Agent.

Planned subareas:

- `ocr/` - OCR and document-layout adapters;
- `legal_rag/` - indexing, retrieval, reranking, and legal evidence resolution;
- `rule_engine/` - deterministic contract audit rules;
- `llm/` - provider-neutral LLM interface and provider adapters.

Do not put business/audit policy into provider SDK wrappers. Keep provider concerns and domain concerns separate.
