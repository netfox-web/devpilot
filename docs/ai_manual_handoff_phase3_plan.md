# AI-to-AI Manual Handoff Phase 3 Plan

Date: 2026-05-12
Status: design only, no implementation in this phase

## 1. Phase 3 Objective

Phase 3 should improve the operational experience around AI-to-AI manual handoffs after the Phase 2 MVP has been deployed and production verified.

The focus is review, auditability, safer status management, and clearer handoff context. Phase 3 should make it easier for operators and authorized AI clients to find pending work, understand why a handoff exists, review risk, and advance the handoff lifecycle without accidentally triggering task execution or project mutation.

Phase 3 builds on these completed commits:

- `62a001d feat: add side-effect-free AI task manual handoff MVP`
- `3b6251d docs: record AI manual handoff production verification`

## 2. Non-Goals

Phase 3 is not an execution phase.

Non-goals:

- No automatic provider calls after handoff creation.
- No worker execution.
- No automatic task status changes.
- No automatic project phase, status, progress, or next-step changes.
- No approval request creation as a side effect of handoff create, accept, complete, or reject.
- No deploy, DNS, SSL, Cloudflare, redirect, Nginx, registrar, or infrastructure changes.
- No migration unless a later implementation phase explicitly approves one.
- No replacement of the existing `handoff_logs` storage model unless a later architecture phase approves it.

## 3. Proposed Features

Phase 3 feature candidates:

- Handoff filters and search on `/ai-handoffs`.
- Pending handoff review queue for operators.
- Handoff detail panel or expanded row.
- Clear status badges for `pending`, `accepted`, `completed`, and `rejected`.
- Clear risk indicators for `low`, `medium`, `high`, `critical`, `deploy`, `dns`, `cloudflare`, `ssl`, `redirect`, `nginx`, `registrar`, and `production`.
- Better reason and next-step display with preserved line breaks and truncation controls.
- Handoff chain visualization in `/tasks/<task_id>/thread`.
- Permission checks for accept, complete, and reject actions.
- Invalid status transition prevention.
- Optional reject reason requirement, or required reject reason for high-risk handoffs.
- Read-only audit export for admin review.
- Admin review view for handoff history and safety metadata.
- Explicit display of `execution_allowed=false` on API and UI surfaces.

## 4. Data Model Constraints

Phase 3 should continue to use `handoff_logs` unless a separate migration phase is approved.

Existing Phase 2 mapping remains valid:

| Field | Storage |
| --- | --- |
| `task_id` | `conversation_ref = ai-task:<task_id>` and `api_payload.task_id` |
| `from_agent` | `source`, `agent_name`, and `api_payload.from_agent` |
| `to_agent` | `api_payload.to_agent` |
| `reason` | `summary` and `api_payload.reason` |
| `next_step` | `next_steps` and `api_payload.next_step` |
| `status` | `api_payload.status` and `api_payload.handoff_status` |
| `accepted_at` | `api_payload.accepted_at` |
| `completed_at` | `api_payload.completed_at` |
| `rejected_at` | `api_payload.rejected_at` |

Constraints:

- New UI/API behavior must not require changing real task or project rows.
- Handoff lifecycle transitions should only update `handoff_logs.api_payload`.
- If additional audit metadata is needed, prefer `api_payload.audit` first.
- If indexing becomes necessary for performance, document a separate migration plan and rollback plan before implementation.
- Any export must be read-only and must avoid exposing secrets, tokens, credentials, or raw sensitive payloads.

## 5. UI Changes

### `/ai-handoffs`

Improve the handoff board as an operator review surface:

- Add filters for status, risk level, source agent, target agent, project, and task.
- Add keyword search across reason, next step, source agent, target agent, and task title.
- Add quick tabs for all, pending, accepted, completed, rejected, and high risk.
- Add compact status and risk badges.
- Add row expansion or a side panel showing full reason, next step, timeline timestamps, and safety metadata.
- Add a pending review queue section sorted by risk and age.

### `/tasks/<task_id>/thread`

Improve timeline readability:

- Group related handoffs into a visible chain.
- Show status transitions with timestamps.
- Show source and target agent labels clearly.
- Keep execution controls absent unless a later approval-gated execution phase authorizes them.
- Show read-only safety flags: provider not called, worker not executed, external writes not performed.

### `/tasks/<task_id>/handoff`

Improve handoff creation and review:

- Make risk selection clearer.
- Show a preview of the target task, project, and current lifecycle state.
- Add better validation hints for reason and next step.
- Warn that handoff is coordination only and does not execute work.

## 6. API Changes

Potential API enhancements:

- Extend `GET /api/ai-handoffs` with search and queue filters.
- Add normalized detail response for `GET /api/handoffs/<handoff_id>`.
- Add an audit-friendly export endpoint such as `GET /api/ai-handoffs/export?format=json` for admins only.
- Add structured transition validation responses for accept, complete, and reject.
- Add optional `reject_reason` validation.
- Return transition metadata consistently:
  - `previous_status`
  - `next_status`
  - `transition_allowed`
  - `transition_reason`
  - `execution_allowed=false`

Status transition rules should be explicit:

| From | Allowed To |
| --- | --- |
| `pending` | `accepted`, `rejected` |
| `accepted` | `completed`, `rejected` |
| `completed` | none by default |
| `rejected` | none by default |

Any reopen behavior should require a separate design decision.

## 7. Security and Permission Checks

Phase 3 should make handoff lifecycle permissions explicit.

Suggested policy:

- Owners and admins can list, create, accept, complete, reject, hide, restore, and export handoffs.
- AI clients with the `ai` role can list and create handoffs.
- AI clients can accept or complete only when explicitly allowed by role policy.
- Reject actions should require owner/admin by default unless the handoff target role is trusted.
- Audit export should be owner/admin only.
- High-risk handoffs should show approval-required state but must not create approval requests automatically.

Security requirements:

- Never expose secrets in export responses.
- Redact or omit raw payload fields that may contain tokens, credentials, API keys, SSH material, environment variables, cookies, or authorization headers.
- Preserve existing authentication requirements on UI and API routes.
- Return `403` for unauthorized lifecycle actions.

## 8. Audit and Logging Expectations

Phase 3 should improve auditability without expanding side effects beyond `handoff_logs`.

Expected audit data:

- Who initiated the transition, when available.
- Previous status.
- New status.
- Transition timestamp.
- Optional reason for reject.
- Whether the handoff was high risk.
- Whether execution was allowed. This should remain `false` in Phase 3.

Preferred storage:

- Add audit entries inside `api_payload.audit.transitions` if no migration is approved.
- Keep `created_at`, `accepted_at`, `completed_at`, and `rejected_at` as normalized timestamp fields inside `api_payload`.

Logging expectations:

- Application logs should record route status and errors only.
- Do not log raw secret-bearing payloads.
- Do not log API tokens, authorization headers, cookies, SSH material, or environment values.

## 9. Test Plan

Unit and route tests should cover:

- `/ai-handoffs` filter and search rendering.
- `GET /api/ai-handoffs` filters for status, risk, project, task, source agent, and target agent.
- Handoff detail response normalization.
- Valid lifecycle transitions.
- Invalid lifecycle transitions returning `400` or `409`.
- Unauthorized lifecycle transitions returning `403`.
- Optional or required reject reason behavior.
- Task thread chain rendering.
- Audit export redaction.
- No mutation of:
  - task status
  - project phase status
  - project status
  - project progress
  - project next steps
  - approval request count
- No calls to provider, worker, sandbox apply, repo write, deploy, Cloudflare, DNS, SSL, Nginx, redirect, registrar, or git push helpers.

Production verification should use one clearly disposable project/task and clean it up after checking:

- UI routes load.
- API lifecycle works.
- `handoff_logs.conversation_ref = ai-task:<task_id>`.
- `api_payload` contains source, target, status, reason, next step, and lifecycle timestamps.
- Protected task/project fields remain unchanged.
- Logs contain no tracebacks or application errors.

## 10. Rollout Plan

Recommended rollout:

1. Prepare Phase 3 implementation as a small UI/API change set.
2. Run local compile and focused tests.
3. Run full unit test discovery if the change touches shared route helpers.
4. Commit and push after review.
5. Build a production Docker image from the verified commit.
6. Recreate only the DevPilot app container from the production compose directory.
7. Run post-deploy smoke checks.
8. Run one disposable lifecycle verification.
9. Record the production verification note.

Rollback:

- Keep the previous Docker image tag available.
- If UI/API errors appear, recreate the app container with the previous known-good image.
- Preserve production data volumes.
- Do not prune images or delete volumes during rollback.

## 11. Explicit Safety Boundaries Inherited From Phase 2

Phase 3 inherits all Phase 2 safety boundaries:

- Manual handoff only.
- Side-effect-free helpers only write or update `handoff_logs`.
- No task status mutation.
- No project phase mutation.
- No project status mutation.
- No project progress mutation.
- No project next-step mutation.
- No provider call.
- No worker execution.
- No sandbox apply.
- No repo write.
- No deploy.
- No git push.
- No approval request creation.
- No Cloudflare, DNS, SSL, redirect, Nginx, registrar, or infrastructure write.
- Timeline and thread integration remain read/display only.

## 12. Open Questions

- Should AI clients be allowed to accept or complete handoffs, or should that remain owner/admin only?
- Should reject reason be required for all rejects or only for high-risk handoffs?
- Should completed or rejected handoffs ever be reopenable?
- Should the pending review queue be global or scoped by project, suite, provider, or target agent?
- What audit export formats are needed first: JSON, CSV, or admin-only HTML?
- Should high-risk handoffs link to Approval Center without creating approval requests automatically?
- Should handoff chains support parent/child relationships, or infer the chain from task and timestamp only?
- Should Phase 3 add database indexes, or keep filtering in the existing `handoff_logs` model until volume requires migration?
- What redaction rules should apply to `api_payload` exports?
