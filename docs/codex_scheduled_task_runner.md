# Codex Scheduled Task Runner

This runbook defines a safe scheduled-task pattern for letting local Codex periodically check whether DevPilot has new AI coding-agent work, without requiring the user to paste logs back into ChatGPT.

Implementation status: implemented in Phase 1 (`7e9d233`) as a local task-queue-driven runner. The runner reads `docs/ai_coding_agent_task_queue.md`, does not query GitHub Issues directly, does not require `gh`, and logs only when no pending task exists.

Final status:

```text
CODEX_SCHEDULED_TASK_RUNNER_RUNBOOK_READY
```

## Objective

Allow a local Windows machine to wake Codex on a schedule, check a local explicit task queue, and only invoke Codex when a pending task exists.

Target flow:

```text
Windows Task Scheduler
  -> PowerShell runner
  -> local repo sync/status check
  -> docs/ai_coding_agent_task_queue.md check
  -> no pending task: log only and stop
  -> pending task: Codex task check
  -> optional file changes only when the task explicitly allows them
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
  -> local task queue file
  -> local Codex CLI only when a pending task exists
  -> local git worktree
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

Required source:

```text
docs/ai_coding_agent_task_queue.md
```

Supporting context:

```text
docs/ai_coding_agent_handoff_status.md
```

Recommended rule:

```text
No unchecked task in docs/ai_coding_agent_task_queue.md -> write log only -> stop.
```

The scheduled runner must not query GitHub Issues directly and must not require `gh`.

## Safe Runner Policy

The scheduled runner should operate under these default rules:

- Run read-only checks first.
- Pull only when refs are safe and the worktree is clean.
- Prefer docs-only work.
- Prefer topic branches for changes.
- Do not commit unexpected files.
- Do not push if secrets, `.env`, runtime code, production settings, or infrastructure files changed unexpectedly.
- Do not deploy.
- If no pending task exists, do not modify files.
- If blocked or uncertain while a pending task exists, update the handoff status only if the task allows it, then stop.

## Suggested Directory Layout

```text
scripts/
  codex_check_tasks.ps1
docs/
  ai_coding_agent_task_queue.md
logs/
  codex_check_tasks.log
```

If `scripts/` or `logs/` do not exist locally, create them on the local machine. Only commit scripts when they are reviewed and intentionally added to the repo.

## PowerShell Runner Template

This template is intended for local use. Review and adapt before enabling it.

Avoid piping native command output directly into `Add-Content`, such as:

```powershell
git status -sb 2>&1 | Add-Content $Log
```

On some Windows PowerShell stream combinations this can fail with:

```text
Add-Content : 資料流是不可讀取的。
```

Use explicit logging helper functions instead:

```powershell
$Repo = "E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager"
$Log = "$Repo\logs\codex_check_tasks.log"
$Npx = "C:\Program Files\nodejs\npx.cmd"
$TaskQueue = "$Repo\docs\ai_coding_agent_task_queue.md"
$Handoff = "$Repo\docs\ai_coding_agent_handoff_status.md"

New-Item -ItemType Directory -Force -Path "$Repo\logs" | Out-Null
Set-Location $Repo

function Write-Log {
    param([string]$Message)
    $Message | Out-File -FilePath $Log -Append -Encoding utf8
}

function Invoke-Logged {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [string]$Label = "command"
    )

    Write-Log "`n--- $Label ---"
    try {
        $output = & $Command 2>&1 | Out-String
        if ([string]::IsNullOrWhiteSpace($output)) {
            Write-Log "(no output)"
        } else {
            Write-Log $output.TrimEnd()
        }
    } catch {
        Write-Log "ERROR: $($_.Exception.Message)"
    }
}

Write-Log "`n===== $(Get-Date -Format s) Codex task check start ====="

# Read-only baseline checks.
Invoke-Logged { git status -sb } "git status -sb"
Invoke-Logged { git log --oneline -5 } "git log --oneline -5"
Invoke-Logged { git rev-parse HEAD } "git rev-parse HEAD"
Invoke-Logged { git rev-parse origin/main } "git rev-parse origin/main"

function Get-PendingQueueTasks {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return @()
    }

    $lines = Get-Content -LiteralPath $Path -Encoding utf8
    $inPendingSection = $false
    $pending = @()

    foreach ($line in $lines) {
        if ($line -match '^##\s+Pending Tasks\s*$') {
            $inPendingSection = $true
            continue
        }
        if ($inPendingSection -and $line -match '^##\s+') {
            break
        }
        if ($inPendingSection -and $line -match '^\s*-\s*\[\s*\]\s+\S+') {
            $pending += $line
        }
    }

    return $pending
}

$PendingTasks = Get-PendingQueueTasks -Path $TaskQueue
if ($PendingTasks.Count -eq 0) {
    Write-Log "NO_PENDING_TASK: docs/ai_coding_agent_task_queue.md has no unchecked task items."
    Write-Log "No files were modified."
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 0
}

$Prompt = @"
You are the scheduled DevPilot Codex runner.

Task source:
- docs/ai_coding_agent_task_queue.md
- docs/ai_coding_agent_handoff_status.md

Rules:
- First inspect current repo status.
- Do not query GitHub Issues directly.
- Do not require gh.
- Do not deploy.
- Do not touch secrets or .env.
- Do not modify production settings.
- Do not run runtime provider live calls.
- Do not modify runtime code unless the task queue contains an explicit pending task requiring it.
- Prefer docs-only updates.
- If no explicit pending task exists, do not modify files; report no pending task in logs and stop.
- If blocked or uncertain, update the handoff status with blocked status and stop only when a pending task exists.
- If files changed, report git status, diff stat, and safety confirmation.
- Do not commit or push unless the task explicitly says commit and push.
"@

Invoke-Logged { $Prompt | & $Npx -y @openai/codex@latest exec --cd $Repo - } "codex exec scheduled task check"

Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
```

## Codex CLI Compatibility Check

The current script uses `npx.cmd` so it does not depend on `codex` being available in PATH:

```powershell
C:\Program Files\nodejs\npx.cmd -y @openai/codex@latest exec --help
```

If `npx.cmd` is unavailable or non-interactive execution fails, do not enable pending-task execution. The no-pending-task path can still log and stop without invoking Codex.

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

## Task Queue Behavior

The runner reads:

```text
docs/ai_coding_agent_task_queue.md
```

Pending tasks are unchecked Markdown tasks under `Pending Tasks`, for example:

```markdown
- [ ] TASK-ID: Short task title
  - Scope: What Codex should do.
  - Allowed files: Paths Codex may modify.
  - Verification: Commands Codex should run.
  - Commit/push: yes/no, with exact rules.
  - Safety: Extra boundaries for this task.
```

When no unchecked task exists:

```text
The runner writes NO_PENDING_TASK to logs and does not modify any file.
```

## Recommended Handoff Status Update

The runner should update `docs/ai_coding_agent_handoff_status.md` only when a pending task exists and the task requires or allows a handoff update.

No-pending-task runs must not update the handoff file.

## Commit and Push Rules

For task-specific updates, use a specific docs or code message only when the task explicitly says commit and push:

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

### `Add-Content` stream is not readable

Symptom:

```text
Add-Content : 資料流是不可讀取的。
```

Cause:

Native command output and redirected error streams can produce objects that do not pipe cleanly into `Add-Content` in Windows PowerShell.

Action:

```text
Use Write-Log / Invoke-Logged helpers that convert output through Out-String before writing to the log file.
```

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
