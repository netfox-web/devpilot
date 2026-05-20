# Approval Object Workflow Design

Date: 2026-05-18
Status: draft persistence implemented in Level 7B; approval and execution remain disabled

## Purpose

Approval Object Workflow is the future human approval layer for high-risk DevPilot actions.

It does not execute actions automatically. It provides a shared model for request intent, risk level, dry-run or diff snapshot, required approvers, status, safety checks, abort conditions, and audit trail.

Level 7 implementation status: draft-only preview UI/API is available at `/admin/approval-object-preview` and `/api/admin/approval-object-preview`. It does not save approval objects, create `approval_requests`, approve, execute, call providers, write usage logs, or write generation results.

Level 7B implementation status: persisted draft approval objects are available through `/admin/approval-objects`, `/api/admin/approval-objects`, and `/api/admin/approval-objects/draft`. Draft persistence does not approve, reject, execute, create `approval_requests`, call providers, write usage logs, or write generation results.

The goal is to make high-risk action review consistent across provider verification, domain execution, deployment, infrastructure mutation, worker execution, and project/task lifecycle changes.

## Scope

Future high-risk action types that should converge on approval objects:

- `external_ai_live_verification`
- `domain_execution`
- `dns_write`
- `cloudflare_write`
- `nginx_write`
- `ssl_change`
- `registrar_nameserver_change`
- `r2_mutation`
- `deploy`
- `worker_execution`
- `project_task_phase_mutation`
- `handoff_transition`
- `provider_budget_change`

## Current Inputs

Current surfaces that can produce approval intent in a later phase:

- External AI Live Verification Gate: `/admin/external-ai-live-verification-gate`
- Domain Execution Dry-run Center: `/admin/domain-execution-dry-run`
- Product Domain Launch Plan: `/admin/product-domain-launch-plan`
- External Project Health Planner: `/admin/automation-planner/external-project-health`
- AI Provider Readiness Dashboard: `/admin/ai-provider-readiness`
- Codex task queue: `docs/ai_coding_agent_task_queue.md`
- Task Queue Generator design: `docs/ai_coding_agent_task_queue_generator_design.md`
- Manual operator note

These inputs should remain read-only until a later implementation phase explicitly creates approval objects.

## Approval Object Shape

Draft JSON shape:

```json
{
  "id": "approval_...",
  "type": "external_ai_live_verification",
  "title": "...",
  "status": "draft|pending|approved|rejected|expired|cancelled|executed|rolled_back",
  "risk_level": "low|medium|high|critical",
  "source_surface": "/admin/external-ai-live-verification-gate",
  "requested_by": "user/system",
  "created_at": "...",
  "expires_at": "...",
  "execution_allowed": false,
  "execution_mode": "none|dry_run|manual|system_after_approval",
  "target": {
    "provider": "gemini",
    "model": "gemini-2.5-flash",
    "domain": null,
    "source_system": null
  },
  "dry_run_snapshot": {},
  "required_approvals": [
    {
      "role": "product_owner",
      "status": "missing|approved|rejected",
      "approved_by": null,
      "approved_at": null
    }
  ],
  "safety_checks": {
    "secrets_exposed": false,
    "env_change": false,
    "provider_live_call": false,
    "dns_write": false,
    "deploy": false
  },
  "abort_conditions": [],
  "audit_events": []
}
```

## Status Model

| Status | Meaning |
| --- | --- |
| `draft` | Approval intent exists but is not ready for review. |
| `pending` | Approval request is ready and waiting for required approvers. |
| `approved` | Required approvals are complete, but execution has not necessarily happened. |
| `rejected` | At least one required approver rejected the request. |
| `expired` | The request exceeded its review window. |
| `cancelled` | The requester or operator cancelled the request before execution. |
| `executed` | The approved action was executed by a later explicit execution flow. |
| `rolled_back` | The executed action was rolled back and rollback evidence was attached. |

## Execution Modes

| Mode | Meaning |
| --- | --- |
| `none` | Approval is informational or blocked from execution. |
| `dry_run` | Approval allows dry-run generation only. |
| `manual` | Approval permits a human operator to execute externally and attach evidence. |
| `system_after_approval` | Approval permits DevPilot to execute a narrowly scoped action after all gates pass. |

Default mode should be `none` unless a later phase explicitly enables another mode.

## Required Approval Roles

Recommended role set by action category:

| Action Category | Required Roles |
| --- | --- |
| External AI live verification | Product owner, engineering owner, operations owner, security reviewer |
| Domain execution | Domain owner, product owner, operations owner, DNS/Cloudflare owner, security reviewer |
| DNS / Cloudflare / Nginx / SSL / R2 | Operations owner, infrastructure owner, security reviewer, rollback owner |
| Deploy | Product owner, engineering owner, operations owner, rollback owner |
| Worker execution | Engineering owner, operations owner, safety reviewer |
| Project/task/phase/handoff mutation | Product owner, project owner, operations owner |
| Provider budget change | Product owner, finance or operations owner, security reviewer |

## Approval Intent Flow

1. A read-only surface shows risk, dry-run, checklist, and blocked execution state.
2. A later explicit action creates a draft approval object from that surface.
3. The requester reviews title, target, dry-run snapshot, safety checks, abort conditions, and required approvers.
4. The approval is submitted as `pending`.
5. Required approvers approve or reject.
6. If approved, execution remains blocked unless the object type and execution mode permit the next phase.
7. Execution, if allowed by a later phase, records audit events and evidence.
8. Rollback, if needed, records rollback events and evidence.

## Dry-run Snapshot Requirements

Every high-risk approval should attach immutable review context:

- Source surface and URL.
- Request type and target.
- Diff, plan, or dry-run preview.
- Risk score or risk level.
- Required approvals.
- Safety checks.
- Abort conditions.
- Timestamp and requester.
- Explicit list of operations that are still disabled.

Approval snapshots must not include:

- raw secrets
- auth headers
- bearer tokens
- provider key hashes
- `.env` contents
- full customer data
- full provider prompts or responses unless separately approved

## Safety Checks

Minimum safety fields:

```json
{
  "secrets_exposed": false,
  "env_change": false,
  "provider_live_call": false,
  "dns_write": false,
  "cloudflare_write": false,
  "nginx_write": false,
  "ssl_change": false,
  "registrar_nameserver_change": false,
  "r2_mutation": false,
  "deploy": false,
  "worker_execution": false,
  "project_task_phase_mutation": false,
  "handoff_transition": false
}
```

For execution-capable future phases, these fields should show the pre-approval plan, not claim execution happened before it did.

## Abort Conditions

Approval objects should carry explicit abort conditions before review. Common abort conditions:

- Any raw secret appears in the request, snapshot, logs, UI, API response, or generated artifact.
- Target domain, provider, model, project, or environment differs from the approved object.
- Required approvals are missing, expired, or rejected.
- Dry-run snapshot is stale or no longer matches current source data.
- Git worktree is dirty with unrelated runtime changes.
- Budget, token, request, or time limits are missing.
- Rollback owner or rollback notes are missing for infrastructure/deploy actions.
- Network, provider, DNS, Cloudflare, Nginx, SSL, or R2 error is ambiguous.
- Any unexpected mutation is detected.

## Audit Events

Approval object audit events should include:

- `created`
- `submitted`
- `approval_added`
- `approval_rejected`
- `safety_check_updated`
- `snapshot_refreshed`
- `cancelled`
- `expired`
- `execution_started`
- `execution_completed`
- `execution_failed`
- `rollback_started`
- `rollback_completed`

Audit events should store actor, timestamp, event type, safe summary, and evidence reference. They should not store raw secrets.

## Integration With Existing Surfaces

### External AI Live Verification Gate

The gate can create a future `external_ai_live_verification` approval object with:

- provider
- model
- fixed prompt
- one-call constraints
- provider readiness snapshot
- required approvals
- abort conditions

Until a later phase implements creation, the gate remains read-only and `live_verification_allowed=false`.

### Domain Execution Dry-run Center

The dry-run center can create future `domain_execution`, `dns_write`, `cloudflare_write`, `nginx_write`, `ssl_change`, or `registrar_nameserver_change` approval objects with:

- selected dry-run actions
- domain targets
- redirect targets
- provider choice pending state
- rollback requirements
- no-write safety snapshot

Until a later phase implements creation, the dry-run center remains read-only and `write_operations_executed=false`.

### Automation Planner External Project Health

The health planner can suggest future approval objects when recommended actions require mutation.

Until a later phase implements creation, recommended actions stay advisory and `execution_allowed=false`.

### Codex Scheduled Runner

The scheduled runner should not create approval objects in Phase 8.

Future queue-driven approval creation should require an explicit pending task and should default to draft approval objects only, not execution.

### Task Queue Generator

The Task Queue Generator can translate a future Approval Object draft into an explicit `docs/ai_coding_agent_task_queue.md` pending item.

It should not approve the object, execute the object, call Codex, commit, push, or mutate runtime data. Its output should be a reviewable queue patch with source, allowed files, forbidden files, risk level, execution mode, verification, commit/push policy, approval requirement, and safety boundaries.

## Storage and API Proposal

Future implementation options:

- Store approval objects in the existing approval request system if its schema can represent snapshots, required roles, safety checks, and audit events.
- Add a dedicated approval object table/file if the existing approval request model is too narrow.
- Provide read-only APIs first:
  - `GET /api/admin/approval-objects`
  - `GET /api/admin/approval-objects/<id>`
- Add creation only after review:
  - `POST /api/admin/approval-objects`
- Add approve/reject actions only after role and audit requirements are implemented:
  - `POST /api/admin/approval-objects/<id>/approve`
  - `POST /api/admin/approval-objects/<id>/reject`

## Test Plan

For a future implementation phase:

- Approval object creation does not execute the requested action.
- Live provider approval creation does not call Gemini or Claude.
- Domain approval creation does not call Cloudflare or write DNS/Nginx/SSL/R2.
- Approval objects do not contain raw secrets, auth headers, bearer tokens, key hashes, or `.env` contents.
- Required approvals are enforced before any execution-capable state.
- Rejected, expired, or cancelled approvals cannot execute.
- Dry-run snapshots are immutable or versioned.
- Audit events are appended safely and cannot overwrite history.
- Anonymous users cannot view or mutate approvals.
- Owner/admin role checks match current admin security boundaries.

## Acceptance Criteria

This design is ready for implementation planning when:

- Product, engineering, operations, and security owners agree on approval roles.
- The canonical approval object shape is accepted.
- Existing `approval_requests` fit is reviewed.
- Read-only approval object list/detail routes are planned before mutation routes.
- Execution remains disabled until a later explicit phase.

## Non-Goals

This Phase 8 design does not:

- create approval objects
- execute provider calls
- execute DNS, Cloudflare, Nginx, SSL, registrar, R2, deploy, or worker actions
- mutate project, task, phase, approval, or handoff records
- change `.env`
- touch secrets
- modify runtime code
- deploy
