# DevPilot Automation Operating Runbook

Date: 2026-05-20
Status: active operating runbook, docs-only

## Purpose

This runbook describes how the operator and Codex should work together on DevPilot automation tasks.

## Operating Model

The standard loop is:

1. Operator states intent.
2. Assistant converts intent into a Codex-ready instruction.
3. Codex performs only the allowed work.
4. Codex reports summary, files, commands, verification, safety, commit, and status.
5. Assistant evaluates the result and gives the next instruction.

The loop should preserve explicit approval gates for runtime changes, deploys, rollback, NAS operations, secrets, `.env`, provider live calls, and CI/CD behavior changes.

## Standard Phase Flow

1. Preflight.
2. Classification.
3. Edit / verify.
4. Commit / push if allowed.
5. Report.
6. Ledger update.
7. State index update.

## Preflight Checklist

Run before edits:

```powershell
git status -sb
git log --oneline -8
```

Confirm:

- Branch is `main`.
- Working tree is clean.
- Latest expected commit is present.
- Task class is known.
- Forbidden actions are explicit.

Stop if the working tree is unexpectedly dirty.

## Execution Rules

- Docs-only tasks can proceed if explicitly requested.
- Read-only tasks can proceed without editing.
- Runtime tasks require explicit approval before edits.
- Deploy and rollback require explicit approval before commands.
- Provider, secrets, and `.env` tasks require explicit approval before access.
- Stop if scope changes.
- Stop if a task that began as docs-only requires runtime changes.
- Stop if a legacy route result conflicts with an active route decision.

## Report Rules

Codex reports must include:

- Summary.
- Files changed.
- Commands run.
- Verification.
- Safety confirmation.
- Commit.
- Final status.
- Latest log.
- Follow-up candidates.

If a commit was created, include:

- Commit hash and message.
- Final `git status -sb`.
- Latest `git log --oneline -5`.

## Recovery / Route Verification Rule

A `404` on a legacy route is not automatically a recovery failure.

Before classifying an issue as production recovery:

1. Verify the active route.
2. Verify expected authentication behavior.
3. Verify whether the route is legacy / non-active.
4. Check whether the behavior was already documented.

AI Handoffs precedent:

- Active route: `/ai-handoffs`.
- Legacy / non-active route: `/admin/devpilot-handoffs`.
- A `404` on `/admin/devpilot-handoffs` is acceptable.
- Smoke tests should use `/ai-handoffs`.
- Optional redirect is a separate runtime change requiring approval.

## Human Approval Phrases

Examples that count as explicit approval:

- `Approved: runtime patch only, no deploy.`
- `Approved: add redirect patch and tests, do not push.`
- `Approved: deploy to staging only.`
- `Approved: rollback production using the documented runbook.`
- `Approved: one provider live call with this exact provider, model, prompt, and budget cap.`

Examples that do not count as explicit approval:

- Vague status reports.
- Asking for explanation.
- Saying `continue` without specifying risk class or allowed actions.
- Reporting that something is broken.
- Asking whether a thing is possible.

## Records To Update

After major automation governance work:

- Add or update `docs/automation_task_ledger.md`.
- Add or update `docs/automation_state_index.md`.
- Keep related release notes and recovery docs linked to the governance docs.
