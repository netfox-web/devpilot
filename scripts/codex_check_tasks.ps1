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

Write-Log "`n===== $(Get-Date -Format s) Codex task check start ====="

Invoke-Logged { git status -sb } "git status -sb"
Invoke-Logged { git branch --show-current } "git branch --show-current"
Invoke-Logged { git log --oneline -5 } "git log --oneline -5"
Invoke-Logged { git rev-parse HEAD } "git rev-parse HEAD"
Invoke-Logged { git rev-parse origin/main } "git rev-parse origin/main"

$CurrentBranch = (git branch --show-current 2>$null | Out-String).Trim()
if ($CurrentBranch -ne "main") {
    Write-Log "BLOCKED: scheduled runner only executes from main; current branch is '$CurrentBranch'."
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 0
}

$Head = (git rev-parse HEAD 2>$null | Out-String).Trim()
$OriginMain = (git rev-parse origin/main 2>$null | Out-String).Trim()
if (-not $Head -or -not $OriginMain -or $Head -ne $OriginMain) {
    Write-Log "BLOCKED: local main is not aligned with origin/main."
    Write-Log "HEAD: $Head"
    Write-Log "origin/main: $OriginMain"
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 0
}

if (-not (Test-Path -LiteralPath $TaskQueue)) {
    Write-Log "BLOCKED: task queue file not found at $TaskQueue"
    Write-Log "No files were modified."
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 0
}

$PendingTasks = Get-PendingQueueTasks -Path $TaskQueue
if ($PendingTasks.Count -eq 0) {
    Write-Log "NO_PENDING_TASK: docs/ai_coding_agent_task_queue.md has no unchecked task items."
    Write-Log "No files were modified."
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 0
}

Write-Log "PENDING_TASK_COUNT: $($PendingTasks.Count)"
foreach ($Task in $PendingTasks) {
    Write-Log "PENDING_TASK: $Task"
}

if (-not (Test-Path -LiteralPath $Npx)) {
    Write-Log "ERROR: npx.cmd not found at $Npx"
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 1
}

$Prompt = @"
You are the scheduled DevPilot Codex runner.

Task source:
- docs/ai_coding_agent_task_queue.md
- docs/ai_coding_agent_handoff_status.md

Rules:
- First inspect current repo status.
- If not on main, stop and report blocked.
- If main is not aligned with origin/main, stop and report blocked.
- Do not query GitHub Issues directly.
- Do not require gh.
- Do not deploy.
- Do not touch secrets or .env.
- Do not modify production settings.
- Do not run runtime provider live calls.
- Prefer docs-only updates.
- Do not modify runtime code unless a pending task in docs/ai_coding_agent_task_queue.md explicitly requests it.
- If no explicit pending task exists, do not modify files; report no pending task in logs and stop.
- If blocked or uncertain, update the handoff status with blocked status and stop only when a pending task exists.
- If files changed, report git status, diff stat, and safety confirmation.
- Do not commit or push unless the task explicitly says commit and push.
"@

Invoke-Logged { $Prompt | & $Npx -y @openai/codex@latest exec --cd $Repo - } "codex exec scheduled task check"

Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
