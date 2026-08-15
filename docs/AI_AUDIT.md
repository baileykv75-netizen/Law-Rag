# Stage 8 — Primary LLM Audit Reasoning

Stage 8 introduces one primary generative audit provider after deterministic extraction, rule checks and legal retrieval are complete. It does not introduce a second reviewer model or an autonomous Agent.

## Pipeline

```text
contract.json
+ audit-rules.json
+ explicit as_of
        ↓
deterministic Stage 8 topic/query builder
        ↓
Stage 7 legal retrieval
        ↓
AuditContextPackage
        ↓
PrimaryAuditProvider
        ↓
strict model JSON
        ↓
deterministic evidence/citation/version validation
        ↓
runtime/jobs/<job-id>/ai-audit.json
```

The model does not reread the raw PDF and does not receive the entire contract by default. The context builder sends only canonical clauses matched by the current deterministic legal-topic map, non-PASS rule context, and Stage 7 Legal Evidence candidates.

## Current deterministic issue map

The first Stage 8 context builder recognizes only a deliberately bounded set of topics that overlap the currently verified public legal seed:

- 格式条款;
- 违约金;
- 定金;
- 合同生效;
- 合同履行;
- 违约责任;
- 合同形式;
- 合同成立.

Each topic maps to a deterministic retrieval query. The query method is recorded as `stage8-keyword-map-v1`.

This is intentionally conservative. A clause that does not match the bounded map is not automatically converted into a novel legal issue by the model.

## Primary provider boundary

Domain code depends on `PrimaryAuditProvider`, not on a provider-specific SDK.

Current adapters:

```text
DeepSeekProvider
FakeAuditProvider   # deterministic tests only
```

The real provider uses the existing `httpx` dependency against DeepSeek's OpenAI-compatible HTTP endpoint. There is no hidden fallback to Kimi, Qwen or another provider.

### DeepSeek configuration

Local environment variables:

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

The API key is never written into `ai-audit.json`.

The DeepSeek API contract was re-verified against official documentation on **2026-08-15**. Current implementation uses:

```text
model: deepseek-v4-pro
response_format: {"type":"json_object"}
thinking: {"type":"enabled"}
reasoning_effort: high
stream: false
```

Official references checked during implementation:

- https://api-docs.deepseek.com/updates/
- https://api-docs.deepseek.com/api/create-chat-completion
- https://api-docs.deepseek.com/zh-cn/guides/json_mode/

The old `deepseek-chat` / `deepseek-reasoner` aliases are not used by Law-Rag Stage 8.

## Prompt-injection boundary

Contract text, evidence quotes, legal text, filenames and deterministic rule explanations are serialized as **untrusted data**.

System instructions explicitly state that embedded text such as:

```text
Ignore previous instructions...
```

must not be treated as an instruction.

This prompt boundary is useful but is not the security guarantee. The deterministic post-model validator remains authoritative.

## Strict post-model validation

A syntactically valid JSON response is not enough. Before persistence, Law-Rag checks:

- output matches the strict Stage 8 Pydantic schema;
- duplicate finding IDs are rejected;
- every issue ID was actually supplied;
- every canonical object ID was actually supplied;
- every contract Evidence ID was actually supplied;
- every Legal Evidence ID was actually supplied by the cited issue package;
- cited legal evidence still exists in the canonical legal store;
- the cited legal version is the version applicable on the requested `as_of` date;
- `SUPPORTED_FINDING` contains both contract evidence and Legal Evidence;
- OCR/source uncertainty propagates into review state;
- insufficient/ambiguous legal retrieval cannot be silently converted into certainty;
- `NO_FINDING` is not accepted as a confident negative conclusion when evidence coverage is incomplete.

If any validation fails, the new response is not written over an existing valid `ai-audit.json`.

## Evidence sufficiency

Stage 8 preserves explicit evidence states:

```text
SUFFICIENT
PARTIAL_CORPUS
INSUFFICIENT_CORPUS
VERSION_UNCERTAIN
SOURCE_UNCERTAIN
```

The current public legal seed is `CURATED_EXCERPT`, so a supported finding can still carry `PARTIAL_LEGAL_CORPUS`. This means the cited evidence supports the stated issue, but the local corpus is not complete enough to claim exhaustive legal review.

## Persistence

Validated report:

```text
runtime/jobs/<job-id>/ai-audit.json
```

Persisted provenance includes:

- audit schema/engine version;
- provider/model;
- explicit `as_of`;
- contract source/content fingerprints;
- deterministic context fingerprint;
- provider request ID when available;
- final response hash;
- safe token-usage metadata;
- supplied contract/Legal Evidence IDs;
- validated findings and warnings.

DeepSeek `reasoning_content` is not persisted. Only the final structured `content` is parsed; a hash of the raw provider response is retained for provenance without storing hidden reasoning text.

## Local API

```text
GET  /api/ai/providers/health?provider=deepseek
POST /api/documents/<job-id>/ai-audit
GET  /api/documents/<job-id>/ai-audit
```

Example POST body:

```json
{
  "as_of": "2026-08-15",
  "provider": "deepseek",
  "use_semantic": false
}
```

Provider health is configuration-only. It does not perform a paid/network model request.

## Normal CI

Normal CI never needs a DeepSeek key and never spends external-model credits.

Deterministic tests use the fake/static provider while still exercising:

- real Stage 6 seed import;
- real Stage 7 BM25 retrieval;
- context construction;
- strict schema validation;
- invented contract/Legal Evidence rejection;
- stale legal-version rejection;
- prompt-injection separation;
- provider failure preservation;
- API persistence/load;
- DeepSeek HTTP request-shape contract through a mocked `httpx` client.

## Optional real DeepSeek smoke

A real network/paid smoke test exists but is skipped by default.

From `backend/`:

```bat
set PYTHONPATH=.
set DEEPSEEK_API_KEY=<your local key>
set LAW_RAG_DEEPSEEK_SMOKE=1
..\.venv\Scripts\python.exe -m pytest -q -m deepseek_smoke
```

The smoke uses synthetic empty context only. It does not send a real/private contract.

## Stage boundary

Stage 8 does **not** include:

- Kimi/Qwen second-model review;
- multi-agent frameworks;
- autonomous tool selection;
- unrestricted chat over a private contract;
- automatic web/legal corpus expansion;
- final human approval workflow;
- final professional audit workstation;
- Windows installer packaging.

Those remain later-stage work.
