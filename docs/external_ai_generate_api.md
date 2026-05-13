# External AI Generate API

## Purpose

`POST /api/external/ai/generate` lets an approved external source system request a narrow text-only AI generation through DevPilot.

This MVP is intentionally small:

- Provider: Gemini only.
- Model: `gemini-1.5-flash` only.
- Mode: non-streaming text only.
- Capabilities: `generate`, `summary`, `rewrite`, `classification`, `extraction`, `planning`, `chat`.

DevPilot keeps provider credentials internal. External systems receive only a DevPilot external API key.

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
  "capability": "generate",
  "model": "gemini-1.5-flash",
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
  "provider": "gemini",
  "model": "gemini-1.5-flash",
  "capability": "generate",
  "text": "Generated text...",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 9,
    "total_tokens": 21
  },
  "estimated_cost_usd": null,
  "execution_allowed": false,
  "side_effects": false
}
```

## Required Source Policy

The authenticated `source_system` must have an enabled External AI Policy allowing:

- provider: `gemini`
- model: `gemini-1.5-flash`
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

DevPilot reads the Gemini provider key from:

- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`

If neither is configured, DevPilot returns:

```json
{
  "ok": false,
  "error": "provider_not_configured"
}
```

The provider key is never returned, logged, or exposed to external systems.

## Idempotency

Use `X-DevPilot-Idempotency-Key` for retry safety.

Behavior:

- A completed result for the same `source_system + idempotency_key` is replayed with `idempotent_replay=true`.
- Replayed responses do not call Gemini again.
- Failed results are recorded, but are not replayed. Retrying the same idempotency key after fixing the failure can call Gemini again.

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
