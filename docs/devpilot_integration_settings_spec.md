# DevPilot Integration Settings Spec

## Purpose

Every external project should provide a DevPilot Integration settings page so it can register itself with DevPilot, report project status, create handoff requests, and later use the External AI Gateway through one DevPilot-issued key.

DevPilot is the central place for project registry, local/NAS paths, repo and container metadata, app URLs, domains, deployment status, events/status callbacks, handoff requests, and future AI Gateway policy/audit controls.

## Required Admin Page In Each Project

Recommended project-side admin page:

```text
/admin/integrations/devpilot
```

Required fields:

- `DEVPILOT_API_BASE_URL`
- `DEVPILOT_SOURCE_SYSTEM`
- `DEVPILOT_API_KEY`

Optional project metadata fields:

- `EXTERNAL_PROJECT_ID`
- `PROJECT_NAME`
- `ENVIRONMENT`
- `LOCAL_PATH`
- `NAS_WORKTREE_PATH`
- `NAS_COMPOSE_PATH`
- `NAS_DATA_PATH`
- `REPO_URL`
- `BRANCH`
- `CONTAINER_NAME`
- `COMPOSE_PROJECT`
- `SERVICE_NAME`
- `HOST_PORT`
- `CONTAINER_PORT`
- `APP_URL`
- `PRIMARY_DOMAIN`
- `REQUESTED_DOMAINS`
- `DEPLOYMENT_TARGET`
- `RUNTIME`
- `OWNER`
- `NOTES`

## Key Storage Rules

- The DevPilot API key is entered once.
- After saving, never show the full key again.
- Show only a masked value or safe prefix.
- Do not log the key.
- Do not expose the key to browser/client-side JavaScript.
- Do not commit the key to the repository.
- Store the key server-side only.
- Support key rotation.
- Support disabling the integration.
- Test connection must not print or return the secret.

External projects receive only a DevPilot external API key. They must never receive raw provider keys such as:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `CLAUDE_API_KEY`
- `REPLICATE_API_TOKEN`
- `FAL_KEY`

## DevPilot-Side Setup Flow

1. Open DevPilot External API Keys and create a `source_system`.
2. Generate a one-time DevPilot external API key.
3. Open External AI Policies, select the same `source_system`, and apply a permission profile.
4. After the project registers itself, review it under External Projects.
5. Download the integration document if available.
6. Give only the DevPilot URL, `source_system`, and generated DevPilot key to the project.

Provider keys remain inside DevPilot. External systems never receive OpenAI, Gemini, Claude, Replicate, or fal credentials.

## Project-Side Setup Flow

1. Admin opens `/admin/integrations/devpilot` in the external project.
2. Admin enters the DevPilot API base URL.
3. Admin enters the assigned `source_system`.
4. Admin enters the one-time DevPilot API key.
5. Save settings.
6. Test connection.
7. Register the project.
8. Send project events/status updates.

## Test Connection

Endpoint:

```text
GET {DEVPILOT_API_BASE_URL}/api/external/projects
```

Headers:

```text
X-DevPilot-Source-System: {DEVPILOT_SOURCE_SYSTEM}
X-DevPilot-Api-Key: {DEVPILOT_API_KEY}
```

Expected result:

- `200` when the source/key pair is valid.
- `403` when the key is missing, wrong, revoked, or not configured.

## Register Project

Endpoint:

```text
POST {DEVPILOT_API_BASE_URL}/api/external/projects/register
```

Headers:

```text
Content-Type: application/json
X-DevPilot-Source-System: {DEVPILOT_SOURCE_SYSTEM}
X-DevPilot-Api-Key: {DEVPILOT_API_KEY}
X-DevPilot-Request-Id: {stable-request-id}
X-DevPilot-Idempotency-Key: {stable-idempotency-key}
```

Example for `AD-Studio_AI`:

```json
{
  "external_project_id": "ad-studio-ai-prod",
  "name": "AD-Studio_AI",
  "description": "AI ad creative/image generation platform",
  "project_type": "ai-saas",
  "environment": "production",
  "status": "active",
  "owner": "chaokun",
  "repo_url": "https://github.com/netfox-web/ad-studio-ai",
  "branch": "main",
  "commit_sha": "<current-commit>",
  "local_path": "E:\\Ai-project\\AD-Studio_AI",
  "nas_worktree_path": "/volume1/worktrees/ad-studio-ai",
  "nas_compose_path": "/volume1/docker/ad-studio-ai",
  "nas_data_path": "/volume1/docker/ad-studio-ai/data",
  "container_name": "ad-studio-ai",
  "compose_project": "ad-studio-ai",
  "service_name": "app",
  "host_port": 5015,
  "container_port": 5000,
  "app_url": "https://adstudio.example.com",
  "primary_domain": "adstudio.example.com",
  "requested_domains": [
    "adstudio.example.com",
    "www.adstudio.example.com"
  ],
  "deployment_target": "nas-docker",
  "runtime": "docker",
  "healthcheck_url": "https://adstudio.example.com/health",
  "notes": "Registered from project admin DevPilot integration"
}
```

Notes:

- `source_system + external_project_id` should be stable.
- Repeated registration updates the existing DevPilot record instead of creating duplicates.
- Domain fields are review-only.
- Registering a project does not perform DNS, Cloudflare, Nginx, SSL, redirect, deploy, or restart changes.

## Send Project Events

Endpoint:

```text
POST {DEVPILOT_API_BASE_URL}/api/external/projects/{external_project_id}/events
```

Supported `event_type` examples:

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

Request example:

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

## Create Handoff To DevPilot

Endpoint:

```text
POST {DEVPILOT_API_BASE_URL}/api/external/tasks/{task_id}/handoffs
```

Use this when the external project wants DevPilot review or an AI-to-AI handoff entry. The handoff API is side-effect-free: it does not execute workers, call providers, create approvals, or mutate project/task status.

## Future AI Gateway

Future endpoint:

```text
POST {DEVPILOT_API_BASE_URL}/api/external/ai/generate
```

External projects can call AI only after DevPilot enables a source policy. Provider, model, capability, token limits, budgets, and audit behavior are controlled centrally by DevPilot.

Permanent defaults:

- Provider keys are never shared.
- No tool calling by default.
- No worker execution by default.
- No project/task mutation by default.
- Usage, budget, and audit controls stay in DevPilot.

## Recommended Project Behavior

Each external project should implement:

- Save DevPilot settings.
- Test connection.
- Register project now.
- Send event/status update.
- Rotate key.
- Disable integration.
- Show last connection test time.
- Show last registration time.
- Show last event status.
- Use stable idempotency keys.
- Retry only safe/retryable failures.

## JavaScript Example

```js
import crypto from "node:crypto";

function normalizeBaseUrl(value) {
  const text = String(value || "").trim().replace(/\/+$/, "");
  if (!text) throw new Error("DEVPILOT_API_BASE_URL is required");
  return text;
}

function requireSetting(name, value) {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

export async function registerWithDevPilot(settings, project) {
  const baseUrl = normalizeBaseUrl(settings.DEVPILOT_API_BASE_URL);
  const sourceSystem = requireSetting("DEVPILOT_SOURCE_SYSTEM", settings.DEVPILOT_SOURCE_SYSTEM);
  const apiKey = requireSetting("DEVPILOT_API_KEY", settings.DEVPILOT_API_KEY);
  const externalProjectId = requireSetting("EXTERNAL_PROJECT_ID", project.external_project_id);
  const requestId = crypto.randomUUID();
  const idempotencyKey = `register:${sourceSystem}:${externalProjectId}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);

  try {
    const response = await fetch(`${baseUrl}/api/external/projects/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-DevPilot-Source-System": sourceSystem,
        "X-DevPilot-Api-Key": apiKey,
        "X-DevPilot-Request-Id": requestId,
        "X-DevPilot-Idempotency-Key": idempotencyKey
      },
      body: JSON.stringify(project),
      signal: controller.signal
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(`DevPilot registration failed: ${response.status} ${payload.error || "unknown_error"}`);
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}
```

Do not log `apiKey` or include it in thrown errors.

## Python Example

```python
import uuid
import requests


def register_with_devpilot(settings, project):
    base_url = settings["DEVPILOT_API_BASE_URL"].rstrip("/")
    source_system = settings["DEVPILOT_SOURCE_SYSTEM"].strip()
    api_key = settings["DEVPILOT_API_KEY"].strip()
    external_project_id = project["external_project_id"]

    if not base_url or not source_system or not api_key or not external_project_id:
        raise ValueError("DevPilot integration settings are incomplete")

    headers = {
        "Content-Type": "application/json",
        "X-DevPilot-Source-System": source_system,
        "X-DevPilot-Api-Key": api_key,
        "X-DevPilot-Request-Id": str(uuid.uuid4()),
        "X-DevPilot-Idempotency-Key": f"register:{source_system}:{external_project_id}",
    }

    response = requests.post(
        f"{base_url}/api/external/projects/register",
        json=project,
        headers=headers,
        timeout=10,
    )
    if response.status_code >= 400:
        try:
            error_code = response.json().get("error", "unknown_error")
        except ValueError:
            error_code = "unknown_error"
        raise RuntimeError(f"DevPilot registration failed: {response.status_code} {error_code}")
    return response.json()
```

Do not log `api_key`, headers, or raw settings.

## Security Checklist

- Do not expose the DevPilot key to frontend JavaScript.
- Do not log the DevPilot key.
- Do not commit the key.
- Use HTTPS for production.
- Use a stable `source_system`.
- Use stable idempotency keys for retries.
- Rotate the key if leaked.
- Disable the integration if unused.
- Do not request DNS/deploy automation from the project side.
- Treat domain changes as review-only until approval-gated automation exists.

## Rollout Checklist For Each Project

- DevPilot external key generated.
- Policy profile applied.
- Integration settings saved server-side.
- Connection test passed.
- Project registered.
- First event sent.
- Project appears in `/admin/external-projects`.
- Domain request is visible for review.
- Full raw key is not shown after save.
