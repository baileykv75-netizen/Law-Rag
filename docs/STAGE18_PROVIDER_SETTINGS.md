# Stage 18.4 — Advanced Provider Settings

## Purpose

Stage 18.4 adds advanced **non-secret** runtime options to the existing DeepSeek-primary / Kimi-secondary provider architecture.

It is not a generic OpenAI-compatible provider framework. The production roles remain fixed:

```text
DeepSeek -> Stage 13E primary Issue audit
Kimi     -> Stage 13F independent Issue + coverage review
```

The settings layer must not alter AuditPlan semantics, evidence scope, prompt safety instructions, output schemas, or application-owned maximum output-token ceilings.

## Secret boundary

API keys remain outside the new runtime configuration.

Existing resolution remains authoritative:

```text
Development environment secret
 -> DEEPSEEK_API_KEY / MOONSHOT_API_KEY
otherwise Windows desktop
 -> Windows Credential Manager
    Law-Rag:DeepSeek-API-Key
    Law-Rag:Kimi-API-Key
```

Stage 18.4 never writes API keys, bearer tokens, credentials, or authorization headers to `provider-runtime.json`, Job artifacts, browser storage, logs, or reports.

The new non-secret artifact is:

```text
runtime/config/provider-runtime.json
```

It contains only:

- explicit model identity;
- API root/base URL;
- request timeout;
- connect timeout;
- bounded HTTP attempt count;
- retry backoff.

Unknown fields are rejected. The persisted artifact must contain a complete DeepSeek + Kimi configuration and is fingerprinted using its canonical Pydantic JSON representation. Symlinked configuration files/directories fail closed.

## Resolution precedence

For model/base URL compatibility:

```text
saved Stage 18.4 runtime settings
 -> existing legacy environment model/base URL
 -> built-in defaults
```

Legacy environment variables remain supported when no saved runtime file exists:

```text
DEEPSEEK_MODEL
DEEPSEEK_BASE_URL
MOONSHOT_MODEL
MOONSHOT_BASE_URL
```

Runtime source is surfaced as:

```text
SAVED
ENVIRONMENT
DEFAULT
```

There is no hidden model/provider fallback.

## Model selection

The UI uses a select control rather than unrestricted model text.

Supported model identities are assembled from:

- the application default model for that provider;
- an existing deployment model environment value;
- optional deployment allowlists:
  - `LAW_RAG_DEEPSEEK_SUPPORTED_MODELS`
  - `LAW_RAG_KIMI_SUPPORTED_MODELS`

A newly saved model must be in the reported list. If an already-saved model later disappears from a deployment allowlist, Law-Rag keeps it visibly selected rather than silently replacing it with another model. The operator can then explicitly change/reset the configuration.

## Endpoint validation and privacy boundary

A provider base URL must be an API root.

Accepted:

```text
https://provider.example/v1
http://127.0.0.1:9000/v1   # loopback development only
http://localhost:9000/v1   # loopback development only
```

Rejected:

- non-loopback plain HTTP;
- embedded username/password;
- query strings;
- URL fragments;
- direct `/chat/completions` endpoint paths.

The built-in official defaults are:

```text
DeepSeek https://api.deepseek.com
Kimi     https://api.moonshot.cn/v1
```

Changing a saved endpoint away from the application default requires explicit confirmation because that endpoint can receive the same bounded contract/legal evidence that would otherwise be sent to the official provider endpoint.

The existing environment-variable endpoint compatibility path is treated as an administrator/development deployment configuration and remains explicit in the surfaced `ENVIRONMENT` source.

## Bounded timeouts and retries

User-editable ranges are deliberately bounded:

```text
request timeout    15–300 seconds
connect timeout     2–60 seconds
HTTP attempts       1–3
retry backoff        0–10 seconds
```

The retry control is intentionally described as **HTTP attempts inside one logical provider call**.

Stage 18.3 accounting remains:

```text
one AuditPlan Issue provider execution
 = one logical provider-call ledger unit
```

If that logical call internally retries a transient 429/5xx/network failure, the Stage 18.3 call-count budget is not falsely reported as multiple independent Issue-level model calls.

This means a request may create more than one HTTP transaction to the same configured provider endpoint while still representing one Issue-level provider execution. The UI states this explicitly.

## Fixed application-owned safety settings

Stage 18.4 does **not** expose these as user settings:

- system/user prompt text;
- evidence IDs or context selection;
- retrieval scope;
- reasoning instructions;
- JSON output schemas;
- primary/secondary provider roles;
- primary Issue max output token ceiling;
- secondary Issue max completion-token ceiling;
- fake provider enable flags.

Current fixed safety ceilings remain owned by the provider adapters and regression tests.

## Local API

Read resolved non-secret runtime settings:

```http
GET /api/config/providers/runtime
```

Save a full DeepSeek + Kimi runtime configuration:

```http
PUT /api/config/providers/runtime
Content-Type: application/json
```

Reset saved overrides and return to legacy environment/default resolution:

```http
DELETE /api/config/providers/runtime
```

GET/PUT/DELETE are local configuration operations only. They never test a provider and never create API usage.

The existing explicit connection probe remains separate:

```http
POST /api/config/providers/test
```

That action intentionally sends one tiny fixed message stating that no contract data is included. It is the only settings action that may use provider/network resources.

## UI

The existing `API 设置` modal now separates:

1. **API Key** controls — protected credential storage / explicit connection test.
2. **高级运行参数** — model, endpoint, timeout and retry settings.

The advanced panel:

- works independently from Windows Credential Manager because it contains no secrets;
- displays `SAVED / ENVIRONMENT / DEFAULT` origin;
- uses provider-specific supported-model selectors;
- requires a custom-endpoint disclosure checkbox before saving a custom endpoint;
- makes clear that saving/resetting does not test the connection;
- distinguishes Stage 18.3 logical call budgets from Stage 18.4 internal HTTP retries.

## Provider adapter consistency

The following real-provider adapters resolve from the same runtime source:

```text
Stage 13E DeepSeek Issue V1 primary
Stage 13F Kimi Issue V1 secondary
legacy Stage 8 DeepSeek compatibility
legacy Stage 9 Kimi compatibility
explicit provider connectivity probe
provider configuration overview/health surfaces
```

This prevents a configuration UI from displaying one model/endpoint while another execution path silently uses a different environment/default value.

## Validation requirements

Provider-free CI must cover at least:

- default non-mutating resolution;
- legacy environment compatibility;
- saved-over-environment precedence;
- canonical artifact fingerprint validation;
- no secret fields in persisted runtime configuration;
- unsupported-model rejection;
- allowlisted model selection;
- custom endpoint confirmation;
- loopback-only plain HTTP;
- rejection of embedded credentials/query/fragment/direct completion paths;
- unknown request-field rejection;
- save/reset performing no network call;
- bounded timeout/retry validation;
- reset semantics;
- symlink fail-closed behavior;
- configuration overview containing no API key;
- explicit probe using resolved runtime settings and fixed non-contract text;
- all four real adapters resolving the same saved model/base URL/timeouts/retries;
- application-owned output-token ceilings remaining unchanged.

Real paid/network DeepSeek/Kimi UAT remains deferred to final acceptance after Stage 19 engineering.
