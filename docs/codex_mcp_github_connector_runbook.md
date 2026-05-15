# Codex MCP GitHub Connector Runbook

This runbook records the verified workflow for using Codex CLI, MCP tools, and the ChatGPT GitHub connector together in DevPilot without manually copying every command between chat windows.

Final status:

```text
CODEX_MCP_GITHUB_CONNECTOR_RUNBOOK_READY
```

## Objective

Define the safe operating model for DevPilot AI-assisted development:

- Local Codex CLI handles local repository work when a local shell is required.
- Codex MCP tools provide local-agent document/tool access such as Context7.
- ChatGPT GitHub connector handles remote repository inspection, branch creation, file updates, comments, and pull requests.
- GitHub remains the synchronization boundary between local Codex and ChatGPT when direct local shell access is not available.

## Verified Environment

Local Codex CLI was verified with:

```text
OpenAI Codex v0.130.0
model: gpt-5.5
repository: E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager
remote: https://github.com/netfox-web/devpilot.git
```

The repository remote was confirmed as:

```text
origin  https://github.com/netfox-web/devpilot.git (fetch)
origin  https://github.com/netfox-web/devpilot.git (push)
```

A push attempt initially failed when GitHub network access was blocked, then succeeded after explicit approval:

```text
Everything up-to-date
```

The clean synchronized state was confirmed as:

```text
## main...origin/main
```

## MCP Verification

Codex MCP was verified inside the Codex TUI with:

```text
/mcp
```

Available MCP servers included:

```text
context7
  Command: npx -y @upstash/context7-mcp
  Tools: query-docs, resolve-library-id
```

This means Codex can use Context7 for documentation lookup from the local Codex environment.

## Important Boundary

ChatGPT cannot directly type into or control the local Codex TUI unless a dedicated bridge is built.

Current direct control boundary:

```text
ChatGPT
  -> GitHub connector
  -> netfox-web/devpilot repository
```

Current local Codex boundary:

```text
Local PowerShell / Codex TUI
  -> local repository
  -> local MCP tools such as Context7
```

Practical synchronization model:

```text
Local Codex commits/pushes to GitHub
ChatGPT reads/writes GitHub branches and PRs
Local machine pulls GitHub changes when needed
```

## No-Paste Operating Model

Use this mode when the user wants to avoid pasting commands and outputs between ChatGPT and Codex.

1. Keep all durable project changes synchronized through GitHub.
2. ChatGPT uses the GitHub connector to inspect repository files, commits, diffs, branches, and pull requests.
3. ChatGPT creates a branch for changes instead of directly mutating `main`.
4. ChatGPT commits documentation or code changes to that branch.
5. ChatGPT opens a pull request for review.
6. The user can review, merge, or pull the branch locally.

This avoids manual command transfer for GitHub-hosted work while preserving reviewability.

## Recommended ChatGPT GitHub Workflow

For documentation-only tasks:

```text
1. Inspect existing files or recent commits.
2. Create a topic branch.
3. Add or update documentation only.
4. Open a PR.
5. Do not deploy.
6. Do not touch secrets.
7. Do not modify runtime code unless explicitly requested.
```

For code tasks:

```text
1. Inspect the issue or requested change.
2. Create a topic branch.
3. Make the smallest safe code change.
4. Update or add focused tests when feasible.
5. Open a PR with verification notes.
6. Leave production deployment to a separate explicit approval step.
```

## Recommended Local Codex Workflow

Use local Codex when work needs local shell execution, local tests, or access to local-only files.

Start Codex from the repository root:

```powershell
cd E:\Ai-project\devpilot_project_manager_v1\devpilot_project_manager
codex
```

Check MCP tools inside Codex:

```text
/mcp
```

Safe local prompt pattern:

```text
Check the current repository status.
Do not modify files, commit, push, deploy, or delete anything.
Report:
1. git status -sb
2. git log --oneline -5
3. recommended next step
```

Safe modification prompt pattern:

```text
Modify only the requested file.
Do not commit.
Do not push.
Do not deploy.
After changes, report git status and the diff.
```

## Safe Git Rules

Default rules for AI-assisted work:

- Prefer topic branches for ChatGPT connector changes.
- Do not push directly to `main` unless the task is explicitly a confirmed direct-main sync.
- Do not create commits if the staged diff contains unexpected files.
- Do not modify `.env`, secrets, provider tokens, encrypted values, or key hashes.
- Do not deploy, restart services, run migrations, or mutate production infrastructure without explicit approval.
- Do not run broad destructive commands.
- Prefer documentation-only commits for process/runbook updates.

## Verified Documentation Commit

The managed GitHub API status-check verification document was added in:

```text
fce5765 docs: add managed GitHub API status check verification
```

That document records:

- Managed GitHub API key resolver behavior.
- Safe status endpoint behavior.
- Failure modes.
- Response shape.
- Security exclusions for raw token, Authorization, Bearer token, encrypted value, and key hash.
- Test coverage.
- Non-goals and safety confirmation.

## Failure Modes and Responses

### Codex config TOML nesting issue

Symptom:

```text
Error loading config.toml: invalid type: string "on-request", expected u32
in `tui.model_availability_nux`
```

Cause:

```text
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```

was placed under `[tui.model_availability_nux]` instead of at the top level.

Fix:

Place top-level Codex settings before any `[table]` section:

```toml
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[tui.model_availability_nux]
"gpt-5.5" = 1
```

### `/mcp` not recognized in PowerShell

Symptom:

```text
/mcp : 無法辨識 '/mcp' 詞彙是否為 Cmdlet...
```

Cause:

`/mcp` is a Codex TUI command, not a PowerShell command.

Fix:

Run:

```powershell
codex
```

Then type inside the Codex TUI:

```text
/mcp
```

### Untracked file has no normal git diff

Symptom:

```powershell
git diff -- docs/example.md
```

returns no output for an untracked file.

Fix:

Use:

```powershell
git diff --no-index -- /dev/null docs/example.md
```

or stage it first and inspect:

```powershell
git add docs/example.md
git diff --cached -- docs/example.md
```

### GitHub network blocked in Codex

Symptom:

```text
fatal: unable to access 'https://github.com/...': Could not connect to server
```

Fix:

Approve the network action when Codex asks for permission, then retry the Git command.

## Non-Goals

This runbook does not establish:

- Direct ChatGPT control of the user's local Codex TUI.
- A public codex-control API.
- A local shell bridge exposed to ChatGPT.
- Automatic deployment.
- Automatic production mutation.
- Secret access or token exfiltration.
- Bypassing GitHub review.

## Future Bridge Option

If direct ChatGPT-to-local-Codex control is required later, build a narrow `codex-control` bridge with explicit allowlists.

Minimum safe bridge capabilities:

```text
codex_plan(task, repo)
codex_run(task, repo, mode)
git_status(repo)
git_diff(repo)
run_tests(repo, command)
```

Avoid exposing generic shell execution, unrestricted filesystem writes, automatic push, or deployment actions.

## Safety Confirmation

This runbook is documentation-only. It records the verified Codex, MCP, and GitHub connector operating model and does not introduce app behavior, deployment, restart, rebuild, migration, infrastructure change, DNS/SSL/Nginx/Cloudflare/R2 change, provider call, worker/task execution, project/task/phase/approval mutation, or secret output.
