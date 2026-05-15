# Codex Scheduled Task Runner

This runbook defines a safe scheduled-task pattern for letting local Codex periodically check whether DevPilot has new AI coding-agent work, without requiring the user to paste logs back into ChatGPT.

Final status:

```text
CODEX_SCHEDULED_TASK_RUNNER_RUNBOOK_READY
```

## Objective

Allow a local Windows machine to wake Codex on a schedule, check for explicit tasks, update the GitHub handoff status, and push results back to GitHub for ChatGPT to continue from.

Target flow:

```text
Windows Task Scheduler
  -> PowerShell runner
  -> local repo sync/status check
  -> Codex task check
  -> docs/ai_coding_agent_handoff_status.md update
  -> commit + push, when safe and explicitly allowed by runner rules
  -> ChatGPT reads GitHub and continues
```

## Current Automation Level

Current verified flow:

```text
Codex local work
  -> Codex commit + push to GitHub
  -> user says: Codex 已回填 GitHub，往下接
  -> ChatGPT reads GitHub commits, diffs, and handoff docs
```

This runbook moves the project toward a scheduled polling model while keeping GitHub as the synchronization boundary.

## Boundaries

This runbook does not grant ChatGPT direct shell access to the user's local Codex TUI or local machine.

Allowed automation boundary:

```text
Local scheduled runner
  -> local Codex CLI
  -> GitHub repo
  -> ChatGPT GitHub connector
```

Disallowed by default:

- production deployment
- secret access or mutation
- `.env` changes
- infrastructure changes
- database migrations
- broad runtime code rewrites
- destructive shell commands
- direct local shell bridge exposed to ChatGPT

## Task Source

Use a narrow task source. Do not let scheduled Codex infer broad work from the whole repository.

Preferred source:

```text
docs/ai_coding_agent_handoff_status.md
```

Optional future source:

```text
GitHub issues labeled codex-task
```

Recommended rule:

```text
No explicit pending task -> update handoff status with no pending task -> stop.
```

## Safe Runner Policy

The scheduled runner should operate under these default rules:

- Run read-only checks first.
- Pull only when refs are safe and the worktree is clean.
- Prefer docs-only work.
- Prefer topic branches for changes.
- Do not commit unexpected files.
- Do not push if secrets, `.env`, runtime code, production settings, or infrastructure files changed unexpectedly.
- Do not deploy.
- If blocked or uncertain, update the handoff status and stop.

## Suggested Directory Layout

```text
scripts/
  codex_check_tasks.ps1
logs/
  codex_check_tasks.log
```

If `scripts/` or `logs/` do not exist locally, create them on the local machine. Only commit scripts when they are reviewed and intentionally added to the repo.

## PowerShell Runner Template

This template is intended for local use. Review and adapt before enabling it.

```powershell
$Repo = "E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager"
$Log = "$Repo\logs\codex_check_tasks.log"

New-Item -ItemType Directory -Force -Path "$Repo\logs" | Out-Null
Set-Location $Repo

Add-Content $Log "`n===== $(Get-Date -Format s) Codex task check start ====="

# Read-only baseline checks.
git status -sb 2>&1 | Add-Content $Log
git log --oneline -5 2>&1 | Add-Content $Log
git rev-parse HEAD 2>&1 | Add-Content $Log
git rev-parse origin/main 2>&1 | Add-Content $Log
git ls-remote origin refs/heads/main 2>&1 | Add-Content $Log

$Prompt = @"
You are the scheduled DevPilot Codex runner.

Task source:
- docs/ai_coding_agent_handoff_status.md

Rules:
- First inspect current repo status.
- Do not deploy.
- Do not touch secrets or .env.
- Do not modify production settings.
- Do not modify runtime code unless the handoff file contains an explicit pending task requiring it.
- Prefer docs-only updates.
- If no explicit pending task exists, update docs/ai_coding_agent_handoff_status.md with a no-pending-task summary only.
- If blocked or uncertain, update the handoff status with blocked status and stop.
- If files changed, report git status, diff stat, and safety confirmation.
- Only commit and push when the changed files are expected and safe.
"@

# Confirm your installed Codex CLI supports exec mode before using this line.
$Prompt | codex exec --cd $Repo - 2>&1 | Add-Content $Log

Add-Content $Log "===== $(Get-Date -Format s) Codex task check end ====="
```

## Codex CLI Compatibility Check

Before scheduling, verify the local CLI supports non-interactive execution:

```powershell
codex --help
codex exec --help
```

If `codex exec` is unavailable, do not enable this runner as written. Use one of these alternatives:

- keep Codex interactive and manually start it
- use a GitHub issue / PR workflow only
- create a narrow local bridge later
- use another approved non-interactive agent runner

## Windows Task Scheduler Setup

Create a scheduled task that runs every 30 minutes:

```powershell
schtasks /Create /TN "DevPilot Codex Task Check" /SC MINUTE /MO 30 /TR "powershell.exe -ExecutionPolicy Bypass -File E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager\scripts\codex_check_tasks.ps1" /F
```

Run it manually:

```powershell
schtasks /Run /TN "DevPilot Codex Task Check"
```

Inspect task state:

```powershell
schtasks /Query /TN "DevPilot Codex Task Check" /V /FO LIST
```

Disable or remove it:

```powershell
schtasks /Delete /TN "DevPilot Codex Task Check" /F
```

## Recommended Handoff Status Update

Each scheduled run should update:

```text
docs/ai_coding_agent_handoff_status.md
```

Required fields:

```text
Latest Run
Summary
Files Reviewed
Files Changed
Diff Summary
Verification
Safety Confirmation
Recommended Next Step
```

If no task exists, write a concise no-op entry:

```text
Status: completed
Summary: No explicit pending Codex task was found.
Files Changed: docs/ai_coding_agent_handoff_status.md only
Recommended Next Step: ChatGPT may inspect GitHub or wait for the next task.
```

## Commit and Push Rules

Allowed default commit message for no-op handoff status updates:

```text
docs: update AI coding agent handoff status
```

For task-specific updates, use a specific docs or code message:

```text
docs: record scheduled Codex task check
```

or:

```text
fix: <specific safe fix>
```

Do not push if the diff includes unexpected paths.

## ChatGPT Follow-Up Pattern

After Codex pushes, the user can say:

```text
Codex 已回填 GitHub，往下接
```

ChatGPT should then:

1. Inspect latest commits.
2. Fetch the latest handoff status file.
3. Review changed files and diff.
4. Decide whether to open a PR, merge, or request a local follow-up.
5. Avoid asking the user to paste Codex logs unless GitHub lacks required information.

## Failure Modes

### Worktree is dirty before scheduled run

Action:

```text
Do not continue broad work. Update handoff status as blocked and report dirty files.
```

### GitHub network access blocked

Action:

```text
Do not retry indefinitely. Record the failure in logs and handoff status if possible.
```

### Permission denied on `.git/FETCH_HEAD`

Action:

```text
Record the permission error. Do not run elevated commands unless the user explicitly approves.
```

### `.pytest_cache` permission warning

Action:

```text
Treat as non-blocking if git status still shows no tracked or untracked project changes. Record it as a warning.
```

### Non-interactive Codex execution unavailable

Action:

```text
Do not enable scheduled autonomous execution. Keep manual Codex TUI or implement a reviewed bridge.
```

## Non-Goals

This scheduled runner does not implement:

- direct ChatGPT-to-local-Codex control
- production deployment automation
- secret rotation
- infrastructure mutation
- database migrations
- unrestricted shell execution
- unattended runtime code rewrites

## Safety Confirmation

This runbook is documentation-only. It records a proposed scheduled Codex task-check pattern and does not introduce app behavior, deployment, restart, rebuild, migration, infrastructure change, DNS/SSL/Nginx/Cloudflare/R2 change, provider call, worker/task execution, project/task/phase/approval mutation, or secret output.
