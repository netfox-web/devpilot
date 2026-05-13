# External Project Registry API

## Purpose

The External Project Registry lets trusted external AI projects register project metadata in DevPilot. DevPilot can then review project ownership, repositories, runtime paths, containers, app URLs, requested domains, and deployment targets from one place.

This registry is metadata-only. It does not perform DNS, Cloudflare, SSL, Nginx, redirect, Docker, deploy, restart, or infrastructure writes.

## Authentication

Use the same DevPilot-issued external API key model as the External AI Handoff API.

Required headers:

```http
X-DevPilot-Source-System: ai-image-site
X-DevPilot-Api-Key: <devpilot-issued-key>
X-DevPilot-Request-Id: req-001
X-DevPilot-Idempotency-Key: ai-image-site-prod:register:v1
```

External systems must not receive raw OpenAI, Gemini, Claude, Replicate, fal, DNS, Cloudflare, SSH, Docker, or infrastructure credentials.

## Register Or Update Project

```http
POST /api/external/projects/register
Content-Type: application/json
```

Example request:

```json
{
  "external_project_id": "ai-image-site-prod",
  "name": "AI Image Site",
  "description": "AI image generation website",
  "project_type": "ai-saas",
  "environment": "production",
  "status": "active",
  "repo_url": "https://github.com/example/ai-image-site",
  "branch": "main",
  "commit_sha": "abc123",
  "local_path": "E:\\Ai-project\\ai-image-site",
  "nas_worktree_path": "/volume1/worktrees/ai-image-site",
  "nas_compose_path": "/volume1/docker/ai-image-site/docker-compose.yml",
  "nas_data_path": "/volume1/docker/ai-image-site/data",
  "container_name": "ai-image-site",
  "compose_project": "ai-image-site",
  "service_name": "web",
  "host_port": "5080",
  "container_port": "3000",
  "app_url": "https://image.example.com",
  "requested_domains": [
    "image.example.com",
    "www.image.example.com"
  ],
  "primary_domain": "image.example.com",
  "deployment_target": "nas-docker",
  "runtime": "node/python/docker",
  "healthcheck_url": "https://image.example.com/health",
  "owner": "client/team name",
  "notes": "Needs domain pointing later"
}
```

Identity is `source_system + external_project_id`. Re-registering the same project updates safe fields and does not create a duplicate.

Example response:

```json
{
  "ok": true,
  "created": true,
  "updated": false,
  "source_system": "ai-image-site",
  "project": {
    "source_system": "ai-image-site",
    "external_project_id": "ai-image-site-prod",
    "name": "AI Image Site",
    "environment": "production",
    "status": "active",
    "requested_domains": ["image.example.com", "www.image.example.com"],
    "domain_status": "review_needed",
    "dns_action_required": true
  },
  "infra_actions_executed": false,
  "provider_calls_executed": false,
  "worker_execution": false,
  "approval_created": false
}
```

## Read Projects

```http
GET /api/external/projects
GET /api/external/projects/<external_project_id>
```

By default, a source system can only see its own records. Cross-source reads require `DEVPILOT_EXTERNAL_API_ALLOW_ALL_SOURCES=1` and `include_all_sources=true`.

## Project Events / Status Callback API

External projects can report lifecycle events back to DevPilot after they are registered.

```http
POST /api/external/projects/<external_project_id>/events
GET /api/external/projects/<external_project_id>/events
```

Example event:

```json
{
  "event_type": "deploy_success",
  "status": "success",
  "message": "Production deployment finished.",
  "environment": "production",
  "commit_sha": "abc123",
  "app_url": "https://image.example.com",
  "metadata": {
    "deployment_id": "deploy-20260513-001",
    "duration_seconds": 42
  }
}
```

Supported `event_type` values:

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

Supported `status` values:

- `info`
- `pending`
- `running`
- `success`
- `warning`
- `failed`
- `blocked`

Events are stored in `data/external_project_events.json`. A source system can only write or read events for projects registered under its own `source_system`.

## Domain Fields Are Review-Only

The registry records:

- `requested_domains`
- `primary_domain`
- `domain_status`: `requested`, `review_needed`, `approved`, `pointed`, `blocked`
- `dns_action_required`
- `domain_notes`

These fields do not perform DNS or infrastructure changes. A human review workflow must approve any future DNS/domain pointing work.

## AD-Studio_AI Example

```json
{
  "external_project_id": "ad-studio-ai-prod",
  "name": "AD-Studio_AI",
  "project_type": "ai-saas",
  "environment": "production",
  "status": "active",
  "repo_url": "https://github.com/example/ad-studio-ai",
  "nas_worktree_path": "/volume1/worktrees/ad-studio-ai",
  "nas_compose_path": "/volume1/docker/ad-studio-ai/docker-compose.yml",
  "container_name": "ad-studio-ai",
  "compose_project": "ad-studio-ai",
  "service_name": "web",
  "app_url": "https://adstudio.example.com",
  "requested_domains": ["adstudio.example.com"],
  "deployment_target": "nas-docker",
  "runtime": "node/python/docker",
  "notes": "Register metadata only; domain pointing requires later review."
}
```

## Safety Boundaries

- No DNS writes.
- No Cloudflare writes.
- No SSL or certificate changes.
- No Nginx or redirect changes.
- No Docker, deploy, restart, or prune actions.
- No AI provider calls.
- No worker execution.
- No approval creation.
- No mutation of unrelated DevPilot project, task, or phase records.
