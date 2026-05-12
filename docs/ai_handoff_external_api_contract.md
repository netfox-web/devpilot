# AI Handoff External API Contract

## Purpose

This contract defines how external systems can create and read AI-to-AI manual handoff records through DevPilot without writing directly to the database or triggering task execution.

External integrations may submit handoff requests and read their own handoff records. They must not mutate task or project workflow state, run providers, execute workers, create approval requests, or call legacy handoff paths.

## Authentication Model

External API endpoints use source-scoped API keys configured by environment variable:

```text
DEVPILOT_EXTERNAL_API_KEYS=source_system_1:key1,source_system_2:key2
```

If the variable is missing or empty, external API endpoints return `403`.

The source system in the request header must match a configured source, and the submitted API key must match that source's configured key. Raw keys are never returned by the API.

## Required Headers

| Header | Required | Purpose |
| --- | --- | --- |
| `X-DevPilot-Api-Key` | Yes | Source-scoped external API key. |
| `X-DevPilot-Source-System` | Yes | Configured external source system name. |
| `X-DevPilot-Request-Id` | Strongly recommended | Caller request/correlation id stored in the handoff payload. |
| `X-DevPilot-Idempotency-Key` | Strongly recommended for create | Replays create requests safely without duplicate handoff logs. |

## Supported Endpoints

| Method | Endpoint | Behavior |
| --- | --- | --- |
| `POST` | `/api/external/tasks/<task_id>/handoffs` | Create a side-effect-free manual handoff for an existing task. |
| `GET` | `/api/external/ai-handoffs` | List safe/redacted handoff records. |
| `GET` | `/api/external/handoffs/<handoff_id>` | Read one safe/redacted handoff record. |

External lifecycle mutation endpoints are intentionally not available in this slice. Accept, complete, and reject remain reviewer-controlled inside DevPilot.

## Create Request

```http
POST /api/external/tasks/123/handoffs
X-DevPilot-Api-Key: <source-scoped-key>
X-DevPilot-Source-System: external-system-a
X-DevPilot-Request-Id: req-2026-05-13-001
X-DevPilot-Idempotency-Key: external-ticket-123:create
Content-Type: application/json
```

```json
{
  "from_agent": "external-system-a",
  "to_agent": "devpilot-reviewer",
  "reason": "Manual review needed before continuing.",
  "next_step": "Review the external ticket and decide the handoff outcome.",
  "risk": "medium",
  "external_ref": "external-ticket-123",
  "actor_type": "system",
  "actor_id": "external-system-a"
}
```

## Create Response

New handoff:

```json
{
  "ok": true,
  "handoff_id": 456,
  "task_id": 123,
  "status": "pending",
  "conversation_ref": "ai-task:123",
  "source_system": "external-system-a",
  "external_ref": "external-ticket-123",
  "idempotency_key": "external-ticket-123:create",
  "idempotent_replay": false,
  "execution_allowed": false
}
```

Idempotent replay:

```json
{
  "ok": true,
  "handoff_id": 456,
  "task_id": 123,
  "status": "pending",
  "conversation_ref": "ai-task:123",
  "source_system": "external-system-a",
  "external_ref": "external-ticket-123",
  "idempotency_key": "external-ticket-123:create",
  "idempotent_replay": true,
  "execution_allowed": false
}
```

## Idempotency Behavior

When `X-DevPilot-Idempotency-Key` is provided, DevPilot searches existing non-hidden handoff logs for the same:

- `conversation_ref = ai-task:<task_id>`
- `api_payload.source_system`
- `api_payload.idempotency_key`

If a match exists, DevPilot returns `200` with the existing handoff and `idempotent_replay: true`. If no match exists, DevPilot creates a new handoff and returns `201` with `idempotent_replay: false`.

Invalid existing `api_payload` JSON is ignored safely during lookup and never crashes idempotency checks.

## Read Filters

`GET /api/external/ai-handoffs` supports:

- `q`
- `from_agent`
- `to_agent`
- `status`
- `risk`
- `risk_level`
- `source_system`
- `external_ref`

By default, an external source only sees records where `api_payload.source_system` matches its authenticated source.

Cross-source reads require:

```text
DEVPILOT_EXTERNAL_API_ALLOW_ALL_SOURCES=1
```

and request parameter:

```text
include_all_sources=true
```

Without both, DevPilot forces the `source_system` filter to the authenticated source and does not leak other external systems' records.

## Read Response Shape

Read endpoints return safe/redacted handoff objects with fields such as:

- `handoff_id`
- `conversation_ref`
- `task_id`
- `task_title`
- `project_id`
- `project_name`
- `project_status`
- `source_system`
- `external_ref`
- `request_id`
- `idempotency_key`
- `actor_type`
- `actor_id`
- `from_agent`
- `to_agent`
- `status`
- `risk`
- `reason`
- `next_step`
- `rejection_reason`
- lifecycle timestamps
- `api_payload_summary`

The raw full `api_payload` is not returned.

## Error Response Format

```json
{
  "ok": false,
  "error": "external API credential is invalid"
}
```

Typical status codes:

- `400`: invalid request or missing handoff fields.
- `403`: external API disabled, unknown source system, or invalid API key.
- `404`: task or handoff not found, including source-isolated handoff reads.

## Safety Boundaries

External API calls must remain side-effect-free except for handoff log creation.

Confirmed boundaries:

- Do not mutate task status.
- Do not mutate project status.
- Do not mutate project phase status, progress, or next steps.
- Do not call AI providers.
- Do not execute workers.
- Do not create approval requests.
- Do not use legacy `save_handoff()`.
- Do not expose raw configured API keys.
- Do not expose raw full `api_payload`.

## External Systems Must Not

- Write directly to DevPilot database tables.
- Implement their own lifecycle transition logic.
- Call internal lifecycle mutation endpoints unless a later contract explicitly allows it.
- Treat handoff creation as approval to execute work.
- Put secrets, tokens, credentials, or private keys into `reason`, `next_step`, `external_ref`, `request_id`, or `idempotency_key`.

## Production Integration Checklist

- Configure `DEVPILOT_EXTERNAL_API_KEYS` with one source-scoped key per external system.
- Keep `DEVPILOT_EXTERNAL_API_ALLOW_ALL_SOURCES` disabled unless cross-source audit access is explicitly required.
- Send all required headers on every request.
- Send stable `X-DevPilot-Request-Id` for tracing.
- Send stable `X-DevPilot-Idempotency-Key` for create retries.
- Use `risk` or `risk_level`; if both are provided, canonical `risk_level` wins.
- Verify create returns `execution_allowed: false`.
- Verify task/project fields remain unchanged after create.
- Verify list/detail only expose records for the authenticated source by default.
- Monitor logs for `403`, `400`, and idempotent replay behavior during rollout.
