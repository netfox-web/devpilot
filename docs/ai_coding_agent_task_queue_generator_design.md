# AI Coding Agent Task Queue Generator Design

Date: 2026-05-18
Status: implemented as preview-only UI/API in Level 7; no execution

## Purpose

Task Queue Generator is the future safe translation layer that converts high-level requests into explicit pending task items in `docs/ai_coding_agent_task_queue.md`.

It does not execute tasks. It does not call Codex. It does not commit. It does not push.

It only produces a reviewable task queue patch, pull request, or draft that a human or a later approved workflow can inspect before the scheduled runner sees a pending task.

Level 7 implementation status: preview-only UI/API is available at `/admin/ai-coding-agent-task-generator` and `/api/admin/ai-coding-agent-task-generator/preview`. It still does not write `docs/ai_coding_agent_task_queue.md`, call Codex, create approvals, commit, push, or execute tasks.

## Current Runner Model

Current Phase 1 runner behavior:

- The runner reads `docs/ai_coding_agent_task_queue.md`.
- If there is no unchecked task, it writes a log entry and stops without modifying files.
- If there is a pending task, it may invoke Codex according to that explicit task.
- The runner does not query GitHub Issues.
- The runner does not depend on `gh`.
- The runner should not automatically create approval objects.
- The runner should not infer work from broad repository context.

## Inputs

Potential future input sources:

- ChatGPT GitHub connector task.
- GitHub Issue with label `codex-task`.
- Admin note.
- Analyst decision.
- Approval Object draft.
- External Project Health Planner recommendation.
- Domain Execution Dry-run selected preview.
- External AI Live Verification Gate checklist outcome.

Each input must be normalized into a narrow task intent before any queue patch is proposed.

## Output

Task Queue Generator output is a task queue patch, not execution:

```markdown
- [ ] TASK-ID: Short title
  - Source: chatgpt|github_issue|admin_note|analyst_decision|approval_object
  - Scope: ...
  - Allowed files:
    - ...
  - Forbidden files:
    - .env
    - data/
    - uploads/
    - logs/
    - .local_backups/
  - Risk level: low|medium|high|critical
  - Execution mode: docs_only|read_only_ui|test_only|approval_draft_only|blocked
  - Verification:
    - ...
  - Commit/push: no|yes_with_exact_message
  - Approval required: true|false
  - Safety:
    - no deploy
    - no secrets
    - no provider live call
    - no DNS write
    - no Cloudflare write
    - no Nginx write
    - no SSL write
    - no R2 mutation
```

## Generator Flow

1. Ingest one source request.
2. Classify request source and action category.
3. Reject or mark blocked if the request is ambiguous, broad, secret-bearing, or execution-capable without approval.
4. Determine allowed files and forbidden files.
5. Determine execution mode.
6. Attach verification commands.
7. Attach commit/push policy.
8. Attach approval requirement.
9. Produce a patch to `docs/ai_coding_agent_task_queue.md`.
10. Stop. Do not run Codex, commit, push, deploy, or mutate runtime data.

## Request Classification

| Request Type | Default Execution Mode | Approval Required | Notes |
| --- | --- | --- | --- |
| Docs planning task | `docs_only` | false | Safe when allowed files are docs-only. |
| Read-only UI/API implementation | `read_only_ui` | false or true by risk | Must include tests and no execution helpers. |
| Test-only verification | `test_only` | false | Must not write runtime data except test artifacts already ignored. |
| Approval Object draft | `approval_draft_only` | true | Creates approval intent only in a future phase, not execution. |
| Live provider call | `blocked` | true | Requires approval gate before any executable task. |
| DNS / Cloudflare / Nginx / SSL / R2 / deploy | `blocked` | true | Must go through approval object and dry-run snapshot first. |
| Worker execution | `blocked` | true | No background execution from queue generation. |
| Secret or `.env` request | `blocked` | true | Must be rejected or escalated manually. |

## Safety Validation

The generator should refuse to create a runnable pending task when:

- The source request contains raw secrets, tokens, auth headers, bearer strings, or `.env` values.
- Allowed files are missing or too broad.
- Forbidden files are not listed.
- Runtime code changes are requested without tests.
- Commit/push policy is ambiguous.
- A deploy, DNS write, Cloudflare write, Nginx write, SSL change, R2 mutation, provider live call, worker execution, or project/task mutation is requested without an approval object.
- The request asks the runner to infer work from repository-wide context.
- The task would require external network access not explicitly approved.

## Task ID Convention

Recommended ID format:

```text
YYYY-MM-DD-source-short-slug
```

Examples:

```text
2026-05-18-github-issue-12-readiness-rollup
2026-05-18-admin-note-domain-docs-update
2026-05-18-approval-draft-gemini-live-check
```

## Patch Review Requirements

Every generated queue patch should be reviewable before merge:

- Shows exactly one new pending task unless batch generation is explicitly requested.
- Keeps existing completed task history.
- Does not remove safety rules.
- Does not mark a task complete.
- Does not modify runtime code.
- Does not change runner behavior.
- Does not create approval objects.

## Relationship To Approval Objects

The generator may read or reference an Approval Object draft in a future phase, but it should not create or approve one by default.

Recommended boundary:

- Approval Object Workflow models high-risk intent and approvals.
- Task Queue Generator translates approved or low-risk intent into a queue item.
- Scheduled runner consumes only explicit queue items.
- Execution remains disabled unless a later phase explicitly authorizes it.

## Relationship To GitHub Issues

The scheduled runner does not query GitHub Issues.

If GitHub Issues are used as source input, a separate generator flow should:

- Read issues via a controlled integration or human-provided context.
- Require label `codex-task`.
- Convert only one issue into one explicit queue patch.
- Preserve issue URL and number in the `Source` field.
- Avoid direct issue polling from the scheduled runner.

## Relationship To ChatGPT

ChatGPT may propose task queue entries, but the queue file remains the runner source of truth.

Any ChatGPT-generated task should include:

- exact scope
- allowed files
- forbidden files
- verification
- commit/push policy
- safety boundaries
- approval requirement

## Non-Goals

This design does not:

- execute Codex
- invoke the scheduled runner
- commit or push
- query GitHub Issues from the runner
- create approval objects
- approve high-risk actions
- call Gemini or Claude
- deploy
- write DNS, Cloudflare, Nginx, SSL, registrar, R2, or production settings
- change `.env`
- touch secrets
- mutate project, task, phase, or handoff records

## Acceptance Criteria

Phase 9 design is ready for future implementation planning when:

- The task item template is accepted.
- Required safety fields are agreed.
- Source-to-task classification rules are accepted.
- Approval Object boundaries are clear.
- The runner remains local-queue-driven and does not gain GitHub issue polling.
- Queue generation remains reviewable before a pending task reaches the runner.
