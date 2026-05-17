# External AI Generate API

## Purpose

`POST /api/external/ai/generate` lets an approved external source system request a narrow text-only AI generation through DevPilot.

This MVP is intentionally small:

- Providers: Gemini by default, plus a Claude mocked/tested gateway path.
- Gemini model: `gemini-1.5-flash`.
- Claude model: `claude-3-5-haiku`.
- Mode: non-streaming text only.
- Capabilities: `generate`, `summary`, `rewrite`, `classification`, `extraction`, `planning`, `chat`.

DevPilot keeps provider credentials internal. External systems receive only a DevPilot external API key.

Claude support is not live-provider-enabled in this phase. The Claude gateway function is intentionally non-live unless patched in tests, so readiness can be verified without calling Anthropic.

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
  "provider": "gemini",
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
  "side_effects": false,
  "provider_calls_executed": true
}
```

## Required Source Policy

The authenticated `source_system` must have an enabled External AI Policy allowing:

- requested provider: `gemini` or `claude`
- requested model: `gemini-1.5-flash` or `claude-3-5-haiku`
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

DevPilot recognizes Claude provider keys from:

- `ANTHROPIC_API_KEY`
- `CLAUDE_API_KEY`

Claude keys are only checked for configured/missing state in this phase. The External AI Generate Claude implementation does not call Claude live unless a later phase explicitly enables that behavior.

If the requested provider key is not configured, DevPilot returns:

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
