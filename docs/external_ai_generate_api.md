# External AI Generate API

## Purpose

`POST /api/external/ai/generate` lets an approved external source system request a narrow text-only AI generation through DevPilot.

The production gateway is intentionally narrow and policy-gated:

- Providers: OpenAI/GPT, Gemini, and Claude.
- OpenAI models: `gpt-4.1-mini`, `gpt-4o-mini`.
- Gemini model: `gemini-1.5-flash`.
- Claude model: `claude-3-5-haiku`.
- Mode: non-streaming text only.
- Capabilities: `generate`, `summary`, `rewrite`, `classification`, `extraction`, `planning`, `chat`.

DevPilot keeps provider credentials internal. External systems receive only a DevPilot external API key.

External projects must not receive or store raw OpenAI, Gemini, or Claude provider keys. DevPilot owns provider credentials, source policy, usage logging, and budget limits.

## Production Deployment Record

Status: deployed to NAS production on 2026-05-20.

- Deployed commit: `fbf058b feat: enable external AI gateway providers`.
- Production base URL: `https://devpilot.aicenter.com.tw`.
- Route status: `/api/external/ai/generate` is present and POST-only.
- Source system provisioned: `external_project_default`.
- DevPilot-issued external API key: created; value is not stored in docs or git.
- External AI Policy: enabled for `openai`, `gemini`, and `claude`.
- Provider live calls during deployment: no.
- Smoke results:
  - `/ai-handoffs`: unauthenticated `302` to login.
  - `/api/external/ai/generate`: unauthenticated HEAD `405 Method Not Allowed`.
  - unauthenticated POST `/api/external/ai/generate`: `403 Forbidden`.

Deployment safety:

- Raw provider keys were not exposed to external projects.
- `.env` contents and secrets were not printed.
- Staging / `5012` was not touched.
- Nginx, DNS, Cloudflare, and SSL were not changed.

## Endpoint

```text
POST {DEVPILOT_API_BASE_URL}/api/external/ai/generate
```

Required headers:

```text
Content-Type: application/json
X-DevPilot-Source-System: {source_system}
X-DevPilot-Api-Key: {devpilot_external_api_key}
X-DevPilot-Request-Id: {stable-request-id}
X-DevPilot-Idempotency-Key: {stable-idempotency-key}
```

## Request

```json
{
  "provider": "openai",
  "capability": "generate",
  "model": "gpt-4.1-mini",
  "prompt": "Write a short product description...",
  "external_ref": "ad-studio-job-123",
  "metadata": {
    "project": "AD-Studio_AI"
  }
}
```

## Success Response

```json
{
  "ok": true,
  "source_system": "ad-studio-ai",
  "request_id": "req-123",
  "idempotency_key": "generate:ad-studio-job-123",
  "idempotent_replay": false,
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "capability": "generate",
  "text": "Generated text...",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 9,
    "total_tokens": 21
  },
  "estimated_cost_usd": null,
  "execution_allowed": false,
  "side_effects": false,
  "provider_calls_executed": true
}
```

## Required Source Policy

The authenticated `source_system` must have an enabled External AI Policy allowing:

- requested provider: `openai`, `gemini`, or `claude`
- requested model: `gpt-4.1-mini`, `gpt-4o-mini`, `gemini-1.5-flash`, or `claude-3-5-haiku`
- requested text capability
- no streaming
- no tool calling
- prompt size within `max_tokens_per_request`

If no policy is enabled, DevPilot returns:

```json
{
  "ok": false,
  "error": "external_ai_policy_not_enabled"
}
```

## Provider Configuration

If `provider` is omitted, DevPilot defaults to Gemini for compatibility with the original MVP.

DevPilot reads the Gemini provider key from:

- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`

DevPilot reads the OpenAI provider key from:

- `OPENAI_API_KEY`

DevPilot recognizes Claude provider keys from:

- `ANTHROPIC_API_KEY`
- `CLAUDE_API_KEY`

If the requested provider key is not configured, DevPilot returns:

```json
{
  "ok": false,
  "error": "provider_not_configured"
}
```

The provider key is never returned, logged, or exposed to external systems.

## External Project Integration Package

For another project that wants to use GPT/Gemini/Claude through DevPilot, give that project these three files from the integration toolbox:

1. `docs/integration_toolbox/external_project_admin_integration_instructions.md`
2. `docs/integration_toolbox/external_ai_gateway_future_api_guide.md`
3. One server-side client helper for that project's stack:
   - `docs/integration_toolbox/devpilot_external_client.js`
   - or `docs/integration_toolbox/devpilot_external_client.py`

Also give the project a DevPilot-issued `DEVPILOT_SOURCE_SYSTEM` and `DEVPILOT_API_KEY`. Do not give the project `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `CLAUDE_API_KEY`.

Operator instruction for the external project:

```text
Use DevPilot as the AI Gateway. Store only DEVPILOT_API_BASE_URL, DEVPILOT_SOURCE_SYSTEM, and DEVPILOT_API_KEY server-side. Call POST /api/external/ai/generate with provider openai, gemini, or claude only after DevPilot has enabled an External AI Policy for your source_system. Never store or request raw provider keys.
```

Required safety:

- Use a stable `X-DevPilot-Idempotency-Key` for retries.
- Never expose `DEVPILOT_API_KEY` to frontend JavaScript.
- Never log provider keys.
- Never log DevPilot API keys.
- Never log prompts that contain secrets.
- Never log full `Authorization` or `X-DevPilot-*` auth headers.
- Do not call raw OpenAI/Gemini/Claude APIs directly from external projects.

## Idempotency

Use `X-DevPilot-Idempotency-Key` for retry safety.

Behavior:

- A completed result for the same `source_system + idempotency_key` is replayed with `idempotent_replay=true`.
- Replayed responses do not call the provider again.
- Failed results are recorded, but are not replayed. Retrying the same idempotency key after fixing the failure can call the requested provider route again.

Completed idempotency results are stored in:

```text
data/external_ai_generation_results.json
```

## Usage / Audit Logging

Each authenticated generate attempt records a safe audit row in:

```text
data/external_ai_usage_log.json
```

Recorded fields include:

- `source_system`
- `request_id`
- `idempotency_key`
- `external_ref`
- `provider`
- `model`
- `capability`
- `status`
- `error_code`
- `input_chars`
- `output_chars`
- `estimated_cost_usd`
- `latency_ms`
- `prompt_hash`
- `prompt_summary`
- `response_hash`
- `response_summary`
- `created_at`

By default, DevPilot does not store the full prompt or full response in the usage log. It stores hashes and short summaries only.

## Safety Boundaries

This MVP does not support:

- Streaming.
- Tool calling.
- Image generation or editing.
- Video generation or editing.
- File writes.
- Worker execution.
- Task/project/phase mutation.
- Approval creation.
- Deploy/restart.
- DNS, SSL, Nginx, Cloudflare, or redirect changes.
- Raw provider key exposure.

External systems must continue to use External Project Registry, External Project Events, and External Handoff APIs for project status and handoff workflows.
