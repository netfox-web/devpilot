# External Project Events Guide

Use External Project Events when an external project wants to report build, deploy, domain, healthcheck, AI job, or usage status back to DevPilot.

Events are append-only status callbacks. They do not perform infrastructure actions.

## Authentication

Headers:

```text
X-DevPilot-Source-System: {DEVPILOT_SOURCE_SYSTEM}
X-DevPilot-Api-Key: {DEVPILOT_API_KEY}
X-DevPilot-Request-Id: {stable-request-id}
X-DevPilot-Idempotency-Key: {stable-idempotency-key}
```

## Create Event

```text
POST {DEVPILOT_API_BASE_URL}/api/external/projects/{external_project_id}/events
```

Request:

```json
{
  "event_type": "deploy_success",
  "status": "success",
  "message": "Production container deployed successfully",
  "environment": "production",
  "commit_sha": "abc123",
  "app_url": "https://adstudio.example.com",
  "metadata": {
    "container_name": "ad-studio-ai",
    "host_port": 5015
  }
}
```

## Read Events

```text
GET {DEVPILOT_API_BASE_URL}/api/external/projects/{external_project_id}/events
```

The authenticated source can only read events for its own registered projects.

## Supported Event Types

- `project_registered`
- `build_started`
- `build_success`
- `build_failed`
- `deploy_started`
- `deploy_success`
- `deploy_failed`
- `domain_requested`
- `domain_ready`
- `healthcheck_ok`
- `healthcheck_failed`
- `ai_job_started`
- `ai_job_completed`
- `ai_job_failed`
- `usage_reported`
- `custom`

## Supported Status Values

- `info`
- `pending`
- `running`
- `success`
- `warning`
- `failed`
- `blocked`

## Recommended Event Timing

- After project registration: `project_registered`
- Before build starts: `build_started`
- After successful build: `build_success`
- After failed build: `build_failed`
- Before deploy starts: `deploy_started`
- After deploy succeeds: `deploy_success`
- After deploy fails: `deploy_failed`
- After domain request is submitted for review: `domain_requested`
- After healthcheck succeeds: `healthcheck_ok`
- After healthcheck fails: `healthcheck_failed`

## Safety Boundaries

Events are status records only. They must not trigger:

- Deploy/restart.
- Docker writes.
- DNS/Cloudflare/SSL/Nginx/redirect changes.
- Provider calls.
- Worker execution.
- Approval creation.
- Normal DevPilot task/project/phase mutation.
