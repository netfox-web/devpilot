# AI-to-AI Manual Handoff Phase 2 Plan

Date: 2026-05-12
Status: design only, no implementation in this phase

## Scope

Phase 2 adds manual AI-to-AI handoff as a controlled workflow on top of the Phase 1 read-only thread board.

The goal is to let one AI or agent record that a task should be handed to another AI or agent, while keeping execution separated from coordination. A handoff is a coordination record, not permission to run a provider, worker, repo write, deploy, or infrastructure write.

Phase 2 must remain safe by default:

- No automatic provider call.
- No automatic worker execution.
- No automatic repo write.
- No automatic deploy.
- No automatic git push.
- No automatic Cloudflare, DNS, SSL, redirect, Nginx, or registrar write.
- No `cf_batch.py` execution.
- No `cf_batch_devpilot_bridge.py` execution.
- No `--apply` or `--confirm-real-write`.
- High-risk handoffs must stay pending approval or be linked to Approval Center before any later action.

## Current State

Phase 1 already provides a read-only AI task timeline:

- `/ai-messages`
- `/tasks/<task_id>/thread`
- `GET /api/ai-messages`
- `GET /api/tasks/<task_id>/timeline`

The timeline aggregates:

- `tasks`
- `ai_messages`
- `dispatch_jobs`
- `agent_runs`
- `handoff_logs`
- `ai_heartbeats`
- `approval_requests`

Existing handoff functionality is project-centered:

- `handoff_logs` stores project handoff records.
- `save_handoff(project_id, payload)` inserts into `handoff_logs`.
- `POST /projects/<project_id>/handoff` creates a handoff from the project UI.
- `POST /api/projects/<project_id>/handoff` creates a handoff by API token.
- `POST /api/projects/<project_id>/handoff/parse` parses free text and creates a handoff.
- `PATCH /api/handoffs/<handoff_id>/hide` and `/restore` soft-hide and restore handoff records.
- Project detail already renders AI handoff records and a manual project handoff form.

Existing `handoff_logs` columns:

```text
id
project_id
source
agent_name
work_mode
conversation_ref
repo_branch
commit_sha
risk_level
summary
raw_text
completed_phases
changed_files
test_result
git_status
db_backups
next_steps
warnings
api_payload
is_hidden
hidden_at
hidden_reason
created_at
```

Important implementation note:

`save_handoff()` is not a pure handoff insert. It can update project phases from `completed_phases`, update `projects.next_steps`, and recalculate project progress. For Phase 2, the implementation should reuse the `handoff_logs` table, but should not blindly use `save_handoff()` for task handoffs unless those side effects are disabled or avoided.

## Can `handoff_logs` Be Reused?

Yes, `handoff_logs` is sufficient for the Phase 2 MVP if the task-handoff fields are stored in existing columns plus structured `api_payload`.

Recommended no-migration mapping:

| Phase 2 field | Existing storage |
| --- | --- |
| `task_id` | `conversation_ref = ai-task:<task_id>` and `api_payload.task_id` |
| `from_agent` | `source`, `agent_name`, and `api_payload.from_agent` |
| `to_agent` | `api_payload.to_agent` |
| `reason` | `summary` and `api_payload.reason` |
| `next_step` | `api_payload.next_step` |
| `risk_level` | `risk_level` |
| `status` | `api_payload.handoff_status` |
| `created_at` | `created_at` |
| `accepted_at` | `api_payload.accepted_at` |
| `completed_at` | `api_payload.completed_at` |
| `rejected_at` | `api_payload.rejected_at` |

This is enough for a low-volume MVP and keeps Phase 2 free of DB migrations.

Limitations of no-migration reuse:

- `status`, `to_agent`, and timestamps inside `api_payload` are not first-class indexed columns.
- Querying by recipient or status requires JSON parsing or text filtering.
- Accept, complete, and reject actions must update `api_payload` carefully.
- A dedicated helper is needed to avoid project progress side effects from the current project handoff helper.

Recommended Phase 2.1 migration only if this workflow becomes active and high-volume:

- Add `task_id` to `handoff_logs`.
- Add `from_agent`.
- Add `to_agent`.
- Add `handoff_status`.
- Add `accepted_at`.
- Add `completed_at`.
- Add `rejected_at`.
- Add optional `approval_request_id`.
- Add indexes on `(task_id, handoff_status)`, `(to_agent, handoff_status)`, and `(project_id, created_at)`.

Do not run this migration during Phase 2 planning.

## MVP Definition

AI-to-AI Manual Handoff Phase 2 is complete when:

- A user or authenticated AI client can create a manual handoff record for an existing AI task.
- The handoff identifies source agent, target agent, reason, next step, risk level, and status.
- The handoff appears in the task thread timeline.
- The handoff list can be viewed from a dedicated handoff board.
- Handoff status can move through `pending`, `accepted`, `completed`, or `rejected`.
- High-risk handoffs cannot trigger execution and remain visibly approval-gated.
- No provider, worker, sandbox apply, repo write, deploy, or infrastructure write is triggered by any handoff endpoint.

Not included in Phase 2:

- Automatic AI execution after handoff.
- Automatic reviewer execution.
- Automatic task status mutation.
- Automatic approval creation unless explicitly approved as a later implementation choice.
- DB schema migration.
- Provider-specific routing or model selection.
- Cloudflare, DNS, SSL, redirect, Nginx, registrar, or deploy automation.

## Proposed Data Flow

1. Planner AI or human creates a task.
2. The task appears in `/tasks/<task_id>/thread`.
3. Planner AI or human opens `/tasks/<task_id>/handoff`.
4. The user creates a manual handoff:
   - `from_agent`
   - `to_agent`
   - `reason`
   - `next_step`
   - `risk_level`
5. DevPilot stores a `handoff_logs` row:
   - `conversation_ref = ai-task:<task_id>`
   - `risk_level` copied to the first-class column.
   - structured handoff metadata written to `api_payload`.
   - `handoff_status = pending`.
6. `/tasks/<task_id>/thread` shows the handoff as a timeline event.
7. The target agent or human accepts, completes, or rejects the handoff manually.
8. Each status update only updates handoff metadata and timestamps.
9. If risk is high, the UI shows `pending approval` and the API refuses to transition it into any execution-like state without a separate Approval Center phase.

## Proposed Handoff Payload

Canonical payload stored under `handoff_logs.api_payload`:

```json
{
  "record_type": "ai_task_handoff",
  "task_id": 123,
  "from_agent": "planner",
  "to_agent": "executor",
  "reason": "Implementation plan is ready for manual execution review.",
  "next_step": "Review the plan and prepare a dry-run patch proposal.",
  "risk_level": "low",
  "handoff_status": "pending",
  "approval_required": false,
  "created_at": "2026-05-12T00:00:00+08:00",
  "accepted_at": null,
  "completed_at": null,
  "rejected_at": null,
  "safety": {
    "provider_call_executed": false,
    "worker_executed": false,
    "repo_write_executed": false,
    "deploy_executed": false,
    "external_write_executed": false
  }
}
```

Allowed statuses:

- `pending`
- `accepted`
- `completed`
- `rejected`

Recommended high-risk behavior:

- `risk_level` values such as `high`, `critical`, `deploy`, `dns`, `cloudflare`, `ssl`, `redirect`, `nginx`, `registrar`, or `production` set `approval_required = true`.
- High-risk handoffs remain coordination records only.
- If no Approval Center integration is implemented yet, the status can remain `pending` with `pending_approval = true` in `api_payload`.

## Proposed UI

### `/ai-handoffs`

Read-only first, with optional manual status actions.

Recommended columns:

- Handoff id.
- Task id and task title.
- Project.
- From agent.
- To agent.
- Risk level.
- Status.
- Created time.
- Accepted/completed/rejected time.
- Latest next step.
- Link to `/tasks/<task_id>/thread`.

Filters:

- status
- risk level
- from agent
- to agent
- project
- task id

Safety display:

- Show a clear `read-only coordination` badge.
- Show `approval required` for high-risk handoffs.
- Do not show buttons that imply provider execution, deploy, DNS, Cloudflare, SSL, redirect, or Nginx write.

### `/tasks/<task_id>/handoff`

Manual handoff form for a single AI task.

Fields:

- from agent
- to agent
- reason
- next step
- risk level

Submit behavior:

- Create a handoff record only.
- Do not update task status.
- Do not call provider.
- Do not run worker.
- Do not write repo.
- Do not deploy.
- Do not perform infrastructure writes.

For high-risk values:

- Show `approval required`.
- Store as pending approval.
- Do not allow accept/complete to imply execution.

### `/tasks/<task_id>/thread`

Extend the existing Phase 1 thread page:

- Show handoff status badge.
- Show from/to agent.
- Show reason and next step.
- Show accepted/completed/rejected timestamps when present.
- Show approval-required state for high-risk handoffs.
- Keep the timeline explicitly read-only.

## Proposed API

### `GET /api/ai-handoffs`

Returns normalized handoff rows derived from `handoff_logs`.

Query parameters:

- `task_id`
- `project_id`
- `status`
- `risk_level`
- `from_agent`
- `to_agent`
- `limit`

Response should include:

- `ok`
- `items`
- `count`
- `read_only`
- `execution_allowed: false`

### `POST /api/tasks/<task_id>/handoff`

Creates a manual handoff record for a task.

Required body:

```json
{
  "from_agent": "planner",
  "to_agent": "executor",
  "reason": "Why this handoff is needed.",
  "next_step": "What the receiving agent should do next.",
  "risk_level": "low"
}
```

Implementation requirements:

- Validate task exists.
- Resolve `project_id` from task.
- Validate required fields.
- Normalize `risk_level`.
- Insert into `handoff_logs`.
- Use `conversation_ref = ai-task:<task_id>`.
- Store status/timestamps in `api_payload`.
- Do not use project progress update paths.
- Return the created normalized handoff.

### `POST /api/handoffs/<handoff_id>/accept`

Updates only the handoff record:

- `handoff_status = accepted`
- `accepted_at = now`

Must not:

- update task status
- dispatch an AI task
- call any provider
- run worker
- create repo write
- deploy
- create external infrastructure writes

### `POST /api/handoffs/<handoff_id>/complete`

Updates only the handoff record:

- `handoff_status = completed`
- `completed_at = now`

Completion means the receiving agent or human has recorded completion. It does not imply any action was executed by DevPilot.

### `POST /api/handoffs/<handoff_id>/reject`

Updates only the handoff record:

- `handoff_status = rejected`
- `rejected_at = now`
- optional rejection reason in `api_payload.rejection_reason`

### `GET /api/tasks/<task_id>/timeline`

Already exists from Phase 1. Phase 2 should extend the normalized handoff objects returned inside the existing timeline payload to include:

- `task_id`
- `from_agent`
- `to_agent`
- `reason`
- `next_step`
- `handoff_status`
- `approval_required`
- `accepted_at`
- `completed_at`
- `rejected_at`

## Safety Rules

Phase 2 endpoint handlers must be coordination-only:

- Read task and project records.
- Insert or update only `handoff_logs`.
- Do not create `dispatch_jobs`.
- Do not create `agent_runs`.
- Do not create `ai_messages` automatically.
- Do not call OpenAI, Gemini, Claude, or other providers.
- Do not call AI Console dispatch.
- Do not call worker execution helpers.
- Do not apply sandbox artifacts.
- Do not update repository files.
- Do not run git push.
- Do not deploy.
- Do not restart backend.
- Do not run Cloudflare/DNS/SSL/redirect/Nginx/registrar code.
- Do not call `cf_batch.py`.
- Do not call `cf_batch_devpilot_bridge.py`.
- Do not accept `--apply` or `--confirm-real-write` as part of any handoff flow.

High-risk handoff safety:

- Normalize risk level before storage.
- Compute `approval_required`.
- Mark high-risk items as `pending approval`.
- Do not create or execute an Approval Center action unless a later phase explicitly approves that feature.
- UI should make it clear that the next step is manual review, not execution.

## Implementation Plan

Recommended safe rollout order:

1. Add handoff normalization helpers.
   - Parse `handoff_logs.api_payload`.
   - Normalize `from_agent`, `to_agent`, `reason`, `next_step`, `handoff_status`, and timestamps.
   - Keep backward compatibility with existing project handoff records.

2. Add a side-effect-free insert helper.
   - Suggested name: `create_ai_task_handoff(task_id, payload)`.
   - Insert into `handoff_logs`.
   - Do not call `update_phase_status()`.
   - Do not update `projects.next_steps`.
   - Do not call `recalc_project()` unless explicitly required for display consistency.

3. Add a side-effect-free status update helper.
   - Suggested name: `update_ai_handoff_status(handoff_id, status, payload=None)`.
   - Update `api_payload` and optional display fields only.
   - Do not mutate tasks, dispatch jobs, approvals, or providers.

4. Add list query helper.
   - Suggested name: `ai_handoff_rows(...)`.
   - Read from `handoff_logs`.
   - Filter by project, task id, status, risk, from/to agent.
   - Keep filtering conservative if using `api_payload` text search before a migration exists.

5. Add API routes.
   - `GET /api/ai-handoffs`
   - `POST /api/tasks/<task_id>/handoff`
   - `POST /api/handoffs/<handoff_id>/accept`
   - `POST /api/handoffs/<handoff_id>/complete`
   - `POST /api/handoffs/<handoff_id>/reject`

6. Add UI routes.
   - `/ai-handoffs`
   - `/tasks/<task_id>/handoff`
   - Extend `/tasks/<task_id>/thread`.

7. Add templates.
   - `templates/ai_handoffs.html`
   - `templates/ai_task_handoff.html`
   - Update `templates/ai_task_thread.html` only for display.
   - Update `templates/base.html` navigation if appropriate.

8. Add tests.
   - Add a focused test file such as `tests/test_ai_manual_handoff_phase2.py`.
   - Keep tests fully local and side-effect free.

9. Run verification.
   - `python -m py_compile app.py`
   - `python -m unittest discover -s tests`
   - `git diff --check`

## Tests Design

Minimum test cases:

1. `GET /ai-handoffs` returns 200.
2. `GET /api/ai-handoffs` returns a list payload with `read_only` or `execution_allowed=false`.
3. `GET /tasks/<task_id>/handoff` returns 200 for an existing task.
4. `POST /api/tasks/<task_id>/handoff` creates a handoff row.
5. Created handoff contains:
   - `task_id`
   - `from_agent`
   - `to_agent`
   - `reason`
   - `next_step`
   - `risk_level`
   - `handoff_status = pending`
6. `GET /api/tasks/<task_id>/timeline` includes the new handoff in `handoffs` and `timeline`.
7. `POST /api/handoffs/<handoff_id>/accept` sets status to `accepted` and records `accepted_at`.
8. `POST /api/handoffs/<handoff_id>/complete` sets status to `completed` and records `completed_at`.
9. `POST /api/handoffs/<handoff_id>/reject` sets status to `rejected` and records `rejected_at`.
10. High-risk handoff returns `approval_required=true` and does not execute anything.
11. Provider call helpers are not called.
12. Worker execution helpers are not called.
13. Sandbox apply helpers are not called.
14. No task status is modified.
15. No approval request is automatically created unless the implementation explicitly chooses a pending Approval Center integration in a later approved phase.

Suggested monkeypatch targets for no-side-effect tests:

- `run_ai_task`
- `run_ai_task_flow`
- `dispatch_ai_console_task`
- `run_project_ai_flow`
- dispatch job creation helpers
- provider client call helpers
- Cloudflare request helpers
- sandbox apply helpers

## Phase 2.1 Migration Plan

Only consider this after Phase 2 MVP proves the workflow needs stronger querying or audit guarantees.

Potential migration:

```text
ALTER TABLE handoff_logs ADD COLUMN task_id INTEGER;
ALTER TABLE handoff_logs ADD COLUMN from_agent TEXT;
ALTER TABLE handoff_logs ADD COLUMN to_agent TEXT;
ALTER TABLE handoff_logs ADD COLUMN handoff_status TEXT DEFAULT 'pending';
ALTER TABLE handoff_logs ADD COLUMN accepted_at TEXT;
ALTER TABLE handoff_logs ADD COLUMN completed_at TEXT;
ALTER TABLE handoff_logs ADD COLUMN rejected_at TEXT;
ALTER TABLE handoff_logs ADD COLUMN approval_request_id INTEGER;
```

Potential indexes:

```text
CREATE INDEX IF NOT EXISTS idx_handoff_logs_task_status ON handoff_logs(task_id, handoff_status);
CREATE INDEX IF NOT EXISTS idx_handoff_logs_to_status ON handoff_logs(to_agent, handoff_status);
CREATE INDEX IF NOT EXISTS idx_handoff_logs_project_created ON handoff_logs(project_id, created_at);
```

Migration is not required for Phase 2 MVP.

## Acceptance Criteria

Phase 2 is acceptable when:

- Manual handoff can be created for an existing AI task.
- Handoff is visible in `/ai-handoffs`.
- Handoff is visible in `/tasks/<task_id>/thread`.
- Handoff can be accepted, completed, or rejected.
- High-risk handoffs are visibly approval-gated.
- Timeline shows handoff status and next step.
- No provider call is executed.
- No worker is executed.
- No sandbox apply is executed.
- No repo write is executed.
- No deploy is executed.
- No Cloudflare, DNS, SSL, redirect, Nginx, or registrar write is executed.
- Existing Phase 1 tests still pass.

## Explicit Non-Actions

This plan does not:

- Modify `app.py` behavior.
- Add a DB migration.
- Deploy code.
- Restart backend.
- Push git commits.
- Write Cloudflare DNS.
- Change SSL.
- Create redirect rules.
- Change Nginx.
- Run `cf_batch.py`.
- Run `cf_batch_devpilot_bridge.py`.
- Use `--apply`.
- Use `--confirm-real-write`.
