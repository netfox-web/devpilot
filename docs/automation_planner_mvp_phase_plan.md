# Automation Planner MVP Phase Plan

## 1. Objective

DevPilot should become the central planner for safe project automation.

The Automation Planner MVP will use external project registry data, external events, source detail, diagnostics, usage, handoffs, and admin context to generate safe automation plans for review.

The MVP is planning-only. It does not execute actions.

The purpose is to help admins answer:

- What is the current state of this external project?
- What recently changed?
- What is blocked?
- What is the safest next action?
- Which actions require approval?
- Which commands or operational steps would be suggested, as text only?

## 2. MVP Scope

The MVP may read existing DevPilot context and generate draft plans.

Allowed planning-only capabilities:

- Read External Project Registry.
- Read External Project Events.
- Read External Integration Diagnostics.
- Read External Source Detail context.
- Read External AI Usage summaries.
- Read handoff records.
- Read product/domain catalog context.
- Read manual admin notes, if provided.
- Generate recommended next actions.
- Generate risk and safety warnings.
- Generate suggested commands as display-only text.
- Require admin review before any future action.
- Store draft automation plans for review.

The MVP must remain read-only with respect to operational systems.

## 3. Non-goals

The MVP must not:

- Deploy.
- Restart.
- Rebuild.
- Run migrations.
- Change DNS.
- Change SSL.
- Change Nginx.
- Change Cloudflare.
- Change R2.
- Change infrastructure.
- Call AI providers unless a later policy-gated slice explicitly allows it.
- Run workers.
- Mutate project/task/phase records.
- Create approvals automatically.
- Execute shell commands.
- Trigger external project actions.
- Print or store secrets.
- Store raw API keys or provider keys.
- Perform automatic remediation.

Any execution bridge must be a later, separate, approval-gated phase.

## 4. Inputs

The planner may use the following read-only inputs:

### External Project Registry

Useful fields:

- `source_system`
- `external_project_id`
- `project_name`
- `status`
- `app_url`
- `primary_domain`
- `environment`
- `runtime`
- `container_name`
- `compose_project`
- `service_name`
- `host_port`
- `repo_url`
- `branch`
- `owner`
- `notes`
- `created_at`
- `updated_at`

### External Project Events

Useful fields:

- `event_type`
- `status`
- `message`
- `metadata`
- `created_at`
- `source_system`
- `external_project_id`

Example event signals:

- `healthcheck_ok`
- failed connection events
- deploy status events
- diagnostic events
- handoff-related events

### External Source Detail

Useful source-level context:

- key configured / missing
- active key count
- revoked key count
- project count
- recent events
- recent handoffs
- usage summary
- diagnostics summary
- policy/profile state

### External Integration Diagnostics

Useful diagnostic signals:

- source system missing
- source system not allowed
- active key exists / missing
- key revoked
- active key never used
- project missing
- event missing
- endpoint mismatch
- validation failures
- common error hints

### External AI Usage

Useful usage context:

- provider usage count
- recent usage
- budget warnings
- gateway enabled / disabled
- provider configured / missing
- policy/profile restrictions

### Handoff Records

Useful handoff context:

- current handoff state
- latest handoff message
- blocked status
- requested action
- source project
- target project
- handoff timestamps

### Product / Domain Catalog

Useful business context:

- known product domains
- project category
- deployment target
- public domains
- allowed operational domains

### Manual Admin Notes

Admins may provide optional planning notes such as:

- "Do not deploy this project today."
- "DNS change requires separate approval."
- "Treat this source as production-critical."
- "Only generate a diagnostic plan."

## 5. Planner Output Model

A draft automation plan should include:

```json
{
  "id": "plan_<timestamp_or_uuid>",
  "source_system": "<source_system>",
  "external_project_id": "<external_project_id>",
  "title": "<short plan title>",
  "objective": "<what this plan aims to achieve>",
  "risk_level": "low|medium|high|blocked",
  "recommended_actions": [
    {
      "label": "<action label>",
      "description": "<human-readable action>",
      "risk_level": "low|medium|high|blocked",
      "requires_approval": true,
      "approval_type": "<none|deploy|infra|dns|worker|provider|mutation>",
      "status": "suggested"
    }
  ],
  "required_approvals": [
    "deploy",
    "dns",
    "worker",
    "provider",
    "project_mutation"
  ],
  "blocked_by": [
    "<missing config or safety blocker>"
  ],
  "safety_checks": [
    {
      "name": "<check name>",
      "status": "pass|warn|fail|not_available",
      "details": "<safe details>"
    }
  ],
  "suggested_commands": [
    {
      "label": "<command purpose>",
      "command": "<display-only command text>",
      "execution_allowed": false
    }
  ],
  "affected_systems": [
    {
      "type": "external_project|devpilot|dns|infra|provider|worker",
      "name": "<system name>",
      "impact": "<read-only planning impact>"
    }
  ],
  "created_at": "<iso timestamp>",
  "status": "draft"
}
```

Allowed plan statuses:

- `draft`
- `reviewed`
- `approved`
- `rejected`
- `executed_later`

For the MVP, `approved` and `executed_later` are status labels only. No execution is performed.

## 6. Storage

Use a file-backed store first:

```text
data/automation_plans.json
```

No database migration for the MVP.

Storage requirements:

- The store must tolerate missing files.
- The store must tolerate malformed JSON by failing safely.
- The store must not contain secrets.
- The store must not contain raw API keys.
- The store must not contain provider keys.
- Suggested commands must be text only.
- Plan records must not imply execution.
- Plan writes are limited to draft plan records only.

Potential file shape:

```json
{
  "version": 1,
  "plans": []
}
```

## 7. Admin UI

Future page:

```text
GET /admin/automation-planner
```

The page should show:

- Source selector.
- Project selector.
- Recent external project signals.
- Current source/project diagnostics.
- Generated draft plan.
- Safety warnings.
- Required approvals.
- Suggested commands as display-only text.
- Plan history.
- Approve/reject buttons later, disabled in MVP.
- No execute button in MVP.

MVP UI rules:

- Admin-only.
- Read-only except draft creation.
- No secret display.
- No raw key display.
- No provider key display.
- No execution controls.
- No deploy/restart/rebuild controls.
- No DNS/SSL/Nginx/Cloudflare/R2 controls.
- No worker/task execution controls.

## 8. API

Optional admin-only routes:

```text
GET  /api/admin/automation-plans
POST /api/admin/automation-plans/draft
```

Rules:

- `GET /api/admin/automation-plans` returns draft/review metadata only.
- `POST /api/admin/automation-plans/draft` may create a draft plan record.
- `POST /draft` must not execute commands.
- `POST /draft` must not call providers.
- `POST /draft` must not run workers.
- `POST /draft` must not mutate project/task/phase.
- `POST /draft` must not create approval requests automatically.
- All outputs must be redacted and secret-free.

## 9. Safety Model

The Automation Planner MVP must fail closed.

Core rules:

- Read-only by default.
- Generated commands are display-only text.
- `execution_allowed` must be `false` for MVP suggested commands.
- No raw API keys in plans.
- No key hashes in plans if hashes are considered sensitive.
- No provider keys in plans.
- No env secret values in plans.
- No automatic execution.
- No deploy/restart/rebuild.
- No DNS/SSL/Nginx/Cloudflare/R2 changes.
- No migrations.
- No worker/task execution.
- No normal project/task/phase mutation.
- No automatic approval creation.
- All future execution must be implemented as a separate approval-gated slice.

Suggested risk levels:

- `low`: read-only diagnostic or documentation action.
- `medium`: local-only implementation or mock test suggestion.
- `high`: deploy/restart/rebuild/provider/infra/DNS/worker action that requires approval.
- `blocked`: missing key/config/path/source/project, unsafe state, or policy denial.

## 10. Rollout Slices

### Slice AP-0: Planning Doc Only

Create this phase plan.

Expected status:

```text
AUTOMATION_PLANNER_MVP_PHASE_PLAN_RECORDED
```

### Slice AP-1: File-backed Draft Plan Store

Implement:

- `data/automation_plans.json`
- safe read/write helpers
- malformed store handling
- no DB migration
- tests for draft persistence and safe failure

Expected status:

```text
AUTOMATION_PLANNER_DRAFT_STORE_LOCAL_READY_FOR_PRODUCTION_REVIEW
```

### Slice AP-2: Read-only Planner Admin Page

Implement:

```text
/admin/automation-planner
```

Features:

- show source/project selectors
- show recent external project signals
- show empty/safe draft area
- no execution controls
- admin-only

Expected status:

```text
AUTOMATION_PLANNER_ADMIN_PAGE_LOCAL_READY_FOR_PRODUCTION_REVIEW
```

### Slice AP-3: Draft Plan Generator From External Context

Implement deterministic plan generation from:

- registry
- events
- diagnostics
- source detail
- usage
- handoffs

No AI provider calls in this slice.

Expected status:

```text
AUTOMATION_PLANNER_DRAFT_GENERATOR_LOCAL_READY_FOR_PRODUCTION_REVIEW
```

### Slice AP-4: Safety Warning Evaluator

Implement:

- risk classification
- required approval detection
- blocked-by detection
- suggested command display-only validation
- no secret leakage checks

Expected status:

```text
AUTOMATION_PLANNER_SAFETY_EVALUATOR_LOCAL_READY_FOR_PRODUCTION_REVIEW
```

### Slice AP-5: Approval Request Integration, Disabled by Default

Implement approval linkage as metadata only.

Rules:

- no automatic approval creation by default
- no execution
- disabled feature flag
- admin review only

Expected status:

```text
AUTOMATION_PLANNER_APPROVAL_LINK_LOCAL_READY_FOR_PRODUCTION_REVIEW
```

### Later: Execution Bridge

A separate future phase may connect approved plans to execution.

This must be:

- approval-gated
- audited
- dry-run capable
- rollback-aware
- budget-aware
- kill-switch controlled
- policy-gated
- separately designed and approved

## 11. Tests Plan

Tests should include:

### Safety Tests

- no execution
- no provider calls
- no worker calls
- no infra writes
- no DNS/SSL/Nginx/Cloudflare/R2 changes
- no project/task/phase mutation
- no approval creation
- no secret leakage
- suggested commands are text only
- `execution_allowed` is false for MVP commands

### Store Tests

- missing plan store loads safely
- malformed plan store does not crash
- draft plan creation works
- draft plan IDs are unique
- draft plan status defaults to `draft`
- plan store does not include raw secrets
- plan store persists non-secret fields

### Context Tests

- known source/project context reads safely
- unknown source handled safely
- project with no events handled safely
- source with revoked key produces warning
- source with active key never used produces warning
- recent healthcheck event is summarized safely

### Admin/API Tests

- admin-only planner page
- unauthenticated access redirects/blocks
- draft endpoint admin-only
- draft endpoint does not execute anything
- draft endpoint rejects unsafe payloads
- draft endpoint redacts secrets from output
- generated plan contains required fields

## 12. Open Questions

- Should plans be primarily scoped per `source_system` or per `external_project_id`?
- Should a source-level plan aggregate multiple projects?
- Should the Automation Planner use AI Gateway later, or remain deterministic by default?
- If AI Gateway is used later, which policy/profile controls apply?
- What admin role is required to review or approve plans?
- Should execution ever be allowed directly from DevPilot?
- Should execution require a second human confirmation?
- How long should plans be retained?
- Should rejected plans be retained for audit?
- Should external projects be allowed to request draft plans?
- Should external projects only request diagnostics, not plans?
- Should plan generation be triggered manually or automatically after events?
- Should a healthcheck event automatically create a draft status plan?
- What is the retention policy for suggested command text?
- Should command text be normalized to avoid accidental copy/paste hazards?

## 13. Initial Recommendation

Proceed in this order:

1. AP-0: record this planning document.
2. AP-1: implement file-backed draft plan store.
3. AP-2: implement read-only admin page.
4. AP-3: implement deterministic draft generator from external context.
5. AP-4: add safety warning evaluator.
6. AP-5: add approval request linkage, disabled by default.

Do not build execution until the planning/review loop has production verification and at least one real external source, such as `gpcarai`, is generating stable project/event data.
