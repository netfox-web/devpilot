# External AI Usage API

## Purpose

The External AI Usage API provides read-only usage visibility for external systems that call DevPilot's External AI Gateway.

This slice adds visibility and budget warning groundwork only. It does not open new providers, models, capabilities, or hard budget enforcement.

## External Endpoint

```text
GET {DEVPILOT_API_BASE_URL}/api/external/ai/usage
```

Required headers:

```text
X-DevPilot-Source-System: {source_system}
X-DevPilot-Api-Key: {devpilot_external_api_key}
```

Each source system can only read its own usage records. Other source systems' records are not returned.

## Filters

Supported query parameters:

- `from`
- `to`
- `provider`
- `model`
- `capability`
- `status`
- `external_ref`

Example:

```text
GET /api/external/ai/usage?provider=gemini&model=gemini-1.5-flash&status=completed
```

## Response Example

```json
{
  "ok": true,
  "source_system": "ad-studio-ai",
  "count": 1,
  "items": [
    {
      "id": "aiusage_...",
      "source_system": "ad-studio-ai",
      "request_id": "req-123",
      "idempotency_key": "generate:ad-job-123",
      "external_ref": "ad-job-123",
      "provider": "gemini",
      "model": "gemini-1.5-flash",
      "capability": "summary",
      "status": "completed",
      "input_chars": 240,
      "output_chars": 120,
      "latency_ms": 950,
      "prompt_hash": "sha256...",
      "prompt_summary": "Short safe summary...",
      "response_hash": "sha256...",
      "response_summary": "Short safe summary...",
      "created_at": "2026-05-13 10:00:00"
    }
  ],
  "summary": {
    "total_requests": 1,
    "success_count": 1,
    "failed_count": 0,
    "total_input_chars": 240,
    "total_output_chars": 120,
    "total_latency_ms": 950,
    "average_latency_ms": 950,
    "estimated_cost_usd": null,
    "grouped_by_model": {
      "gemini-1.5-flash": {
        "total_requests": 1,
        "success_count": 1,
        "failed_count": 0,
        "input_chars": 240,
        "output_chars": 120
      }
    },
    "grouped_by_capability": {
      "summary": {
        "total_requests": 1,
        "success_count": 1,
        "failed_count": 0,
        "input_chars": 240,
        "output_chars": 120
      }
    }
  },
  "read_only": true,
  "execution_allowed": false,
  "side_effects": false
}
```

## Admin Dashboard

Admin page:

```text
/admin/external-ai-usage
```

The dashboard shows:

- usage table
- source system
- provider/model
- capability
- status
- external reference
- input/output chars
- latency
- created time
- prompt/response hashes
- safe prompt/response summaries

Admin filters:

- `q`
- `source_system`
- `provider`
- `model`
- `capability`
- `status`
- `from`
- `to`
- `external_ref`

## Prompt / Response Privacy

The API and admin dashboard do not expose full prompts or full responses by default.

They only expose fields already stored in the usage log:

- `prompt_hash`
- `prompt_summary`
- `response_hash`
- `response_summary`

## Budget Warning Groundwork

Slice 5B adds warning-only helpers:

- `daily_request_limit_near`
- `daily_request_limit_exceeded`
- `daily_token_limit_near`
- `daily_token_limit_exceeded`
- `monthly_budget_not_enforced_yet`

These warnings are advisory only. Hard budget and rate-limit enforcement is planned for Slice 5C.

## Safety Boundaries

This API and dashboard are read-only. They do not:

- call providers
- execute workers
- create approvals
- mutate task/project/phase state
- write DNS, SSL, Nginx, Cloudflare, redirects, Docker, or deployment configuration
- expose raw provider keys
- expose full prompts/responses by default
