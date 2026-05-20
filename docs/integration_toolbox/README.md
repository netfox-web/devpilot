# DevPilot Integration Toolbox

This toolbox is the standard package for every external project that needs to connect back to DevPilot.

DevPilot should be the shared registry, event hub, handoff center, and AI Gateway policy point. External projects receive DevPilot-issued external API keys only. They must not receive raw OpenAI, Gemini, Claude, Replicate, or fal provider keys.

## Toolbox Contents

1. DevPilot Integration Settings Spec
   - Canonical spec: `../devpilot_integration_settings_spec.md`
   - Purpose: implement `/admin/integrations/devpilot` in every external project.

2. External Handoff API Guide
   - File: `external_handoff_api_guide.md`
   - Purpose: let external systems create/read DevPilot handoff requests safely.

3. External Project Registry API Guide
   - Canonical guide: `../external_project_registry_api.md`
   - Purpose: let projects report local/NAS/repo/container/domain metadata.

4. External Project Events Guide
   - File: `external_project_events_guide.md`
   - Purpose: report build/deploy/domain/healthcheck/AI job status callbacks.

5. External AI Gateway API Guide
   - File: `external_ai_gateway_future_api_guide.md`
   - Purpose: explain policy-gated GPT, Gemini, and Claude text generation through DevPilot.

6. JavaScript Client Example
   - File: `devpilot_external_client.js`
   - Purpose: server-side Node.js helper for test/register/event/handoff calls.

7. Python Client Example
   - File: `devpilot_external_client.py`
   - Purpose: server-side Python helper for test/register/event/handoff calls.

8. Environment Template
   - File: `devpilot.env.example`
   - Purpose: standard environment names for external project integration.

## AI Gateway Quick Handoff

When another project needs to use GPT/Gemini/Claude through DevPilot, give it these three files:

1. `external_project_admin_integration_instructions.md`
2. `external_ai_gateway_future_api_guide.md`
3. One server-side client helper:
   - `devpilot_external_client.js` for Node.js
   - or `devpilot_external_client.py` for Python

Also issue that project a DevPilot external API key and source system. Do not give it raw `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `CLAUDE_API_KEY`.

Operator instruction:

```text
Use DevPilot as the AI Gateway. Store DEVPILOT_API_BASE_URL, DEVPILOT_SOURCE_SYSTEM, and DEVPILOT_API_KEY server-side only. Call POST /api/external/ai/generate with provider openai, gemini, or claude after DevPilot has enabled an External AI Policy for your source_system. Never request or store raw provider keys.
```

Required safety:

- Use a stable `X-DevPilot-Idempotency-Key` for retries.
- Never expose `DEVPILOT_API_KEY` to frontend JavaScript.
- Never log provider keys.
- Never log DevPilot API keys.
- Never log prompts that contain secrets.
- Never log full `Authorization` or `X-DevPilot-*` auth headers.
- Do not call raw OpenAI/Gemini/Claude APIs directly from external projects.

## Standard External Project Setup

Each project should expose an admin/backend settings page:

```text
/admin/integrations/devpilot
```

Minimum required settings:

```text
DEVPILOT_API_BASE_URL
DEVPILOT_SOURCE_SYSTEM
DEVPILOT_API_KEY
```

Recommended actions from that page:

- Save settings server-side.
- Test connection.
- Register project.
- Send a test event.
- Rotate key.
- Disable integration.
- Show last connection, registration, and event status.

## Security Defaults

- Store DevPilot keys server-side only.
- Never show the full key after save.
- Never log keys.
- Never expose keys to browser JavaScript.
- Use HTTPS in production.
- Use stable idempotency keys.
- Treat domain fields as review-only.
- Do not trigger deploy, DNS, SSL, Nginx, Cloudflare, redirects, provider calls, or worker execution from external projects unless a later approval-gated phase explicitly allows it.
