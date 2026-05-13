# External AI Gateway Future API Guide

The External AI Gateway will let approved external projects call AI capabilities through DevPilot without receiving raw provider keys.

Current status: future/provider-call behavior is policy-gated and should be treated as disabled unless DevPilot explicitly enables it for the source system.

## Why Use DevPilot As The AI Gateway

- Provider keys never leave DevPilot.
- Source systems can be revoked independently.
- Provider/model/capability access is centrally controlled.
- Usage and cost can be audited.
- Budgets and token limits can be enforced.
- Provider/model changes do not require external project code changes.

## Future Generate Endpoint

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
  "capability": "summary",
  "model": "gemini-1.5-flash",
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
  "provider": "gemini",
  "model": "gemini-1.5-flash",
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
