# Level 7 Safe AI Automation Scaffold

Date: 2026-05-18
Status: implemented preview-only scaffold, no execution

## Level 7 Scope

Level 7 gives DevPilot a safe automation scaffold:

- Low-risk requests can be translated into reviewable task queue items.
- Medium-risk requests can produce a PR/task queue patch/reviewable plan.
- High-risk requests are classified as `approval_draft_only` or `blocked`.
- High-risk requests are not executed.
- Live provider, DNS, Cloudflare, Nginx, SSL, R2, deploy, worker, and production mutations remain disabled.

## What Is Implemented

Preview-only UI/API:

```text
GET /admin/ai-coding-agent-task-generator
POST /api/admin/ai-coding-agent-task-generator/preview
GET /admin/approval-object-preview
POST /api/admin/approval-object-preview
```

Implemented behavior:

- Task Queue Generator preview classifies request risk and execution mode.
- Low-risk docs-only requests can produce a Markdown task queue item preview.
- Read-only UI/API requests are classified as medium risk.
- High-risk live provider, DNS, Cloudflare, Nginx, SSL, R2, deploy, worker, and production mutation requests are classified as `approval_draft_only` or `blocked`.
- Approval Object Preview returns a draft-only approval payload with required roles, abort conditions, safety checks, and no persistence.
- Level 7B Approval Draft Persistence can save draft approval objects for review.

## What Remains Disabled

- No generated task is executed.
- No generated task is written to `docs/ai_coding_agent_task_queue.md`.
- No Codex call is made.
- No commit or push is allowed.
- Approval objects may be saved only as Level 7B drafts.
- No `approval_requests` row is created.
- No provider live call is made.
- No usage log or generation result is written.
- No DNS, Cloudflare, Nginx, SSL, registrar, R2, deploy, worker, project/task/phase/handoff, or production mutation is executed.

## Task Generator Classification Rules

| Request | Classification | Risk | Approval |
| --- | --- | --- | --- |
| Docs-only | `docs_only` | low | false |
| Read-only UI/API | `read_only_ui` | medium | usually false until scope grows |
| Test-only | `test_only` | low | false |
| Live provider / DNS / deploy / Cloudflare / SSL / Nginx / R2 / production mutation | `approval_draft_only` or `blocked` | high or critical | true |
| Secrets, raw keys, `.env`, auth headers, bearer tokens, key hashes | `blocked` | critical | true |
| Ambiguous request | `blocked` | critical | true |

## Approval Preview Behavior

Approval preview supports these draft types:

- `external_ai_live_verification`
- `domain_execution`
- `deploy`
- `worker_execution`
- `provider_budget_change`
- `project_task_phase_mutation`

The preview response includes:

- `approval_object_created: false`
- `execution_allowed: false`
- `status: draft_preview`
- `execution_mode: none`
- required approvals
- safety checks
- abort conditions
- empty audit events

## Safety Boundaries

- Read-only by default.
- Preview-only for task generation and approval drafts.
- No queue write.
- No approval persistence.
- No provider live call.
- No infrastructure mutation.
- No production mutation.
- No worker execution.
- No secrets or `.env` access.

## Next Phases

### Level 7B - Approval Draft Persistence

Implemented in `docs/level_7b_approval_draft_persistence.md`.

Persist approval drafts only. No approve, reject, execute, or `approval_requests` workflow exists in this phase.

### Level 7C - Approval Inbox

Add an owner/admin inbox for approval drafts, missing approvals, rejected approvals, and stale dry-run snapshots.

### Level 7D - Runner Consumes Low-risk Tasks

Allow reviewed low-risk task queue patches to reach the scheduled runner. The runner still must not infer work or auto-commit/push unless the task explicitly says so.

### Level 7E - High-risk Approval Routing

Route high-risk requests into approval drafts and required approver workflows. Execution remains disabled.

### Level 8 - Limited Execution Adapters

Only after explicit approval, add narrowly scoped execution adapters. Live provider, DNS, Cloudflare, Nginx, SSL, R2, deploy, worker, and production actions require separate implementation phases.

## Non-Goals

This scaffold does not:

- execute generated tasks
- call Codex
- write the task queue
- create approval objects
- create `approval_requests`
- call Gemini or Claude
- deploy
- mutate DNS, Cloudflare, Nginx, SSL, registrar, R2, workers, projects, tasks, phases, handoffs, or production settings
- change `.env`
- touch secrets
