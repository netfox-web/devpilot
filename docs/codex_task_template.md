# Codex Task Template

Date: 2026-05-20
Status: reusable operator template, docs-only

Use this template when giving Codex DevPilot tasks. Pair it with `docs/automation_decision_gates.md` before execution.

## Template

````markdown
# Task title

## Context

- Repo:
- Current branch:
- Relevant production/staging context:
- Relevant prior commits:

## Task class

- Class A - Docs-only update
- Class B - Read-only verification / smoke test
- Class C - Runtime code change
- Class D - Deploy / restart / Docker / NAS / staging operation
- Class E - Production recovery / rollback
- Class F - Provider live call / secrets / .env

## Safety constraints

- no deploy
- no restart
- no build
- no Docker action
- no NAS/staging/production mutation
- no secrets or `.env`
- no provider live call
- no runtime code change unless explicitly approved

## Allowed actions

- ...

## Forbidden actions

- ...

## Required checks

- `git status -sb`
- `git log --oneline -5`
- ...

## Implementation steps

1. ...
2. ...
3. ...

## Verification commands

```powershell
git diff --check
git status -sb
git diff --stat
```

## Commit instructions

- Commit allowed: yes/no
- Push allowed: yes/no
- Exact commit message:

## Required report format

- Summary
- Files changed
- Commands run
- Verification result
- Safety confirmation
- Commit hash, if committed
- Final `git status -sb`
- Latest `git log --oneline -5`, if committed
- Runtime code changed: yes/no
- Deploy/restart/build/Docker/NAS/staging/secrets/.env/provider live call occurred: yes/no
````

## Example 1 - Docs-only Task

Task class: Class A - Docs-only update

Allowed:

- Edit docs.
- Run `git diff --check`, `git status -sb`, and `git diff --stat`.
- Commit and push only if the operator explicitly requests it.

Forbidden:

- Runtime code changes.
- Deploy, restart, build, Docker, NAS, staging, secrets, `.env`, or provider live call.

Example instruction:

```markdown
Update docs to record the confirmed production route. This is docs-only. Commit and push if only docs changed.
```

## Example 2 - Read-only Smoke Test Task

Task class: Class B - Read-only verification / smoke test

Allowed:

- Run unauthenticated `curl -I` checks.
- Confirm redirects and HTTP status codes.
- Inspect safe local output.

Forbidden:

- Login with credentials unless explicitly approved.
- Mutate app state.
- Call provider live routes.
- Deploy, restart, build, Docker, NAS, or staging mutation.

Example instruction:

```markdown
Run read-only HTTPS smoke checks against `/`, `/login`, and `/ai-handoffs`. Do not log in and do not mutate state.
```

## Example 3 - Runtime Redirect Task Requiring Approval

Task class: Class C - Runtime code change

This must not be executed without explicit approval.

Example instruction:

```markdown
Prepare a patch to redirect `/admin/devpilot-handoffs` to `/ai-handoffs`. Do not commit, push, deploy, or restart until separately approved.
```

Required gate:

- Explicit approval to change runtime code.
- Tests identified before commit.
- Separate deployment approval before production use.

## Example 4 - Deploy Task Requiring Approval

Task class: Class D - Deploy / restart / Docker / NAS / staging operation

This must not be executed without explicit approval.

Example instruction:

```markdown
Deploy the approved commit to production 5010 using the documented Docker Compose command. Do not change Nginx, DNS, Cloudflare, SSL, secrets, or `.env`.
```

Required gate:

- Explicit production deploy approval.
- Exact target path.
- Exact service/container.
- Rollback plan or backup reference.
- Post-deploy verification commands.

## Example 5 - Provider Live Call Task Requiring Approval

Task class: Class F - Provider live call / secrets / .env

This must not be executed without explicit approval.

Example instruction:

```markdown
Run one approved Gemini live verification call using the fixed prompt and budget cap. Do not print keys or full prompts/responses.
```

Required gate:

- Explicit provider live-call approval.
- Provider, model, prompt, budget, and abort conditions.
- Secret handling policy.
- Logging and redaction plan.
- Confirmation that no unrelated provider call will execute.
