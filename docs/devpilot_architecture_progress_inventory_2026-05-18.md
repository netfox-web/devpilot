# DevPilot Architecture and Progress Inventory

Date: 2026-05-18
Audience: analyst, product planning, operations planning
Status: planning inventory, no implementation changes

## Executive Summary

DevPilot is currently an internal AI operations, release-management, safety, domain, and external-integration console.

The system direction is safety-first:

- Use GitHub as the synchronization boundary for Codex, ChatGPT, and AI coding agents.
- Prefer read-only dashboards, reports, exports, dry-runs, and approval gates.
- Do not automatically deploy, change DNS, change SSL, write redirect rules, change registrar nameservers, or mutate infrastructure without a separate explicit phase.
- Keep provider keys inside DevPilot-controlled runtime or a future provider key vault.
- External systems receive DevPilot-issued external API keys only, never raw OpenAI, Gemini, Claude, DNS, Cloudflare, SSH, Docker, or infrastructure credentials.

Current local repository note:

```text
Phase 1-6 implementation work has been completed and pushed to main.
The current architecture posture is read-only first, dry-run before execution, and explicit approval before live provider or infrastructure mutation.
```

Phase 1-6 completion rollup:

```text
Phase 1 Runner Reliability: 7e9d233
Phase 2 AI Provider Readiness Dashboard: 2428b1f
Phase 3 Product Domain Launch Plan Dashboard: 55e0418
Phase 4 External Project Health Planner: a9d3e17
Phase 5 External AI Live Verification Gate: 439dd2d
Phase 6 Domain Execution Dry-run Center: 5c680bf
```

Latest capability map:

- AI Coding Agent Operations: local task-queue-driven runner, no GitHub issue polling, no `gh` dependency.
- External AI Governance: provider readiness dashboard plus live verification gate, with live calls still disabled.
- Product Domain / Domain Operations: catalog, launch plan, redirect plan, canonical strategy, and domain execution dry-run center.
- Automation Planner / External Project Health: read-only project health planner with risk, blockers, warnings, recommended actions, and safety checks.

Route summary added through Phase 6:

```text
/admin/ai-provider-readiness
/api/admin/ai-provider-readiness
/admin/product-domain-launch-plan
/api/admin/product-domain-launch-plan
/admin/automation-planner/external-project-health
/api/admin/automation-planner/external-project-health
/admin/external-ai-live-verification-gate
/api/admin/external-ai-live-verification-gate
/admin/domain-execution-dry-run
/api/admin/domain-execution-dry-run
```

Recommended next phases:

- Phase 8: Approval Object Workflow Design.
- Phase 9: Task Queue Generator.
- Phase 10: Readiness Rollup Dashboard.
- Phase 11: Optional Live Verification Implementation after approval.
- Phase 12: Domain Execution Approval Workflow.

## 1. Core Admin Console

DevPilot has a broad admin console for operations and safety review.

Implemented surfaces include:

- Operations command center: `/`
- Release dashboard: `/release-dashboard`
- Production release note: `/production-release-note`
- Release archive: `/production-release-archive`
- Manual operations checklist: `/manual-operations-checklist`
- Operations runbook: `/operations-runbook`
- Approval requests: `/approval-requests`
- API key center: `/api-keys`
- AI costs: `/ai-costs`

Primary purpose:

- Provide operational visibility.
- Keep high-risk actions visible but separated from execution.
- Support audit, release review, safety review, and manual approval workflows.

Current posture:

- Read-only first.
- Dry-run before write.
- Explicit approval before production-impacting actions.

## 2. Product Domain Architecture

The AI Office product-domain architecture is fixed as:

```text
Brand -> Suite -> Product -> Module -> Domain
```

Current brand model:

```text
Brand: AI Office
Brand key: ai_office
Brand hub official domain: aioffice.com.tw
Brand hub redirect domain: aioffice.tw
```

Current catalog summary:

```text
Suites: 7
Products: 26
Domains: 60
Validation: ok
```

Domain role counts:

```text
official: 27
redirect: 32
campaign: 1
```

Important domain rules:

- `aioffice.com.tw` is the Brand Hub official domain.
- `aioffice.tw` redirects to the Brand Hub.
- Each Product has exactly one official domain.
- Redirect domains must define `target_domain`.
- Owned domains are not automatically treated as independent websites.

Implemented routes:

```text
/product-domains
/api/product-domains
/api/product-domains/lookup
/api/product-domains/validate
/api/product-domains/redirect-plan
/api/product-domains/redirect-plan/export
```

Current status:

- Catalog model exists.
- Admin UI and read APIs exist.
- Redirect plan exports exist.
- Product Domain Launch Plan Dashboard is implemented as a read-only UI/API.
- Domain Execution Dry-run Center is implemented as a read-only UI/API.
- No DNS, Cloudflare, Nginx, registrar, or SSL changes are performed by this catalog.

Analyst questions:

- Should all 26 products receive standalone landing pages?
- Which products should launch first?
- Which redirect domains should stay redirects versus become campaigns or reserved domains?
- What is the SEO/canonical strategy across `.tw`, `.com.tw`, `.net.tw`, and `.fun`?

## 3. Domain, DNS, Cloudflare, and Redirect Safety

Implemented admin surfaces:

```text
/cloudflare
/domains
/domain-readiness
/domain-action-plan
/admin/domain-execution-dry-run
/api/admin/domain-execution-dry-run
/api/cloudflare/dns-write-flag
/api/cloudflare/zones
/api/cloudflare/zones/<zone_id>/dns-records
```

Implemented capabilities:

- Cloudflare settings visibility.
- Read-only zone and DNS overview.
- Domain readiness checks.
- Domain action plan board.
- Product-domain redirect plan export.
- DNS approval/preflight/dry-run structures.
- Domain Execution Dry-run Center for read-only DNS, redirect, SSL, Nginx, and Cloudflare action previews.

Current safety boundary:

- No DNS record writes.
- No SSL mode writes.
- No redirect rule writes.
- No Nginx config writes.
- No registrar nameserver changes.
- No R2 mutations.
- No deploys.

Current dry-run status:

- Product Domain catalog, launch plan, redirect plan, and canonical strategy can be combined into preview actions.
- Preview actions require approval and keep `execution_allowed=false`.
- The dry-run center does not call Cloudflare, write DNS records, generate Nginx files, change SSL, mutate registrar/nameservers, deploy, call providers, run workers, or modify production settings.
- Implementation status: implemented as read-only UI/API in Phase 6; execution remains disabled.

Pending planning decisions:

- Official product hosting target.
- Standard `www` behavior.
- Whether each product needs `app` and `api` subdomains.
- Cloudflare Redirect Rules versus Bulk Redirects versus Nginx redirects.
- Cloudflare SSL mode and origin certificate strategy.

## 4. External Project Registry and Communication

DevPilot supports metadata registration for external AI-related projects.

Implemented external project APIs:

```text
POST /api/external/projects/register
GET /api/external/projects
GET /api/external/projects/<external_project_id>
POST /api/external/projects/<external_project_id>/events
GET /api/external/projects/<external_project_id>/events
```

Registry purpose:

- Track external project identity.
- Store repo/runtime/container/domain metadata.
- Record lifecycle events such as deploy, healthcheck, AI jobs, and domain requests.
- Provide a central status hub without sharing secrets.

Safety boundaries:

- No DNS writes.
- No Cloudflare writes.
- No deploy or restart.
- No provider calls.
- No worker execution.
- No approval creation.
- No unrelated project/task mutation.

Future communication roadmap:

- Project relationships.
- Project-to-project messages.
- Event subscriptions.
- Shared context lookup.
- Cross-project handoff workflow.
- Communication audit timeline.

These future APIs should remain metadata-first and policy-gated.

## 5. External AI Gateway

Strategic direction:

```text
External System
  -> DevPilot External API Key
  -> DevPilot External AI Gateway
  -> Source policy / budget / audit
  -> Approved AI provider
```

Implemented layers:

- External API key manager.
- External AI policy manager.
- External AI permission profiles.
- External AI usage dashboard/API.
- Provider config inspection.
- Provider secrets admin page.
- External AI Generate API.

Current generate endpoint:

```text
POST /api/external/ai/generate
```

Current provider support:

```text
Gemini default provider: gemini-1.5-flash
Claude mocked/tested path: claude-3-5-haiku
```

Implemented read-only governance surfaces:

```text
/admin/ai-provider-readiness
/api/admin/ai-provider-readiness
/admin/external-ai-live-verification-gate
/api/admin/external-ai-live-verification-gate
```

Supported text capabilities:

- `generate`
- `summary`
- `rewrite`
- `classification`
- `extraction`
- `planning`
- `chat`

Important current boundary:

- Claude support is not live-provider-enabled in this phase.
- The Claude gateway function is mock/test oriented unless a later phase explicitly enables live calls.
- Gemini and Claude live verification gates are implemented, but `live_verification_allowed=false`.
- Usage logging stores hashes and short summaries by default, not full prompt/response.
- Idempotent replay avoids duplicate provider calls for completed results.

Recent relevant commit:

```text
decf031 feat: add Claude mock external AI generate path
```

Next planning decisions:

- Whether to enable a live Gemini verification phase.
- Whether to enable a live Claude verification phase.
- Which external `source_system` gets first production AI Gateway access.
- Budget, token, and request limits by source.
- Whether full prompt/response storage is ever allowed.

## 6. AI Console and Sandbox

Implemented surfaces:

```text
/ai-console
/ai-console/sandbox
/ai-console/sandbox/<artifact_id>
/api/ai-console/sandbox
/api/ai-console/sandbox/<artifact_id>/download
/api/ai-console/sandbox/cleanup-plan
```

Capabilities:

- AI prompt execution/review workflows.
- Claude executor preview.
- Gemini reviewer.
- Sandbox HTML artifact generation.
- Sandbox gallery, preview, download.
- Cleanup plan dry-run.

Safety boundaries:

- Sandbox artifacts write only to runtime sandbox storage.
- No project repo write by default.
- No deploy.
- No DNS.
- No apply-to-project button.
- Cleanup is dry-run only.

Future phase:

- Sandbox artifact apply-plan generator.
- Artifact validation.
- Diff preview.
- Approval-gated apply-to-staging.
- Deploy remains a separate phase.

## 7. Automation Planner

The Automation Planner is a planning-only system for safe project automation.

Implemented/planned inputs:

- External Project Registry.
- External Project Events.
- External Integration Diagnostics.
- External Source Detail.
- External AI Usage.
- Handoff records.
- Product/domain catalog.
- Manual admin notes.

Expected outputs:

- Draft automation plan.
- Risk level.
- Recommended actions.
- Required approvals.
- Blockers.
- Safety checks.
- Display-only suggested commands.

Current non-goals:

- No deploy.
- No restart.
- No migrations.
- No DNS, SSL, Nginx, Cloudflare, R2, or infrastructure changes.
- No provider calls unless a later policy-gated phase allows it.
- No worker execution.
- No automatic remediation.

Implementation status:

- External Project Health Planner is implemented as read-only UI/API in Phase 4.
- It reports health, risk score, signals, blockers, warnings, recommended actions, context, and safety checks.
- Execution remains disabled.

Analyst decision:

- Which category should Automation Planner serve first:
  - AI SaaS project health.
  - Domain operations.
  - Deploy readiness.
  - AI usage governance.
  - External project onboarding.

## 8. GitHub, Codex, and Scheduled Runner

GitHub is the current synchronization boundary for local Codex and external review.

Implemented runner file:

```text
scripts/codex_check_tasks.ps1
```

Recent commit:

```text
7e9d233 chore: make Codex runner task-queue driven
```

Runner design:

- Windows Task Scheduler invokes PowerShell.
- Runner logs to `logs/codex_check_tasks.log`.
- Uses `Write-Log` and `Invoke-Logged`.
- Uses `C:\Program Files\nodejs\npx.cmd`.
- Calls `npx -y @openai/codex@latest exec`.
- `.local_backups/` and `logs/` are ignored by Git.
- Reads `docs/ai_coding_agent_task_queue.md` as the local scheduled-runner task source.
- Does not query GitHub Issues directly.
- Does not require `gh`.
- If no pending task exists, logs only and does not modify files.

Current issue:

- Task queue auto-generation is not implemented yet.
- Whether the runner may ever auto-commit or auto-push remains an owner policy decision.

Planning options:

- Generate task queue entries from GitHub issues, admin UI notes, or analyst docs.
- Keep automatic execution disabled until explicit owner policy is approved.
- Route runner decisions through a future readiness rollup dashboard.

## 9. Testing and Verification Coverage

Relevant test files:

```text
tests/test_ai_manual_handoff.py
tests/test_product_domains.py
tests/test_github_admin_status.py
tests/test_automation_plans.py
tests/test_ai_messages_thread_board.py
tests/test_domain_pages_performance.py
```

Recent notable results recorded in docs/history:

```text
External AI / handoff focused tests: 47 passed
Managed GitHub status tests: 6 passed
Historical full pytest record: 114 passed, 28 subtests passed
```

Current inventory did not rerun the full suite.

## 10. Current Risks and Open Items

Immediate local housekeeping:

- Decide whether to keep, commit, or restore the local scheduled-run change in `docs/ai_coding_agent_handoff_status.md`.

Architecture risks:

- Scheduled runner GitHub issue access is not reliable yet.
- Claude External AI Generate is mock/test only, not live-enabled.
- Product Domain catalog is ready for analysis, but DNS/SSL/redirect execution is intentionally not implemented.
- AI Console sandbox apply-to-project is not implemented.
- Cross-project communication APIs are still roadmap/planning.
- External AI Gateway budget enforcement is still early; warnings and logging exist, but hard enforcement should be reviewed before production use.

## 11. Recommended Planning Roadmap

### Phase A: Analyst Review

Review:

- AI Office suite/product/domain hierarchy.
- Product launch priority.
- Redirect/campaign/reserved/infra classifications.
- Brand Hub IA.
- SEO canonical policy.

### Phase B: Runner Reliability

Decide:

- `gh` CLI versus managed GitHub API.
- Whether scheduled task should be issue-aware or handoff-only.
- Whether runner should create branches/PRs or only update handoff.

### Phase C: External AI Gateway Governance

Decide:

- First production `source_system`.
- Provider/model permissions.
- Budget limits.
- Token/request limits.
- Whether live Gemini/Claude verification is allowed.

### Phase D: Domain Execution Dry-Runs

Prepare:

- DNS dry-run.
- Redirect dry-run.
- SSL plan.
- Nginx plan.

No writes until separately approved.

### Phase E: Automation Planner MVP

Choose first use case:

- External project health diagnosis.
- Domain readiness planning.
- Deploy readiness planning.
- AI usage governance.

Keep it planning-only.

## 12. Analyst Questions

1. Which products are first-wave launch candidates?
2. Should every official product domain get a standalone landing page?
3. Which redirect domains should be reclassified as campaign or reserved?
4. What is the canonical domain strategy for `.tw`, `.com.tw`, `.net.tw`, and `.fun`?
5. Should `www` redirect be universal?
6. Which source systems should use External AI Gateway first?
7. Should Claude remain mocked until Gemini live verification is complete?
8. Should scheduled Codex runner read GitHub issues directly, or only read the handoff file?
9. Which operations require approval object creation versus documentation-only review?
10. What is the minimum safe production launch set?
