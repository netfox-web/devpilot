# External Handoff API Guide

Use the External Handoff API when an external project needs DevPilot to record a review or AI handoff request.

This API is intentionally side-effect-free. It writes handoff records only. It does not execute workers, call providers, create approvals, or mutate task/project status.

## Authentication

Headers:

```text
X-DevPilot-Source-System: {DEVPILOT_SOURCE_SYSTEM}
X-DevPilot-Api-Key: {DEVPILOT_API_KEY}
X-DevPilot-Request-Id: {stable-request-id}
X-DevPilot-Idempotency-Key: {stable-idempotency-key}
```

## Create Handoff

```text
POST {DEVPILOT_API_BASE_URL}/api/external/tasks/{task_id}/handoffs
```

Request:

```json
{
  "from_agent": "ad-studio-ai",
  "to_agent": "devpilot-reviewer",
  "reason": "External project requests review before next step",
  "next_step": "Review context and decide whether a human handoff is needed",
  "risk": "medium",
  "external_ref": "ad-job-123",
  "actor_type": "system",
  "actor_id": "ad-studio-ai"
}
```

Success response:

```json
{
  "ok": true,
  "handoff_id": 123,
  "task_id": 456,
  "status": "pending",
  "conversation_ref": "ai-task:456",
  "source_system": "ad-studio-ai",
  "external_ref": "ad-job-123",
  "idempotency_key": "task-456-handoff-ad-job-123",
  "idempotent_replay": false
}
```

## Read Handoffs

```text
GET {DEVPILOT_API_BASE_URL}/api/external/ai-handoffs
GET {DEVPILOT_API_BASE_URL}/api/external/handoffs/{handoff_id}
```

Supported filters:

- `q`
- `from_agent`
- `to_agent`
- `status`
- `risk`
- `risk_level`
- `source_system`
- `external_ref`

By default, a source system can only see its own records.

## Idempotency

Use a stable `X-DevPilot-Idempotency-Key` for retries. A repeated create with the same source, task, and idempotency key returns the existing handoff rather than creating a duplicate.

## Safety Boundaries

External systems cannot accept, complete, or reject handoffs. Lifecycle actions remain controlled inside DevPilot.

This API must not be used for:

- Provider calls.
- Worker execution.
- Task/project mutation.
- Approval creation.
- DNS, SSL, Nginx, Cloudflare, redirect, deploy, restart, or Docker actions.
