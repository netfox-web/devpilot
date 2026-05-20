# External AI Gateway API Guide

The External AI Gateway lets approved external projects call GPT, Gemini, and Claude text capabilities through DevPilot without receiving raw provider keys.

Current status: active for policy-gated text generation through `POST /api/external/ai/generate`. A source system must have an enabled External AI Policy before provider calls are allowed.

## Why Use DevPilot As The AI Gateway

- Provider keys never leave DevPilot.
- Source systems can be revoked independently.
- Provider/model/capability access is centrally controlled.
- Usage and cost can be audited.
- Budgets and token limits can be enforced.
- Provider/model changes do not require external project code changes.

## Generate Endpoint

```text
POST {DEVPILOT_API_BASE_URL}/api/external/ai/generate
```

Headers:

```text
Content-Type: application/json
X-DevPilot-Source-System: {DEVPILOT_SOURCE_SYSTEM}
X-DevPilot-Api-Key: {DEVPILOT_API_KEY}
X-DevPilot-Request-Id: {stable-request-id}
X-DevPilot-Idempotency-Key: {stable-idempotency-key}
```

Example request:

```json
{
  "provider": "openai",
  "capability": "summary",
  "model": "gpt-4.1-mini",
  "prompt": "Summarize this product update for a marketing dashboard.",
  "external_ref": "ad-job-123",
  "metadata": {
    "project": "AD-Studio_AI"
  }
}
```

Example response:

```json
{
  "ok": true,
  "source_system": "ad-studio-ai",
  "request_id": "req-123",
  "idempotency_key": "ai-generate-ad-job-123",
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "capability": "summary",
  "text": "Short generated response...",
  "usage": {
    "input_tokens": 100,
    "output_tokens": 80,
    "total_tokens": 180
  },
  "estimated_cost_usd": null,
  "execution_allowed": false,
  "side_effects": false
}
```

## Required DevPilot Policy

Before an external project can use the gateway, DevPilot must have an enabled source policy for that `source_system`.

The policy controls:

- Allowed providers.
- Allowed models.
- Allowed capabilities.
- Max tokens per request.
- Daily request limit.
- Daily token limit.
- Monthly budget.
- Streaming allowed or disabled.
- Tool calling allowed or disabled.
- Prompt/response retention behavior.

Supported text gateway providers and models:

- OpenAI/GPT: `gpt-4.1-mini`, `gpt-4o-mini`
- Gemini: `gemini-2.5-flash`
- Claude: `claude-haiku-4-5-20251001`

Compatibility aliases:

- `gemini-1.5-flash` is accepted as a legacy request value and resolved inside DevPilot to `gemini-2.5-flash`.
- `claude-3-5-haiku` and retired dated value `claude-3-5-haiku-20241022` are accepted as legacy request values and resolved inside DevPilot to `claude-haiku-4-5-20251001`.

Prefer the current model IDs above for new integrations.

If `provider` is omitted, DevPilot defaults to Gemini for compatibility with the original MVP. New integrations should send the provider explicitly.

## Three Files To Give An External Project

For a project that needs GPT/Gemini/Claude through DevPilot, give the project these files:

1. `external_project_admin_integration_instructions.md`
2. `external_ai_gateway_future_api_guide.md`
3. One server-side client helper:
   - `devpilot_external_client.js` for Node.js projects
   - or `devpilot_external_client.py` for Python projects

The project also needs:

```text
DEVPILOT_API_BASE_URL
DEVPILOT_SOURCE_SYSTEM
DEVPILOT_API_KEY
```

It must not receive raw provider keys.

## Minimal AI Generate Instruction For External Projects

```text
Use DevPilot as the AI Gateway. Do not call OpenAI, Gemini, or Claude directly with raw provider keys. Store DEVPILOT_API_BASE_URL, DEVPILOT_SOURCE_SYSTEM, and DEVPILOT_API_KEY server-side only. Call POST /api/external/ai/generate with provider openai, gemini, or claude. Use a stable X-DevPilot-Idempotency-Key for retries. Never log DEVPILOT_API_KEY or prompt/response secrets.
```

Required safety:

- Never expose `DEVPILOT_API_KEY` to frontend JavaScript.
- Never log provider keys.
- Never log DevPilot API keys.
- Never log prompts that contain secrets.
- Never log full `Authorization` or `X-DevPilot-*` auth headers.
- Do not call raw OpenAI/Gemini/Claude APIs directly from external projects.

## Safety Defaults

- No raw provider key exposure.
- No unlimited model access.
- No tool calling by default.
- No streaming by default.
- No worker execution.
- No file writes.
- No deploy/restart.
- No DNS/SSL/Nginx/Cloudflare/redirect changes.
- No project/task mutation.
- Prompt/response storage defaults to hash and short summary only.

## Provider Keys

External projects must never receive:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `ANTHROPIC_API_KEY`
- `CLAUDE_API_KEY`
- `REPLICATE_API_TOKEN`
- `FAL_KEY`

They receive only:

- `DEVPILOT_API_BASE_URL`
- `DEVPILOT_SOURCE_SYSTEM`
- `DEVPILOT_API_KEY`
