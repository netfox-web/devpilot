# External Project Admin Integration Instructions

## Purpose

Every external project should provide a server-side DevPilot integration settings page so an admin can connect the project to DevPilot without exposing provider keys or raw secrets. The standard page is:

```text
/admin/integrations/devpilot
```

This page stores the DevPilot connection settings, tests the connection, registers project metadata, and sends project lifecycle events back to DevPilot.

## Required Settings

The external project must support these settings:

```text
DEVPILOT_API_BASE_URL=https://YOUR_DEVPILOT_DOMAIN
DEVPILOT_SOURCE_SYSTEM=your-source-system
DEVPILOT_API_KEY=<paste-the-key-shown-once>
```

The DevPilot API key is a DevPilot-issued external API key. It is not an OpenAI, Gemini, Claude, Replicate, fal, Cloudflare, DNS, or infrastructure credential.

## Optional Project Metadata

Projects should also support these optional fields when available:

```text
EXTERNAL_PROJECT_ID=
PROJECT_NAME=
APP_URL=
PRIMARY_DOMAIN=
LOCAL_PATH=
NAS_WORKTREE_PATH=
NAS_COMPOSE_PATH=
CONTAINER_NAME=
COMPOSE_PROJECT=
SERVICE_NAME=
HOST_PORT=
CONTAINER_PORT=
REPO_URL=
BRANCH=
DEPLOYMENT_TARGET=
RUNTIME=
OWNER=
NOTES=
```

Use a stable `EXTERNAL_PROJECT_ID` for each environment. Repeated registration with the same `DEVPILOT_SOURCE_SYSTEM` and `EXTERNAL_PROJECT_ID` updates the existing DevPilot registry record instead of creating duplicates.

## Security Rules

The external project must treat `DEVPILOT_API_KEY` as a server-side secret:

- API key is entered once.
- Never show the full key again after saving.
- Show only a masked value or short prefix.
- Do not log the key.
- Do not expose the key to browser/client-side JavaScript.
- Do not commit the key to Git.
- Store the key server-side only.
- Support rotating the key.
- Support disabling the DevPilot integration.
- Test connection responses must not print the secret.

External projects must never receive or store raw provider keys:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `ANTHROPIC_API_KEY`
- `CLAUDE_API_KEY`
- `REPLICATE_API_TOKEN`
- `FAL_KEY`

## Admin Page Actions

The `/admin/integrations/devpilot` page should support:

- Save settings.
- Test connection.
- Register project.
- Send event.
- Rotate key.
- Disable integration.
- Show last connection test time.
- Show last registration time.
- Show last event status.

All actions must be server-side. Do not send `DEVPILOT_API_KEY` to frontend JavaScript.

## DevPilot API Endpoints

### Test Connection

```text
GET /api/external/projects
```

Required headers:

```text
X-DevPilot-Source-System: <source-system>
X-DevPilot-Api-Key: <paste-the-key-shown-once>
```

Expected result:

- `200` when source/key are valid.
- `403` when the key is missing, wrong, revoked, or paired with the wrong source.

### Register Project

```text
POST /api/external/projects/register
```

Required headers:

```text
Content-Type: application/json
X-DevPilot-Source-System: <source-system>
X-DevPilot-Api-Key: <paste-the-key-shown-once>
X-DevPilot-Request-Id: <stable-request-id>
X-DevPilot-Idempotency-Key: register:<external-project-id>
```

Example body:

```json
{
  "external_project_id": "project-prod",
  "name": "External Project",
  "project_type": "ai-saas",
  "environment": "production",
  "status": "active",
  "repo_url": "https://github.com/example/project",
  "branch": "main",
  "local_path": "E:\\Ai-project\\ExternalProject",
  "nas_worktree_path": "/volume1/worktrees/external-project",
  "nas_compose_path": "/volume1/docker/external-project",
  "container_name": "external-project",
  "compose_project": "external-project",
  "service_name": "app",
  "host_port": 5015,
  "container_port": 5000,
  "app_url": "https://project.example.com",
  "primary_domain": "project.example.com",
  "requested_domains": ["project.example.com"],
  "deployment_target": "nas-docker",
  "runtime": "docker",
  "owner": "team-name",
  "notes": "Registered from project admin DevPilot integration"
}
```

Domain fields are review-only in this workflow. Registering a project does not change DNS, Cloudflare, SSL, Nginx, redirects, Docker, R2, or infrastructure.

### Send Project Event

```text
POST /api/external/projects/<external_project_id>/events
```

Example body:

```json
{
  "event_type": "deploy_success",
  "status": "success",
  "message": "Production container deployed successfully",
  "environment": "production",
  "commit_sha": "abc123",
  "app_url": "https://project.example.com",
  "metadata": {
    "container_name": "external-project",
    "host_port": 5015
  }
}
```

Supported event types include build, deploy, domain, healthcheck, AI job, usage, and `custom` events.

### Generate Text Through DevPilot AI Gateway

```text
POST /api/external/ai/generate
```

Required headers are the same DevPilot external integration headers:

```text
Content-Type: application/json
X-DevPilot-Source-System: <source-system>
X-DevPilot-Api-Key: <paste-the-key-shown-once>
X-DevPilot-Request-Id: <stable-request-id>
X-DevPilot-Idempotency-Key: ai-generate:<stable-job-id>
```

Example body:

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "capability": "generate",
  "prompt": "Write a short product summary.",
  "external_ref": "external-job-123",
  "metadata": {
    "project": "External Project"
  }
}
```

Supported text gateway providers:

- `openai` with `gpt-4.1-mini` or `gpt-4o-mini`
- `gemini` with `gemini-2.5-flash`
- `claude` with `claude-haiku-4-5-20251001`

Legacy request values are accepted for compatibility and resolved inside DevPilot to the current upstream model IDs:

- `gemini-1.5-flash` -> `gemini-2.5-flash`
- `claude-3-5-haiku` -> `claude-haiku-4-5-20251001`
- `claude-3-5-haiku-20241022` -> `claude-haiku-4-5-20251001`

New integrations should use the current IDs listed above.

Candidate / Future Models shown in DevPilot admin are not available to external projects until DevPilot completes Gateway model onboarding: backend allowlist, adapter compatibility, tests/docs, NAS deployment approval, and one-provider-at-a-time live smoke approval. Do not configure external projects to call candidate model IDs before DevPilot marks them active.

DevPilot must first enable an External AI Policy for the source system with the requested provider, model, and capability. If no enabled policy exists, the gateway returns `external_ai_policy_not_enabled`.

Do not put raw provider keys in the external project. The external project should never request, store, log, or display `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `CLAUDE_API_KEY`.

Required safety:

- Use a stable `X-DevPilot-Idempotency-Key` for retries.
- Never expose `DEVPILOT_API_KEY` to frontend JavaScript.
- Never log provider keys.
- Never log DevPilot API keys.
- Never log prompts that contain secrets.
- Never log full `Authorization` or `X-DevPilot-*` auth headers.
- Do not call raw OpenAI/Gemini/Claude APIs directly from external projects.

## Safe Environment Template

```dotenv
DEVPILOT_API_BASE_URL=https://YOUR_DEVPILOT_DOMAIN
DEVPILOT_SOURCE_SYSTEM=your-source-system
DEVPILOT_API_KEY=<paste-the-key-shown-once>

EXTERNAL_PROJECT_ID=project-prod
PROJECT_NAME=External Project
APP_URL=https://project.example.com
PRIMARY_DOMAIN=project.example.com
```

Do not commit a filled `.env` file.

## JavaScript Fetch Example

This example is for server-side JavaScript only.

```js
import crypto from "node:crypto";

const baseUrl = (process.env.DEVPILOT_API_BASE_URL || "").replace(/\/+$/, "");
const sourceSystem = process.env.DEVPILOT_SOURCE_SYSTEM || "";
const apiKey = process.env.DEVPILOT_API_KEY || "";

function requireSetting(value, name) {
  if (!value || value.includes("paste-the-key") || value.startsWith("YOUR_")) {
    throw new Error(`${name} is not configured`);
  }
  return value;
}

async function devpilotFetch(path, { method = "GET", body, idempotencyKey } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${requireSetting(baseUrl, "DEVPILOT_API_BASE_URL")}${path}`, {
      method,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "X-DevPilot-Source-System": requireSetting(sourceSystem, "DEVPILOT_SOURCE_SYSTEM"),
        "X-DevPilot-Api-Key": requireSetting(apiKey, "DEVPILOT_API_KEY"),
        "X-DevPilot-Request-Id": crypto.randomUUID(),
        "X-DevPilot-Idempotency-Key": idempotencyKey || crypto.randomUUID()
      },
      body: body ? JSON.stringify(body) : undefined
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || `DevPilot request failed with ${response.status}`);
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}
```

Never log `apiKey` or include it in client-side bundles.

## Python Requests Example

```python
import os
import uuid

import requests

BASE_URL = os.getenv("DEVPILOT_API_BASE_URL", "").rstrip("/")
SOURCE_SYSTEM = os.getenv("DEVPILOT_SOURCE_SYSTEM", "")
API_KEY = os.getenv("DEVPILOT_API_KEY", "")
TIMEOUT_SECONDS = 15


def require_setting(value, name):
    if not value or "paste-the-key" in value or value.startswith("YOUR_"):
        raise RuntimeError(f"{name} is not configured")
    return value


def devpilot_request(method, path, payload=None, idempotency_key=None):
    response = requests.request(
        method,
        f"{require_setting(BASE_URL, 'DEVPILOT_API_BASE_URL')}{path}",
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-DevPilot-Source-System": require_setting(SOURCE_SYSTEM, "DEVPILOT_SOURCE_SYSTEM"),
            "X-DevPilot-Api-Key": require_setting(API_KEY, "DEVPILOT_API_KEY"),
            "X-DevPilot-Request-Id": str(uuid.uuid4()),
            "X-DevPilot-Idempotency-Key": idempotency_key or str(uuid.uuid4()),
        },
        timeout=TIMEOUT_SECONDS,
    )
    body = response.json() if response.content else {}
    if not response.ok:
        raise RuntimeError(body.get("error") or f"DevPilot request failed with {response.status_code}")
    return body
```

Do not print `API_KEY` in logs, tracebacks, or admin status output.

## Safety Boundaries

The external project integration must not:

- Share provider keys with the external project.
- Call OpenAI, Gemini, Claude, Replicate, or fal directly using DevPilot provider keys.
- Trigger worker execution.
- Write DNS, Cloudflare, R2, SSL, Nginx, redirects, Docker, or infrastructure changes.
- Mutate DevPilot task/project/phase state except the expected external registry/event records.
- Create approvals automatically.

## Troubleshooting

| Symptom | Likely cause | Safe fix |
| --- | --- | --- |
| `403` | Wrong key, wrong source, revoked key, or missing headers. | Confirm `DEVPILOT_SOURCE_SYSTEM`, rotate key if needed, and re-enter the key server-side. |
| `404` | Wrong `DEVPILOT_API_BASE_URL` or endpoint path. | Trim trailing slash and verify the DevPilot base URL. |
| `422` | Invalid request payload. | Check required fields, enum values, and domain/path formatting. |
| `500` | DevPilot application error. | Check DevPilot diagnostics and server logs without printing secrets. |
| Key active but external project fails | Key was not saved, saved in the wrong environment, or source mismatch. | Re-save settings and test connection. |
| Source mismatch | Header source does not match the managed key's source system. | Use the exact DevPilot `source_system` value. |

Use DevPilot admin pages for diagnosis:

- `/admin/external-api-keys`
- `/admin/external-integration-diagnostics`
- `/admin/external-sources`
- `/admin/external-projects`
