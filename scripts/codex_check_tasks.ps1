$Repo = "E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager"
$Log = "$Repo\logs\codex_check_tasks.log"
$Npx = "C:\Program Files\nodejs\npx.cmd"

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

if (-not (Test-Path -LiteralPath $Npx)) {
    Write-Log "ERROR: npx.cmd not found at $Npx"
    Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
    exit 1
}

Invoke-Logged { git status -sb } "git status -sb"
Invoke-Logged { git branch --show-current } "git branch --show-current"
Invoke-Logged { git log --oneline -5 } "git log --oneline -5"
Invoke-Logged { git rev-parse HEAD } "git rev-parse HEAD"
Invoke-Logged { git rev-parse origin/main } "git rev-parse origin/main"

$Prompt = @"
You are the scheduled DevPilot Codex runner.

Task source:
- GitHub issue with label codex-task
- docs/ai_coding_agent_handoff_status.md

Rules:
- First inspect current repo status.
- If not on main, stop and report blocked.
- If main is not aligned with origin/main, stop and report blocked.
- Do not deploy.
- Do not touch secrets or .env.
- Do not modify production settings.
- Prefer docs-only updates.
- Do not modify runtime code unless a GitHub issue labeled codex-task explicitly requests it.
- If no explicit pending task exists, update docs/ai_coding_agent_handoff_status.md with a no-pending-task summary only.
- If blocked or uncertain, update the handoff status with blocked status and stop.
- If files changed, report git status, diff stat, and safety confirmation.
- Do not commit or push unless the task explicitly says commit and push.
"@

Invoke-Logged { $Prompt | & $Npx -y @openai/codex@latest exec --cd $Repo - } "codex exec scheduled task check"

Write-Log "===== $(Get-Date -Format s) Codex task check end ====="
