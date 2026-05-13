# DevPilot Integration Toolbox

This toolbox is the standard package for every external project that needs to connect back to DevPilot.

DevPilot should be the shared registry, event hub, handoff center, and future AI Gateway policy point. External projects receive DevPilot-issued external API keys only. They must not receive raw OpenAI, Gemini, Claude, Replicate, or fal provider keys.

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

5. External AI Gateway Plan / Future API Guide
   - File: `external_ai_gateway_future_api_guide.md`
   - Purpose: explain future AI generate/chat integration through DevPilot policy.

6. JavaScript Client Example
   - File: `devpilot_external_client.js`
   - Purpose: server-side Node.js helper for test/register/event/handoff calls.

7. Python Client Example
   - File: `devpilot_external_client.py`
   - Purpose: server-side Python helper for test/register/event/handoff calls.

8. Environment Template
   - File: `devpilot.env.example`
   - Purpose: standard environment names for external project integration.

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
