# Automation Planner External Project Health MVP

Date: 2026-05-18
Audience: product planning, engineering planning, operations planning
Status: implemented as read-only UI/API in Phase 4; execution remains disabled

## Purpose

Define a first Automation Planner MVP focused on external project health.

The MVP should help operators inspect external project registry records, events, diagnostics, handoffs, and AI usage signals, then produce a read-only health plan with risk level, blockers, recommended checks, and suggested next actions.

Implementation status: implemented as read-only UI/API in Phase 4 (`a9d3e17`). It does not deploy, restart services, call AI providers, create DNS records, change Cloudflare, change SSL, change Nginx, mutate R2, change `.env`, or touch secrets.

Approval workflow boundary: Phase 8 defines future approval objects for planner recommendations that require mutation in `docs/approval_object_workflow_design.md`. This health planner remains read-only and does not create approval objects or execute recommended actions.

## Inputs

Primary inputs:

- External Project Registry records.
- External Project Events.
- External Integration Diagnostics.
- External Source Detail.
- External AI Usage records.
- AI handoff records.
- External API key status metadata.
- Product Domain catalog lookup results when an external project declares domains.
- Manual operator notes, when added by an authenticated owner/admin.

Existing surfaces that can provide context:

- `/admin/automation-planner/external-project-health`
- `/api/admin/automation-planner/external-project-health`
- `/admin/external-projects`
- `/admin/external-projects/<source_system>/<external_project_id>`
- `/admin/external-integration-diagnostics`
- `/admin/external-sources`
- `/admin/external-ai-usage`
- `/ai-handoffs`
- `/api/external/projects`
- `/api/external/projects/<external_project_id>/events`
- `/api/ai-handoffs`
- `/api/product-domains/lookup?domain=...`

Input fields to normalize:

- `source_system`
- `external_project_id`
- project name / label
- repo URL metadata
- runtime URL metadata
- container/service metadata
- declared domains
- last event timestamp
- recent event types
- recent handoff count
- open/pending handoff count
- recent AI usage count
- AI usage failure count
- external API key active/revoked state
- diagnostic warnings
- missing integration fields

## Output Shape

The MVP output should be a read-only JSON-like health plan.

Draft shape:

```json
{
  "ok": true,
  "read_only": true,
  "execution_allowed": false,
  "source_system": "example-source",
  "external_project_id": "example-project",
  "health_status": "attention_needed",
  "risk_level": "medium",
  "risk_score": 45,
  "summary": "Recent events exist, but diagnostics show missing runtime metadata.",
  "signals": [
    {
      "id": "recent_events",
      "status": "pass",
      "severity": "info",
      "message": "Recent project events were received."
    }
  ],
  "blockers": [],
  "warnings": [],
  "recommended_actions": [
    {
      "type": "manual_check",
      "title": "Confirm runtime URL",
      "description": "Ask the external project owner to register the current runtime URL.",
      "requires_approval": false
    }
  ],
  "safety_checks": {
    "provider_calls_executed": false,
    "deployment_executed": false,
    "dns_changes_executed": false,
    "cloudflare_changes_executed": false,
    "ssl_changes_executed": false,
    "nginx_changes_executed": false,
    "r2_changes_executed": false,
    "secrets_accessed": false,
    "env_changed": false,
    "project_mutation_executed": false,
    "task_mutation_executed": false,
    "approval_created": false,
    "handoff_mutation_executed": false
  },
  "generated_at": "2026-05-18T00:00:00"
}
```

## Risk Scoring

Risk scoring should be deterministic and explainable. It should not use live AI provider calls in the MVP.

Draft score bands:

| Risk level | Score range | Meaning |
| --- | ---: | --- |
| `low` | 0-24 | Healthy or mostly complete metadata, no immediate blockers. |
| `medium` | 25-59 | Missing metadata, stale events, or non-critical warnings. |
| `high` | 60-84 | Multiple warning signals, failed integration checks, or pending handoff risk. |
| `blocked` | 85-100 | Critical missing identity, revoked key, repeated failures, or unsafe requested action. |

Draft scoring signals:

| Signal | Score impact |
| --- | ---: |
| Missing `source_system` or project identity | +85 |
| External API key revoked or unavailable for managed source | +50 |
| No recent project event | +25 |
| Missing runtime URL or health URL metadata | +20 |
| Missing repo URL metadata | +10 |
| Pending high-risk handoff | +30 |
| Any pending handoff | +15 |
| Recent external AI usage failures | +20 |
| Declared domain not found in Product Domain catalog | +15 |
| Diagnostics warnings present | +10 each, capped at +30 |
| Recent successful healthcheck/deploy event metadata | -10 |
| Complete registry metadata | -10 |

The score should be clamped to `0-100`.

## Safety Checks

The MVP must report explicit safety flags:

- `read_only: true`
- `execution_allowed: false`
- `provider_calls_executed: false`
- `deployment_executed: false`
- `dns_changes_executed: false`
- `cloudflare_changes_executed: false`
- `ssl_changes_executed: false`
- `nginx_changes_executed: false`
- `r2_changes_executed: false`
- `secrets_accessed: false`
- `.env_changed: false`

Planner recommendations must stay advisory. They may suggest manual checks or future approval-gated actions, but must not execute them.

## Non-Goals

This MVP does not:

- call OpenAI, Gemini, Claude, or any other provider
- deploy or restart services
- mutate projects, tasks, phases, approvals, or handoffs
- create DNS records
- change Cloudflare settings
- change SSL settings
- write Nginx config
- modify R2 buckets or objects
- read, print, hash, copy, or change secrets
- modify `.env`
- create GitHub issues or pull requests
- auto-remediate external project failures
- decide product launch priority

## API/UI Proposal

### UI

Owner/admin page:

```text
/admin/automation-planner/external-project-health
```

Suggested UI sections:

- Source/project selector.
- Health status summary.
- Risk score with contributing signals.
- Blockers.
- Warnings.
- Recommended manual actions.
- Recent events.
- Related handoffs.
- Related AI usage summary.
- Safety confirmation panel.

### API

Owner/admin API:

```text
GET /api/admin/automation-planner/external-project-health
```

Query parameters:

- `source_system`
- `external_project_id`
- `include_events=true|false`
- `include_handoffs=true|false`
- `include_usage=true|false`

Expected API properties:

- authenticated owner/admin only
- read-only
- no provider calls
- no deployment calls
- no infrastructure mutation
- deterministic score from local records

Implementation notes:

- If `source_system` is omitted, return an empty selected state with source options and `health_status: not_available`.
- If selected source/project data is missing, return a safe blocked or attention-needed payload instead of HTTP 500.
- The health endpoint must not create draft automation plans. Draft plan creation remains a separate later phase.
- The endpoint may reuse existing read helpers such as registry, events, diagnostics, handoff rows, and usage summaries.

## Test Plan

Unit/API tests should cover:

- Anonymous UI access redirects to login.
- Anonymous API access returns permission denied.
- Owner/admin can load the UI.
- Owner/admin can call the API.
- Missing project returns a safe not-found or empty-state payload.
- Complete project metadata returns low risk.
- Missing runtime metadata increases risk.
- Revoked or missing external API key status increases risk.
- Pending high-risk handoff increases risk.
- Recent failed AI usage increases risk.
- Declared unknown domain creates a warning, not a DNS action.
- Output includes safety flags.
- Output does not contain raw API keys, provider keys, `Authorization`, `Bearer`, or `key_hash`.
- Provider call helpers are not called.
- Cloudflare/DNS/deploy helpers are not called.

Suggested verification commands once implemented:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_automation_plans.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_ai_manual_handoff.py
git diff --check
```

## Acceptance Criteria

- A read-only external project health plan can be generated for a selected `source_system` and optional `external_project_id`.
- The response includes `health_status`, `risk_level`, `risk_score`, `signals`, `blockers`, `warnings`, `recommended_actions`, and `safety_checks`.
- Risk scoring is deterministic and explained by returned signals.
- No live AI provider calls occur.
- No deploy, DNS, Cloudflare, SSL, Nginx, R2, `.env`, or secret mutation occurs.
- The UI and API are owner/admin gated.
- Outputs do not expose raw secrets, `Authorization`, `Bearer`, or `key_hash`.
- Tests confirm read-only behavior and no external side effects.
