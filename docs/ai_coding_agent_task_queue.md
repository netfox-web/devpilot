# AI Coding Agent Task Queue

This file is the local scheduled-runner task source for DevPilot AI coding agents.

Final status:

```text
AI_CODING_AGENT_TASK_QUEUE_READY
```

## Purpose

Use this file to give the local scheduled Codex runner explicit work without requiring GitHub Issues access or the GitHub CLI.

The scheduled runner reads this file only. It does not query GitHub Issues directly and does not depend on `gh`.

## Queue Rules

- Pending scheduled work must be written as an unchecked Markdown task item under `Pending Tasks`.
- If there is no unchecked task item, the runner writes a no-pending-task log entry and stops without modifying files.
- Keep tasks narrow, explicit, and safe.
- Do not use this queue to request deployment, secret access, `.env` changes, production setting changes, provider live calls, DNS writes, SSL writes, Nginx writes, Cloudflare writes, R2 writes, or infrastructure mutation.
- Codex must not commit or push unless the task explicitly says to commit and push.

## Pending Tasks

No pending scheduled Codex task.

## Task Template

```markdown
- [ ] TASK-ID: Short task title
  - Scope: What Codex should do.
  - Allowed files: Paths Codex may modify.
  - Verification: Commands Codex should run.
  - Commit/push: yes/no, with exact rules.
  - Safety: Extra boundaries for this task.
```

## Completed Tasks

- [x] 2026-05-18: Add local task queue file for Phase 1 runner reliability.
