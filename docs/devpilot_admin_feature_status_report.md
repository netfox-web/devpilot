# DevPilot Admin Feature Status Report

Generated: 2026-05-11

This report summarizes the DevPilot admin backend and operations UI as currently built across the recent phases. It is intended for analyst, product, and operations review. It separates completed read-only/admin capabilities from pending execution-capability work.

## 1. Executive Summary

DevPilot has evolved into an internal AI operations and release-management console. The current direction is safety-first:

- Prefer read-only dashboards and export/report pages.
- Keep high-risk operations behind manual approval and separate phases.
- Avoid automatic DNS, deployment, SSL, Telegram, or registrar changes unless explicitly approved.
- Use DevPilot as the control and audit surface before building automation.

The admin system currently includes:

- Operations Command Center
- Release and backup dashboards
- Approval Requests
- API Key Center
- Cloudflare read-only and token management surfaces
- Domain Center and product-domain catalog
- Domain Readiness and Action Plan
- Manual Operations Checklist
- Operations Runbook
- Production Release Note / Archive
- AI Console with Claude executor and Gemini reviewer
- Sandbox artifact generation, gallery, metadata, and cleanup dry-run
- AI Center Fleet read-only integration page
- Bilingual UI foundation and translation coverage work

Several capabilities remain intentionally not enabled:

- No automatic production deploy from safety dashboards.
- No automatic Cloudflare DNS write from product-domain reports.
- No automatic SSL mode write from the product-domain catalog.
- No automatic redirect rule write.
- No automatic registrar nameserver update.
- No automatic apply-to-project from sandbox artifact.

## 2. Core Admin Navigation

The admin UI is grouped into:

### Core

- Home
- Projects
- New Project
- AI Console
- AI Heartbeats
- AI Costs
- API Keys

### Safety

- Approval Requests
- Cloudflare
- Domains
- Product Domains
- Domain Readiness
- Domain Action Plan

### Operations

- Release Dashboard
- Release Note / QA Report
- AI Center Fleet
- Manual Checklist
- Runbooks
- Deployment Targets
- Deployment Board
- NAS Docker Scan

## 3. Completed Admin Functions

### 3.1 Operations Command Center

Route:

```text
/
```

Purpose:

- High-level admin landing page.
- Shows production status, release label, safety badges, backend status, approval status, and operational overview.

Status:

```text
Completed / production deployed in earlier phases
```

Notes:

- Read-only status-oriented dashboard.
- Includes safety labels such as read-only / no deploy / DNS write disabled.

### 3.2 Release Dashboard

Route:

```text
/release-dashboard
```

Purpose:

- Release and backup visibility.
- Production identity.
- DB count snapshot.
- Backup inventory.
- Approval and DNS audit context.

Status:

```text
Completed
```

Not included:

- No restore button.
- No automatic rollback.
- No production deployment trigger from this dashboard.

### 3.3 Production Release Note / Admin QA Report

Routes:

```text
/production-release-note
/api/production-release-note/export.md
```

Purpose:

- Summarize production release state.
- Document completed phases.
- Show safety chain status.
- Provide markdown export.

Status:

```text
Completed
```

### 3.4 Release Archive

Routes:

```text
/production-release-archive
/api/release/archive-index.json
/api/release/qa-summary.md
/api/release/version
```

Purpose:

- Provide read-only archive index.
- Provide release version JSON.
- Provide QA summary markdown.
- Mark release label:

```text
DevPilot Admin Safety Release 2026-05-09
```

Status:

```text
Completed
```

### 3.5 Local Git Tag

Tag:

```text
devpilot-admin-safety-2026-05-09
```

Target:

```text
1f8bc01
```

Status:

```text
Created local annotated tag, no push
```

Notes:

- Production app still shows `git_tag_created=false`, which is expected because the app was not updated after local tag creation.

### 3.6 Approval Requests

Route:

```text
/approval-requests
```

Purpose:

- Review approval requests.
- Support approval-related safety workflows.
- Mock notification controls exist for controlled testing.

Status:

```text
Completed / legacy controls labeled
```

Important:

- Real DNS/deploy approval must be separately authorized.
- Telegram send is not part of normal read-only review phases.

### 3.7 API Key Center

Routes:

```text
/api-keys
```

Purpose:

- Store API keys encrypted in DB.
- Show masked metadata only.
- Support provider metadata and AI provider configuration.

Status:

```text
Completed
```

Known current use:

- Cloudflare API Token is stored in API Key Center and used by the NAS bridge process in memory only.
- OpenAI, Gemini, and Claude/Anthropic providers have been configured.

Security:

- Full API key values must not be printed or exported.
- Encrypted values must not be exposed.

### 3.8 Cloudflare Settings

Route:

```text
/cloudflare
```

Purpose:

- Cloudflare credential management.
- Read-only DNS write flag/status visibility.
- Legacy token save/test controls are labeled as sensitive.

Status:

```text
Completed / warning labels added
```

Current safety stance:

- DNS write remains disabled unless a separate phase explicitly authorizes it.
- Product-domain redirect exports do not call Cloudflare.

### 3.9 Domain Center

Route:

```text
/domains
```

Purpose:

- Read-only Cloudflare zone and DNS overview.
- Preview domain plan for project mapping.
- Legacy/manual binding controls exist.

Status:

```text
Completed / legacy controls labeled
```

Important:

- Does not perform Cloudflare DNS writes.
- Binding to internal project mapping is not the same as creating DNS records.

### 3.10 Product Domain Management

Routes:

```text
/product-domains
/api/product-domains
/api/product-domains/lookup?domain=...
/api/product-domains/validate
```

Purpose:

- Model AI Office product-domain architecture:

```text
Brand -> Suite -> Product -> Module -> Domain
```

Status:

```text
Implemented in repo working tree
```

Current model:

- Brand: AI Office
- Brand Hub: `aioffice.com.tw`
- Suites: 7
- Products: 26
- Domains: 60

UI supports:

- Search by domain / product / suite.
- Role filter.
- Suite/product filters.
- Summary cards.
- Validation status.

### 3.11 Redirect Plan

Routes:

```text
/api/product-domains/redirect-plan
/api/product-domains/redirect-plan/export?format=json
/api/product-domains/redirect-plan/export?format=csv
/api/product-domains/redirect-plan/export?format=nginx
/api/product-domains/redirect-plan/export?format=cloudflare-bulk
```

Purpose:

- Generate read-only redirect plan from the product-domain catalog.
- Provide analyst-friendly exports.
- Provide Nginx and Cloudflare bulk templates without applying them.

Status:

```text
Implemented in repo working tree
```

Safety:

- Does not connect to Cloudflare.
- Does not write redirect rules.
- Does not write Nginx config.

### 3.12 Domain Readiness

Route:

```text
/domain-readiness
```

Purpose:

- Readiness dashboard for selected domains.
- Checks DNS/HTTP/HTTPS/TLS/backend context.

Status:

```text
Completed
```

Safety:

- Read-only.
- No DNS/NAS changes from this page.

### 3.13 Domain Action Plan

Routes:

```text
/domain-action-plan
/api/domain-action-plan/export.csv
```

Purpose:

- Read-only action plan board.
- Groups domain work into readiness lanes.
- CSV export.

Status:

```text
Completed
```

### 3.14 Manual Operations Checklist Center

Routes:

```text
/manual-operations-checklist
/api/manual-operations-checklist/export.csv
```

Purpose:

- Static read-only checklist for high-risk manual operations:
  - DNS real write
  - NAS reverse proxy
  - SSL certificate
  - Release deploy
  - Rollback readiness
  - Secret safety

Status:

```text
Completed
```

### 3.15 Operations Runbook Center

Routes:

```text
/operations-runbook
/api/operations-runbook/export.csv
```

Purpose:

- Static read-only runbooks:
  - DNS write
  - NAS SSL / Reverse Proxy
  - Release deploy
  - Emergency rollback
  - Secret leak response
  - Telegram approval test

Status:

```text
Completed
```

### 3.16 AI Console

Route:

```text
/ai-console
```

Purpose:

- AI prompt execution and review workflows.
- Claude/Anthropic executor.
- Gemini reviewer.
- Preview-only output.

Status:

```text
Completed
```

Current provider status from recent work:

- OpenAI configured.
- Gemini configured.
- Claude/Anthropic configured.

Safety:

- No project repo write by default.
- No deploy.
- No DNS.
- No secret output.

### 3.17 AI Console Sandbox Artifacts

Routes:

```text
/ai-console/sandbox
/ai-console/sandbox/<artifact_id>
/api/ai-console/sandbox
/api/ai-console/sandbox/<artifact_id>/download
/api/ai-console/sandbox/cleanup-plan
```

Purpose:

- Save Claude-generated HTML into sandbox-only artifact files.
- Preview/download sandbox artifacts.
- Gallery of recent artifacts.
- Metadata and retention policy.
- Cleanup planning dry-run.

Status:

```text
Completed
```

Safety:

- Writes only to sandbox runtime directory.
- Does not write project repo.
- Does not deploy.
- Cleanup is dry-run only.
- No delete button.
- No apply-to-project button.

### 3.18 AI Console Apply-to-Project Design Review

Status:

```text
Design reviewed only
```

Future safe apply design:

1. Select sandbox artifact.
2. Validate artifact.
3. Generate apply plan.
4. Preview diff.
5. Require approval.
6. Apply only to staging workspace after approval.
7. Deploy remains a separate phase.

Not implemented:

- No apply button.
- No project repo write.
- No approval submission for apply.

### 3.19 AI Center Fleet Read-only Integration

Route:

```text
/ai-center/fleet
```

Purpose:

- Read-only entry for external AI Fleet Console.
- Recommended protected domain:

```text
fleet.aicenter.com.tw
```

Status:

```text
Completed as read-only integration/status page
```

Pending:

- Cloudflare Access protection.
- Reverse proxy review.
- WebSocket upgrade verification.
- API no-longer-public verification.

Not done:

- No Fleet DB merge.
- No Fleet app modification.
- No DNS write.

### 3.20 Bilingual Admin UI

Status:

```text
Foundation and coverage patches completed
```

Implemented:

- zh-Hant / English language switcher.
- Base nav bilingual foundation.
- Login bilingual.
- Translation dictionary expansion.
- Legacy page translation coverage improvements.
- Translation safety exclusions for:
  - `code`
  - `pre`
  - `textarea`
  - `script`
  - `style`
  - `kbd`
  - `samp`

Pending:

- Further deep translation coverage for newly added pages, including the Product Domain pages if needed.

## 4. Cloudflare / Domains Current Status

### 4.1 Batch Tooling

Implemented local/NAS tooling:

```text
cf_batch.py
cf_batch_devpilot_bridge.py
domains.csv
cloudflare-result.csv
nameserver-update-list.csv
nameserver-update-result.csv
```

Bridge design:

- Reads Cloudflare token from DevPilot API Key Center.
- Token exists only in process memory.
- No token written to `.env`, CSV, README, logs, or reports.

### 4.2 Zone and Nameserver Status

Current priority set:

```text
60 domains
```

Verified:

```text
Cloudflare zone exists: 60
Cloudflare status active: 60
Nameserver status active: 60
```

Report:

```text
/volume1/docker/devpilot/scripts/cloudflare_batch/cloudflare-active-verify-priority.csv
```

### 4.3 Not Yet Applied

Not yet applied by automation:

- DNS records
- SSL mode
- Redirect rules
- Nginx redirect config

## 5. Incomplete / Pending Work

### 5.1 Commit and Deployment of Latest Product Domain Work

The latest Product Domain / Redirect Plan work exists in the repo working tree. It still needs a normal commit/deploy phase if it should go to production.

Likely files:

```text
AGENTS.md
app.py
services/product_domains.py
templates/base.html
templates/product_domains.html
tests/test_product_domains.py
docs/ai_office_website_architecture_report.md
docs/devpilot_admin_feature_status_report.md
```

### 5.2 DNS Record Setup

Needed:

- Confirm default official product hosting target.
- Confirm `www` behavior.
- Decide whether `app` and `api` subdomains are needed for each product.
- Dry-run first.
- Apply only after approval.

### 5.3 SSL Setup

Needed:

- Confirm Cloudflare SSL mode.
- Confirm origin certificate strategy.
- Decide Full vs Full strict.

### 5.4 Redirect Rule Setup

Needed:

- Choose implementation:
  - Cloudflare Redirect Rules
  - Cloudflare Bulk Redirects
  - Nginx
- Confirm whether `www.source` should also redirect.
- Use current read-only exports as templates.

### 5.5 Website IA and Content

Needed:

- Brand Hub sitemap.
- Suite pages.
- Product landing template.
- Product-specific copy and positioning.
- Canonical SEO strategy.
- Analytics/conversion strategy.

### 5.6 AI Console Apply-to-Project

Needed:

- Plan generator.
- Approval payload draft.
- Diff preview.
- Future apply-to-staging only.

Still prohibited until explicitly approved:

- Writing sandbox output into project repo.
- Deploying generated output.

### 5.7 Fleet Protection

Needed:

- Cloudflare Access in front of Fleet Console.
- Protected domain:

```text
fleet.aicenter.com.tw
```

- Verify:
  - root no longer public
  - APIs no longer public
  - WebSocket headers work

## 6. Safety and Governance

Current DevPilot posture:

- Read-only first.
- Dry-run before write.
- Controlled deploy by explicit file list.
- No `.env` overwrite.
- No production DB schema changes without explicit phase.
- No token or secret output.
- No git push unless explicitly approved.

High-risk actions requiring separate phase:

- Cloudflare DNS create/update/delete.
- Cloudflare SSL write.
- Redirect rule write.
- Registrar nameserver changes.
- NAS reverse proxy changes.
- Synology certificate changes.
- Telegram send.
- Production deploy.
- Backend restart.
- Project repo write from AI Console artifact.

## 7. Recommended Next Roadmap

### Phase 1: Analyst Architecture Review

Review:

- Product-domain catalog.
- Redirect/campaign/infra/reserved roles.
- Brand Hub and suite hierarchy.
- Official domain choices.

### Phase 2: Product Domain Production Deploy

Controlled deploy latest Product Domain UI/API only.

### Phase 3: DNS Plan Dry-run

Generate product DNS plan:

- `@`
- `www`
- optional `app`
- optional `api`

No write.

### Phase 4: Redirect Rule Dry-run

Use export templates and compare:

- Cloudflare Bulk JSON
- Nginx template
- CSV review

No write.

### Phase 5: Brand Hub IA

Define actual website structure for:

- `aioffice.com.tw`
- suites
- product cards
- lead capture
- SEO

### Phase 6: Product Landing Template

Create reusable page template before building 26 individual product sites.

### Phase 7: AI Console Apply Plan Generator

Generate apply plans from sandbox artifacts, still no project writes.

## 8. Analyst Review Questions

1. Should every official product domain get a standalone landing page, or should rollout start with selected suites?
2. Is `AIShopping` the official product name, or should `ShopAI` become the official brand?
3. Which domains should be reclassified as `reserved` instead of redirect?
4. Which domains are infrastructure endpoints and should use `infra`?
5. Should campaign domains redirect immediately or host temporary campaign pages?
6. Should redirects preserve full request path?
7. Should redirects include both apex and `www` variants?
8. What is the canonical SEO policy across `.tw`, `.com.tw`, `.net.tw`, and `.fun`?
9. What should the AI Office Brand Hub conversion path be?
10. What is the minimum safe production launch set?
