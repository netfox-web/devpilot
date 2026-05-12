# AI-to-AI Communication MVP Plan

Generated: 2026-05-12

This document defines a safe MVP path for DevPilot AI-to-AI communication. It is a design and discovery document only. It does not implement features, add migrations, deploy code, restart services, or execute Cloudflare/DNS/Nginx tooling.

## 1. Current State

DevPilot already has a strong AI collaboration foundation:

- AI Console at `/ai-console` for provider health, AI task dispatch, task execution, flow runs, and recent `ai_messages`.
- AI task detail page at `/ai-tasks/<task_id>` with task metadata, prompt/result, parent/child task relationships, related flow runs, and task-linked AI messages.
- Flow run detail page at `/flow-runs/<flow_run_id>` with related tasks, system flow messages, and AI messages.
- AI Heartbeats page at `/ai-heartbeats` and API at `/api/ai-heartbeats` for Codex, Claude, Cursor, Antigravity, Fleet, and other agents.
- Handoff API at `/api/projects/<project_id>/handoff` and `/api/projects/<project_id>/handoff/parse` for agent completion reports.
- Dispatch job APIs at `/api/dispatch`, `/api/dispatch-jobs`, `/api/dispatch-jobs/<job_id>/status`, and `/api/dispatch-jobs/<job_id>/agent-runs`.
- AI task APIs at `/api/tasks`, `/api/ai-tasks/<task_id>`, `/api/tasks/<task_id>/run`, `/api/tasks/<task_id>/run-flow`, `/api/tasks/<task_id>/approve`, `/api/tasks/<task_id>/reject`, `/api/tasks/<task_id>/retry`, `/api/tasks/<task_id>/block`, `/api/tasks/<task_id>/unblock`, and `/api/tasks/<task_id>/cancel`.
- AI message API at `/api/ai/messages`.
- Claude executor preview with optional Gemini reviewer in the AI Console.
- Sandbox artifact gallery at `/ai-console/sandbox`, `/ai-console/sandbox/<artifact_id>`, `/api/ai-console/sandbox`, `/api/ai-console/sandbox/<artifact_id>/download`, and `/api/ai-console/sandbox/cleanup-plan`.
- Approval Requests at `/approval-requests` for high-risk action review.
- AI Center Fleet read-only integration at `/ai-center/fleet`.

Existing data tables that can be reused:

- `tasks`: AI task records with status, provider, prompt, parent task, approval flags, retry state, and result.
- `ai_messages`: provider/model/task_role messages with status, response text, error text, and `raw_response`.
- `dispatch_jobs`: queued work for external/runner agents, including risk level, approval requirement, result, changed files, and diff stat.
- `agent_runs`: command/output records associated with `dispatch_jobs`.
- `handoff_logs`: project handoff records with source agent, risk, summary, changed files, tests, warnings, and next steps.
- `ai_heartbeats`: agent presence and current-task state.
- `approval_requests`: high-risk action approval queue.
- `ai_usage_logs`: provider/model/task-role cost and execution tracking.
- `flow_runs`: project AI flow execution summaries and related message windows.

Reusable implementation details:

- `create_ai_task()` already creates structured AI tasks.
- `run_ai_task()` already calls a provider and writes an `ai_messages` row with `raw_response.task_id`.
- `run_ai_task_flow()` and `run_project_ai_flow()` already support chained execution and approval stops.
- `approve_ai_task()` and `reject_ai_task()` already write approval system messages.
- `task_ai_message_rows()` already maps `ai_messages` back to a task through `raw_response.task_id`.
- `save_handoff()` already records agent handoff payloads and updates project next steps.
- `save_ai_heartbeat()` already upserts agent status by source, agent name, machine, project, and session.

## 2. MVP Definition

AI-to-AI Communication MVP is complete when DevPilot can show and preserve a complete, reviewable AI collaboration thread for a task.

The MVP completion standard:

- Planner AI can create or propose a task.
- Executor AI can respond to the task.
- Reviewer AI can review the executor output.
- Ops AI or system verification can record a verification note.
- DevPilot can create or attach a handoff record for the task/project.
- UI can display a single thread/timeline containing task, messages, reviews, verification, heartbeats, approvals, dispatch jobs, and handoff records.
- Any high-risk follow-up remains blocked behind explicit human approval.

The MVP does not include:

- Automatic repository writes.
- Automatic production deploy.
- Automatic `git push`.
- Automatic Cloudflare/DNS/SSL/redirect/Nginx writes.
- Automatic execution of `cf_batch.py` or `cf_batch_devpilot_bridge.py`.
- Automatic use of `--apply` or `--confirm-real-write`.
- DB schema changes in the discovery phase.
- Fully autonomous worker loops without human-visible queue and approval controls.

## 3. Proposed Flow

1. Planner AI creates task
   - Planner uses `POST /api/tasks` or a future UI action to create a `tasks` row.
   - Suggested `task_type`: `requirement_analysis`, `development_plan`, `test_checklist`, `deploy_check`, or `handoff_report`.
   - For risky work, `requires_approval=1` is set from the start.

2. Executor AI replies
   - Executor runs through existing `run_ai_task()` or a future message-only endpoint.
   - Output is written to `ai_messages` with `task_role=executor`.
   - `raw_response.task_id` links the message back to the task.

3. Reviewer AI reviews
   - Reviewer creates a message with `task_role=reviewer`.
   - Review includes pass/warn/fail status, risks, missing tests, and suggested next step.
   - Reviewer output is visible in the same task thread.

4. Ops AI records verification
   - Ops AI records read-only validation output as `task_role=tester` or `task_role=ops`.
   - Verification may reference local tests, HTTP checks, dry-run results, or post-deploy checks.

5. System creates handoff
   - When the task reaches a human-approved completion point, DevPilot creates or attaches a `handoff_logs` row.
   - Handoff references the task/thread through `conversation_ref` until a dedicated thread id exists.

6. UI displays full thread
   - A thread page groups task metadata, all related `ai_messages`, related `dispatch_jobs`, `agent_runs`, `handoff_logs`, approval events, and heartbeats.
   - Timeline is ordered by created/updated time and shows source, role, status, and safety flags.

7. Human approval gates high-risk next step
   - High-risk actions create an `approval_requests` item or require `tasks.requires_approval=1`.
   - No action executes automatically just because an AI message says it should.

## 4. Data Model Mapping

`tasks`

- Canonical work item for the MVP.
- Existing fields cover title, task type, priority, provider, prompt, status, result, error, retry, parent/child relation, and approval state.
- Use `parent_task_id` for planner -> executor -> reviewer chains until a dedicated thread table is approved.

`ai_messages`

- Canonical message/event payload table.
- Existing fields cover project, provider, model, task role, status, response text, errors, and raw JSON.
- Today task linking is indirect through `raw_response.task_id`.
- MVP can continue using this link for Phase 1 and Phase 2.
- Future phase may add explicit `task_id`, `thread_id`, `parent_message_id`, and `message_type`, but this discovery phase does not add migrations.

`dispatch_jobs`

- Queue for external runner or worker agents.
- Useful for worker dry-runs, Codex runner tasks, and future AI-to-AI execution delegation.
- Existing `risk_level` and `approval_required` map directly to safety rules.

`agent_runs`

- Execution trace for runner jobs.
- Should appear in timelines as read-only run evidence.

`handoff_logs`

- Project-level completion and transfer record.
- Can use `conversation_ref` to store a task/thread reference such as `ai-task:<id>` in the MVP.
- Should not contain token values or secret material.

`ai_heartbeats`

- Agent presence and current-task indicator.
- Timeline can show latest heartbeat for each agent participating in a task or project.
- `active_dispatch` can connect an agent to a current dispatch job.

`approval_requests`

- Separate safety center for high-risk actions.
- MVP should show related approvals in a task timeline when the payload references a project/task/thread.
- High-risk work must stop here until a human approves.

`flow_runs`

- Existing project-level AI flow execution record.
- Useful for grouping related task and message events by time window.

## 5. Proposed UI

`/ai-messages`

- Read-only global message board.
- Filters: project, task role, provider, status, date range, task id, thread id when available.
- Shows message source, status, prompt summary, response summary, and linked task/project.

`/ai-messages/<thread_id>`

- Read-only full thread view once a stable thread id exists.
- Until then, thread id can be a virtual id such as `task-<task_id>` or `flow-<flow_run_id>`.

`/tasks/<task_id>/thread`

- Task-centered timeline.
- Shows task metadata, planner prompt, executor responses, reviewer output, ops verification, approval events, related handoff, related dispatch jobs, and agent heartbeats.
- Can initially redirect or alias to `/ai-tasks/<task_id>` if the existing page is extended.

`AI Console thread panel`

- Add a compact panel to `/ai-console`.
- Show latest active AI-to-AI threads, pending reviews, pending approvals, and blocked tasks.

`Handoff timeline`

- In project detail and task thread, show `handoff_logs` related by project and `conversation_ref`.
- Highlight source agent, work mode, risk level, tests, warnings, and next steps.

`Review timeline`

- Show reviewer messages separately from executor messages.
- Reviewer status should be visually distinct: pass, warn, fail, needs-human-review.

## 6. Proposed API

`GET /api/ai-messages`

- Read-only list of messages.
- Query parameters: `project_id`, `task_id`, `thread_id`, `provider`, `task_role`, `status`, `limit`.
- Can wrap existing `/api/ai/messages` behavior and add filters later.

`GET /api/ai-messages/<thread_id>`

- Read-only thread/timeline payload.
- Returns task, messages, reviews, dispatch jobs, handoffs, heartbeats, approvals, and safety summary.

`POST /api/tasks/<task_id>/messages`

- Append a message to an existing task.
- Allowed roles: `planner`, `executor`, `reviewer`, `tester`, `ops`, `system`.
- Should sanitize text and reject token/secret-like content.
- Does not execute code or external writes.

`POST /api/tasks/<task_id>/handoff`

- Create a `handoff_logs` record from a task thread.
- Stores `conversation_ref=ai-task:<task_id>`.
- Does not deploy, push, or write infrastructure.

`POST /api/tasks/<task_id>/review`

- Create a reviewer message and optional review status.
- May call configured reviewer provider in a later phase.
- MVP Phase 1 can support manual reviewer message only.

`GET /api/tasks/<task_id>/timeline`

- Read-only normalized timeline.
- Combines task events, `ai_messages`, `dispatch_jobs`, `agent_runs`, `handoff_logs`, `ai_heartbeats`, and `approval_requests`.
- Should return safety flags such as `high_risk_action_detected`, `approval_required`, and `execution_allowed=false`.

## 7. Safety Rules

- Read-only first.
- No automatic repo writes.
- No automatic deploy.
- No automatic backend restart.
- No automatic `git push`.
- No Cloudflare/DNS/SSL/redirect/Nginx write.
- No registrar write.
- No DB schema migration without a separate explicit phase.
- No `cf_batch.py` execution.
- No `cf_batch_devpilot_bridge.py` execution.
- No `--apply` or `--confirm-real-write` from AI-to-AI flows.
- No token, secret, Authorization header, cookie, session, password, private key, or decrypted credential output.
- High-risk actions require Approval Center and explicit human authorization.
- AI messages may propose high-risk work, but the system must label such proposals as plans only.
- Generated code or sandbox artifacts may not be applied to a project repo in the MVP.
- External runner execution must remain in dry-run or queued state until a separate worker phase is approved.

## 8. MVP Phases

### Phase 1: Read-only thread board

- Add read-only message/thread views.
- Reuse `tasks`, `ai_messages`, `handoff_logs`, `ai_heartbeats`, `dispatch_jobs`, and `approval_requests`.
- No new execution paths.
- No DB migration if feasible by deriving virtual threads from task id and `raw_response.task_id`.

### Phase 2: Manual AI handoff

- Add manual endpoint/UI to attach a message or handoff to a task.
- Use existing `save_handoff()` and `ai_messages`.
- Human confirms before handoff is created.

### Phase 3: Reviewer loop

- Add reviewer message creation.
- Initial mode can be manual reviewer note.
- Later mode can call Gemini/OpenAI reviewer and store result in `ai_messages`.
- Reviewer never executes external writes.

### Phase 4: Worker dry-run

- Connect `dispatch_jobs` and `agent_runs` to the thread board.
- Worker may report plan/test/diff summaries only.
- No deploy, push, DNS, Cloudflare, SSL, redirect, Nginx, or registrar writes.

### Phase 5: Approval-gated execution

- Only after Phases 1-4 are stable.
- High-risk next steps create `approval_requests`.
- Execution remains blocked unless a separate approved phase explicitly permits a specific action.

## 9. Acceptance Criteria

- AI task thread can be viewed from a task id.
- Messages are grouped by task/thread.
- Planner, executor, reviewer, tester/ops, and system messages are visually distinct.
- Handoff chain is visible.
- Reviewer output is visible.
- Heartbeat status for related agents is visible.
- Related dispatch jobs and agent runs are visible.
- Approval state is visible.
- High-risk action proposals are labeled plan-only.
- No high-risk action executes automatically.
- No token or secret-like text is displayed.
- Existing AI Console task and message functionality continues to work.

## 10. Implementation Plan

Likely files to modify in a later implementation phase:

- `app.py`
  - Add timeline/query helpers.
  - Add read-only routes and APIs.
  - Add message append/review/handoff endpoints only after Phase 1.
- `templates/base.html`
  - Add navigation entry for AI Messages or AI Threads.
- `templates/ai_console.html`
  - Add thread panel and pending-review summary.
- `templates/ai_task_detail.html`
  - Add or link to full task thread timeline.
- New template: `templates/ai_messages.html`
  - Global message board.
- New template: `templates/ai_thread.html`
  - Task/thread timeline.
- Tests
  - Add route smoke tests for `/ai-messages`, `/tasks/<task_id>/thread`, and timeline APIs.
  - Add tests for grouping by `raw_response.task_id`.
  - Add tests that high-risk text is flagged plan-only.
  - Add tests that message append does not execute deploy/DNS/git/Cloudflare functions.
  - Add tests that token-like content is rejected or redacted.

Safe rollout order:

1. Add read-only timeline builder using existing tables.
2. Add read-only API `GET /api/tasks/<task_id>/timeline`.
3. Add read-only `/tasks/<task_id>/thread` UI.
4. Add `/ai-messages` global board.
5. Add manual message append endpoint with secret scanning.
6. Add manual task handoff creation endpoint.
7. Add reviewer message endpoint.
8. Add tests for safety gates and route smoke coverage.
9. Deploy only after a separate controlled deploy approval.

Recommended validation for implementation phase:

```powershell
python -m py_compile app.py services/ai_tasks.py
python -m unittest discover -s tests
git diff --check
```

## 11. Current Gaps

- No explicit `thread_id` field yet.
- `ai_messages` links to tasks indirectly through `raw_response.task_id`.
- No global `/ai-messages` UI route yet.
- No normalized task timeline API yet.
- No direct task message append endpoint yet.
- No direct task review endpoint yet.
- Handoff is project-level and does not yet have a formal task/thread relation beyond possible `conversation_ref`.
- Approval requests do not yet have a generalized thread/task reference model.
- Claude is available in preview/sandbox flow, but `call_task_provider("claude")` is still not implemented for regular `tasks`.
- AI Center Fleet is read-only and not merged into DevPilot's task/message data model.
