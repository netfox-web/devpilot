# DevPilot Phase 1–6 Completion Rollup

Date: 2026-05-18
Status: completed implementation rollup, docs-only

## Executive Summary

DevPilot has completed six safety-first implementation phases:

- Local task-queue-driven Codex runner.
- AI Provider Readiness Dashboard.
- Product Domain Launch Plan Dashboard.
- External Project Health Planner.
- External AI Live Verification Gate.
- Domain Execution Dry-run Center.

The common pattern is now established: read-only dashboards and APIs first, dry-run previews before execution, and explicit approvals before any live provider call, deployment, DNS, Cloudflare, Nginx, SSL, registrar, R2, worker, or production mutation.

## Completed Phases

| Phase | Name | Commit | Status | Routes / Files | Safety Boundary |
| --- | --- | --- | --- | --- | --- |
| 1 | Runner Reliability | `7e9d233` | Complete | `docs/ai_coding_agent_task_queue.md`; `scripts/codex_check_tasks.ps1`; `docs/codex_scheduled_task_runner.md` | Local queue only; no GitHub issue polling; no `gh` dependency; no pending task writes log only. |
| 2 | AI Provider Readiness Dashboard | `2428b1f` | Complete | `/admin/ai-provider-readiness`; `/api/admin/ai-provider-readiness` | Read-only; no provider live call; no raw key output; `live_verified=false`; `live_call_enabled=false`. |
| 3 | Product Domain Launch Plan Dashboard | `55e0418` | Complete | `/admin/product-domain-launch-plan`; `/api/admin/product-domain-launch-plan` | `execution_allowed=false`; no DNS, Cloudflare, Nginx, SSL, or deploy. |
| 4 | External Project Health Planner | `a9d3e17` | Complete | `/admin/automation-planner/external-project-health`; `/api/admin/automation-planner/external-project-health` | Read-only; no provider call; no worker execution; no project, task, approval, or handoff mutation. |
| 5 | External AI Live Verification Gate | `439dd2d` | Complete | `/admin/external-ai-live-verification-gate`; `/api/admin/external-ai-live-verification-gate` | `live_verification_allowed=false`; `provider_calls_executed=false`; approval objects not created; usage logs not written; generation results not written. |
| 6 | Domain Execution Dry-run Center | `5c680bf` | Complete | `/admin/domain-execution-dry-run`; `/api/admin/domain-execution-dry-run` | `dry_run=true`; `write_operations_executed=false`; no DNS, Cloudflare, Nginx, SSL, registrar, R2, or deploy. |

## Current Capability Map

### 1. AI Coding Agent Operations

Implemented UI/API/files:

- `docs/ai_coding_agent_task_queue.md`
- `docs/ai_coding_agent_handoff_status.md`
- `docs/codex_scheduled_task_runner.md`
- `scripts/codex_check_tasks.ps1`

Current status:

- The scheduled runner reads a local explicit task queue.
- It does not depend on `gh`.
- It does not query GitHub Issues directly.
- If no pending task exists, it writes logs only and does not modify files.

Still blocked:

- Automatic task queue generation.
- Automatic issue-to-queue ingestion.
- Broad autonomous commit/push policy.

Needs approval:

- Whether the runner may ever auto-commit or auto-push.
- Whether GitHub issues, admin UI notes, or analyst docs should generate queue entries.

### 2. External AI Governance

Implemented UI/API:

- `/admin/ai-provider-readiness`
- `/api/admin/ai-provider-readiness`
- `/admin/external-ai-live-verification-gate`
- `/api/admin/external-ai-live-verification-gate`
- Existing External AI Generate route: `/api/external/ai/generate`

Current status:

- Gemini and Claude readiness are visible without live calls.
- Gemini readiness is mock-verified, live verification disabled.
- Claude readiness is mock-verified, live verification disabled.
- Live verification gate is implemented as a read-only checklist.

Still blocked:

- Live Gemini verification.
- Live Claude verification.
- Approval object creation for live verification.
- Hard budget enforcement review.

Needs approval:

- Provider, model, fixed prompt, budget, token, and request constraints.
- Product, engineering, operations, and security approvals before any live call.

### 3. Product Domain / Domain Operations

Implemented UI/API:

- `/product-domains`
- `/api/product-domains`
- `/api/product-domains/lookup`
- `/api/product-domains/validate`
- `/api/product-domains/redirect-plan`
- `/api/product-domains/redirect-plan/export`
- `/admin/product-domain-launch-plan`
- `/api/admin/product-domain-launch-plan`
- `/admin/domain-execution-dry-run`
- `/api/admin/domain-execution-dry-run`

Current status:

- AI Office catalog is modeled as `Brand -> Suite -> Product -> Module -> Domain`.
- Product Domain Launch Plan Dashboard exposes analyst planning fields.
- Domain Execution Dry-run Center previews DNS, redirect, SSL, and Nginx candidate actions.

Still blocked:

- DNS writes.
- Cloudflare writes.
- Nginx config writes.
- SSL changes.
- Registrar or nameserver changes.
- R2 mutation.
- Deployment.

Needs approval:

- Launch wave order.
- Canonical strategy decisions.
- Redirect status, path preservation, and query preservation.
- DNS hosting target and rollback plan.
- Domain execution approval workflow.

### 4. Automation Planner / External Project Health

Implemented UI/API:

- `/admin/automation-planner/external-project-health`
- `/api/admin/automation-planner/external-project-health`
- Existing external project registry, events, diagnostics, source detail, AI usage, and handoff records.

Current status:

- External Project Health Planner can produce read-only health status, risk score, signals, blockers, warnings, recommended actions, context, and safety checks.

Still blocked:

- Worker execution.
- Automatic remediation.
- Project/task/phase/approval/handoff mutation.
- Provider calls.
- Deploy or infrastructure changes.

Needs approval:

- Which source systems should be prioritized.
- Whether Approval Requests become the universal execution gate.

## Current Safety Model

- Read-only by default.
- Dry-run before execution.
- Explicit approval before live provider, deploy, DNS, or infrastructure mutation.
- No raw provider keys exposed.
- GitHub is the synchronization boundary.
- Codex runner uses a local task queue.
- High-risk actions are planning-only until a separate explicit phase approves execution.

## Verification Snapshot

- Phase 2 tests: `tests/test_ai_manual_handoff.py` passed with 52 tests after the live gate phase.
- Phase 3/6 tests: `tests.test_product_domains` passed with 36 tests after the dry-run phase.
- Phase 4 tests: `tests/test_automation_plans.py` passed with 23 tests and 20 subtests.
- `py_compile app.py` passed in relevant phases.
- `py_compile app.py services/product_domains.py` passed in Product Domain / dry-run phases.
- `git diff --check` passed in relevant phases.

## Open Risks

- Live Gemini / Claude verification is still not approved.
- No production deploy has been executed.
- Domain dry-run does not execute writes.
- Approval object workflow is not implemented for the live gate.
- Budget hard enforcement for the External AI Gateway needs review.
- Task queue auto-generation is not yet implemented.
- Stash remains on the local machine and is not part of the repo.
- Full test suite was not rerun after every phase unless separately stated.

## Recommended Next Phases

### Phase 8 - Approval Object Workflow Design

- Docs-only or read-only UI.
- Connect approval checklist concepts to existing `approval_requests`.
- No execution.

Phase 8 design source:

```text
docs/approval_object_workflow_design.md
```

The design keeps approval objects as a future unifying layer for live provider calls, domain execution, deploy, infrastructure mutation, worker execution, and project/task lifecycle changes. It does not create approvals or execute actions.

### Phase 9 - Task Queue Generator

- Convert ChatGPT, GitHub issue, or admin note inputs into `docs/ai_coding_agent_task_queue.md` pending items.
- No automatic execution yet.

Phase 9 design source:

```text
docs/ai_coding_agent_task_queue_generator_design.md
```

The design keeps queue generation as a reviewable patch/draft process. It does not call Codex, invoke the scheduled runner, commit, push, create approval objects, or execute high-risk actions.

Level 7 scaffold source:

```text
docs/level_7_safe_ai_automation_scaffold.md
```

Level 7 implements preview-only UI/API for task queue generation and approval object previews. Low-risk docs-only requests can generate reviewable task queue patch previews; high-risk requests are classified as `approval_draft_only` or `blocked`. Execution, persistence, provider calls, infrastructure writes, commit, and push remain disabled.

Level 7B draft persistence source:

```text
docs/level_7b_approval_draft_persistence.md
```

Level 7B persists draft approval objects only. It does not approve, reject, execute, create `approval_requests`, call providers, write usage/generation results, or mutate infrastructure or production state.

### Phase 10 - Readiness Rollup Dashboard

- Add one admin page showing provider, domain, automation, and runner readiness.

### Phase 11 - Optional Live Verification Implementation

- Only after approval gate is reviewed and approved.
- One-call Gemini first.
- Claude later.

### Phase 12 - Domain Execution Approval Workflow

- Approval objects plus dry-run plan snapshots.
- Still no direct DNS write until a later explicit execution phase.

## Analyst / Owner Decisions Needed

1. Which products launch first?
2. Should Gemini live verification be approved before Claude?
3. Who can approve live provider calls?
4. Who can approve domain execution?
5. Should the runner ever auto-commit or auto-push from the task queue?
6. Should the task queue be generated from GitHub issues or admin UI?
7. Should Approval Requests become the universal gate for provider, domain, and deploy execution?

## Non-Goals

This rollup does not execute anything.

It does not:

- deploy
- call Gemini or Claude
- mutate DNS, Cloudflare, Nginx, SSL, registrar, nameserver, R2, or production infrastructure
- create approval objects
- touch secrets
- change `.env`
- modify runtime behavior
