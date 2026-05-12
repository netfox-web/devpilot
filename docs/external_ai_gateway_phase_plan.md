# External AI Gateway Phase Plan

Date: 2026-05-13
Status: planning only, no implementation in this phase

## 1. Objective

DevPilot should become a controlled AI provider gateway and usage governance center for external systems.

External systems should call AI providers through DevPilot instead of receiving raw OpenAI, Gemini, Claude, or other provider keys. DevPilot should authenticate the caller, enforce source-specific policy, route to approved providers/models, record usage and audit data, and return a safe response without exposing provider credentials.

## 2. Architecture

External systems should:

- Use DevPilot external API keys.
- Never receive raw OpenAI, Gemini, Claude, or provider-specific keys.
- Call DevPilot External AI Gateway endpoints.
- Let DevPilot route to allowed providers/models.

Suggested architecture:

```text
External System
  -> DevPilot External API Key
  -> DevPilot External AI Gateway
  -> Provider policy / budget / audit
  -> OpenAI / Gemini / Claude
```

The gateway should be a broker and governance layer, not a general-purpose remote execution surface.

## 3. DevPilot as Unified AI Key / Provider / Usage Governance Center

### Strategic Goal

DevPilot should become the shared AI gateway for future AI-related projects and internal/external systems.

All future AI-related systems should integrate through DevPilot for AI capability access, rather than receiving direct OpenAI, Gemini, Claude, or other provider credentials. DevPilot should centrally decide which `source_system` can use AI, which provider/model it can use, which capabilities it can call, and what rate, token, budget, and audit rules apply.

### Standard Integration Model

External systems receive:

```text
DEVPILOT_API_BASE_URL
DEVPILOT_SOURCE_SYSTEM
DEVPILOT_API_KEY
```

External systems do not receive:

```text
OPENAI_API_KEY
GEMINI_API_KEY
ANTHROPIC_API_KEY
CLAUDE_API_KEY
```

Provider keys stay inside DevPilot-controlled runtime configuration or a future DevPilot provider key vault.

### Admin Workflow

DevPilot admins should be able to:

- Generate and revoke external API keys.
- Configure `source_system` identities.
- Choose allowed providers.
- Choose allowed models.
- Choose allowed capabilities.
- Set daily and monthly request/token limits.
- Set budget limits.
- Disable tool calling.
- Disable worker execution.
- Disable project/task mutation.
- Review usage and audit logs.

### Source Policy Examples

`crm-system`:

- Allowed provider: OpenAI.
- Allowed model: `gpt-4.1-mini`.
- Capabilities: `summary`, `classification`, `rewrite`.
- Daily request limit: `1000`.
- Daily token limit: `500000`.
- Monthly budget: `50 USD`.
- Tool calling: `false`.
- Worker execution: `false`.
- Project mutation: `false`.

`crawler-system`:

- Allowed provider: Gemini.
- Allowed model: `gemini-flash`.
- Capabilities: `extraction`, `summarization`.
- Daily request limit: `300`.
- Daily token limit: `200000`.
- Monthly budget: `20 USD`.
- Tool calling: `false`.
- Worker execution: `false`.
- Project mutation: `false`.

`internal-agent-console`:

- Allowed providers: OpenAI, Claude.
- Allowed models: small/medium approved models only.
- Capabilities: `summary`, `rewrite`, `planning`.
- Requires approval for advanced actions.
- No deploy or infrastructure actions by default.

### Benefits

- Provider keys never leave DevPilot.
- Source systems can be revoked independently.
- Provider/model can be changed centrally.
- Usage and cost can be audited.
- Budgets can be enforced.
- External systems do not need code changes when provider routing changes.
- Safer foundation for future AI projects.
- One common integration pattern for all AI-related systems.

### Safety Defaults

Permanent defaults:

- Fail closed if no source policy exists.
- No raw provider key exposure.
- No unlimited provider access.
- No worker execution by default.
- No tool calling by default.
- No project/task mutation by default.
- No deploy or infrastructure actions by default.
- No full prompt/response storage by default unless policy allows it.
- All AI gateway requests must be audited.

### Roadmap Alignment

- External API Key Manager is the first layer.
- Provider Config Inspection is the second layer.
- Source AI Policy Manager is the third layer.
- External AI Gateway Generate API comes only after policy, budget, and audit behavior are ready.
- Chat, streaming, and tool calling come later and must be policy-gated.

## 3. Why Not Share Raw Provider Keys

Raw provider keys should not be distributed to external systems because they are difficult to revoke, audit, and constrain once they leave DevPilot.

Keeping provider keys inside DevPilot provides:

- Reduced risk of provider key leakage.
- Centralized revoke for external systems.
- Centralized model/provider policy.
- Centralized usage and cost tracking.
- Centralized audit trail.
- Provider/model changes without external system code changes.
- Safer incident response if one integration is compromised.

## 4. Key Management Layers

### A. External API Key Manager

Already implemented.

Responsibilities:

- Identifies `source_system`.
- Authenticates external systems.
- Can revoke keys.
- Stores hash and prefix only.
- Does not store raw keys.
- Does not expose raw keys after initial generation.

### B. Provider Key Vault / Provider Config

Future gateway provider credentials should be managed separately from external API keys.

Responsibilities:

- Manages OpenAI, Gemini, Claude, and future provider credentials.
- Keeps provider keys hidden from external systems.
- First version may inspect env-based provider config only.
- Later version may support managed provider keys through DevPilot admin UI.
- Must never return provider keys in API responses, logs, exports, or UI pages.

### C. Source AI Policy

Each `source_system` should have explicit policy.

Policy fields:

- `allowed_providers`
- `allowed_models`
- `allowed_capabilities`
- `max_tokens_per_request`
- `daily_request_limit`
- `daily_token_limit`
- `monthly_budget`
- `streaming_allowed`
- `tool_calling_allowed`
- `enabled`

Default behavior should be fail-closed: no policy means no gateway access.

### D. Usage / Audit Log

Each gateway request should record:

- `source_system`
- `request_id`
- `idempotency_key`
- `provider`
- `model`
- `capability`
- `status`
- `token_usage`
- `cost_estimate`
- `latency`
- `prompt_hash`
- `prompt_summary`
- `response_hash`
- `response_summary`
- `created_at`

Do not store full prompt/response by default.

## 5. Proposed MVP Endpoints

Planned endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/external/ai/generate` | Single prompt to one non-streaming text response. |
| `POST` | `/api/external/ai/chat` | Structured chat messages to one non-streaming assistant response. |
| `GET` | `/api/external/ai/usage` | Source-scoped usage and budget status. |

Recommended MVP start:

```text
POST /api/external/ai/generate
```

Start with one provider/model behind a strict allowlist before adding chat, streaming, or multi-provider routing.

## 6. Authentication

Reuse external API key auth:

- `X-DevPilot-Source-System`
- `X-DevPilot-Api-Key`
- `X-DevPilot-Request-Id`
- `X-DevPilot-Idempotency-Key`

Authentication must accept DevPilot-managed external keys and existing compatible env-based keys where already supported. Gateway endpoints must not accept raw provider keys from callers.

## 7. MVP Generate Request Contract

```http
POST /api/external/ai/generate
X-DevPilot-Source-System: crm-system
X-DevPilot-Api-Key: <devpilot-external-key>
X-DevPilot-Request-Id: req-123
X-DevPilot-Idempotency-Key: ticket-123:summary:v1
Content-Type: application/json
```

```json
{
  "capability": "summary",
  "model": "gpt-4.1-mini",
  "prompt": "Summarize this text...",
  "external_ref": "ticket-123",
  "metadata": {
    "tenant_id": "optional",
    "user_id": "optional"
  }
}
```

Notes:

- `capability` should be checked against source policy.
- `model` should be optional only if source policy defines a safe default.
- `external_ref` should be stored for audit/search.
- `metadata` should be treated as untrusted and redacted in summaries.

## 8. MVP Generate Response Contract

```json
{
  "ok": true,
  "request_id": "req-123",
  "source_system": "crm-system",
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "capability": "summary",
  "text": "...",
  "usage": {
    "input_tokens": 100,
    "output_tokens": 80,
    "total_tokens": 180
  },
  "estimated_cost_usd": 0.001,
  "execution_allowed": false,
  "side_effects": false
}
```

Error responses should be structured and should not expose provider keys, raw upstream stack traces, or secret-like content.

## 9. Safety Boundaries For MVP

The MVP must not allow:

- Worker execution.
- Arbitrary tool calling.
- File writes.
- Project/task mutation.
- Approval request creation.
- Deploy/restart.
- DNS, SSL, Nginx, Cloudflare, redirect, registrar, or infrastructure changes.
- Raw provider key exposure.
- Unrestricted model access.
- Unlimited token usage.

Gateway responses should include explicit safety markers such as `execution_allowed=false` and `side_effects=false`.

## 10. Fail-Closed Behavior

The gateway should reject requests when:

- Source has no policy.
- Source policy is disabled.
- API key is missing, wrong, or revoked.
- Requested capability is not allowed.
- Requested provider/model is not allowed.
- Provider is not configured.
- Budget is exceeded.
- Request is too large.
- Token limit is exceeded.
- Required request fields are missing.
- Idempotency replay is ambiguous or unsafe.

Fail-closed responses should use safe status codes such as `400`, `403`, or `429` with concise error messages.

## 11. Provider Abstraction

Planned provider routing:

- OpenAI
- Gemini
- Claude

Recommendation:

- First MVP supports one provider/model only.
- Provider/model must be behind a source-specific allowlist.
- External systems may request a model, but DevPilot policy decides whether it is allowed.
- DevPilot should normalize provider responses into the same response contract.
- DevPilot should record the actual provider/model used.
- DevPilot must never expose provider credentials.

## 12. Rate Limit And Budget Model

Plan source-scoped controls:

- Per-source daily request limit.
- Per-source daily token limit.
- Per-source monthly budget.
- Per-request max tokens.
- Optional per-minute burst limit.

Budget/rate limit checks should run before provider calls whenever possible.

Example rejection:

```json
{
  "ok": false,
  "error": "daily token limit exceeded",
  "source_system": "crm-system",
  "limit_type": "daily_tokens",
  "limit": 500000,
  "used": 500000,
  "execution_allowed": false,
  "side_effects": false
}
```

## 13. Prompt / Response Storage Policy

Default recommendation:

- Do not store full prompt by default.
- Store prompt hash and short summary.
- Do not store full response by default unless source policy allows it.
- Store response hash and short summary.
- Allow per-source retention policy later.

Potential retention modes:

- `none`
- `hash_only`
- `summary`
- `full`

Full retention should require explicit policy and should be avoided for sensitive integrations.

## 14. Idempotency

Use:

- `X-DevPilot-Idempotency-Key`

Expected behavior:

- Same source system and same idempotency key should return the same gateway result when safe.
- Retries should avoid duplicate provider calls if a prior successful result exists.
- Failed provider attempts should be recorded carefully so callers know whether retry is safe.
- Idempotency lookups must handle malformed prior records safely.

Open design point:

- Decide whether idempotency caches full response text, only metadata, or a redacted response summary.

## 15. Rollout Plan

### Slice 3A

- Planning doc only.

### Slice 3B

- Provider config inspection UI.
- Add `/admin/ai-providers`.
- Show configured/missing only.
- No provider calls yet.
- Do not reveal raw provider keys.

### Slice 3C

- Source AI policy manager.
- Add `/admin/external-ai-policies`.
- Use file-backed `data/external_ai_policies.json`.
- No DB migration.
- No provider calls yet.

### Slice 3D

- Minimal non-streaming `POST /api/external/ai/generate`.
- Strict allowlist.
- One provider/model.
- Audit log.
- No side effects.

### Slice 3E

- Usage log and export.
- Add `GET /api/external/ai/usage`.
- Add admin usage view.

### Slice 3F

- Budget and rate limit enforcement.

### Later

- Chat endpoint.
- Streaming.
- Multi-provider routing.
- Approval-gated advanced actions.

Each implementation slice should be separately reviewed, tested, committed, deployed, and production verified.

## 16. Test Plan

Tests should cover:

- Missing key.
- Wrong key.
- Revoked key.
- Source without policy.
- Model not allowed.
- Provider not configured.
- Token limit exceeded.
- Budget exceeded.
- Provider failure.
- Idempotency replay.
- Audit log created.
- No task/project mutation.
- No worker execution.
- No provider key leakage.
- No raw prompt/response leakage unless policy allows it.
- Malformed policy/audit files do not crash.
- Provider errors return safe structured responses.

## 17. Open Questions

- Which external system should onboard first?
- Which provider should be enabled first?
- Which model should be enabled first?
- What daily/monthly budget should be used?
- Should prompts be stored, summarized, or hashed only?
- Should responses be stored?
- Is streaming needed?
- Is tenant-level usage needed?
- What capabilities are allowed first: summary, classification, rewrite, extraction, or translation?
- Should idempotency return cached AI output or only prevent duplicate provider calls?
- Should gateway usage appear in existing AI cost screens or in a dedicated external usage view?

## Safety Reminder

This plan is documentation-only. It does not implement provider calls, gateway endpoints, worker execution, project/task mutation, migrations, deployment, restart, DNS, SSL, Nginx, Cloudflare, redirect, or infrastructure changes.
