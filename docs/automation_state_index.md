# DevPilot Automation State Index

Date: 2026-05-20
Status: active automation state index, docs-only

## Purpose

This file records the current operational state of DevPilot automation governance. It is the quick index for operators and Codex sessions before starting new work.

## Current Automation Status

- Automation governance baseline: established.
- Latest automation governance commit: `206ca75 docs: add automation decision gates`.
- Latest route verification commit: `3d814d0 docs: record AI Handoffs production route verification`.
- Latest External AI Gateway deployment: `fbf058b feat: enable external AI gateway providers` deployed to NAS production on 2026-05-20.
- Latest External AI Policies UI deployment: `daa0941 feat: improve external AI model onboarding UI` deployed to NAS production on 2026-05-21.
- Current automation maturity estimate: 80-85%.
- Target next maturity band: 85-90%.
- Production route verification: passed.
- Deployment action required: no.
- Rollback required: no.

## External AI Gateway Production State

- Route: `POST /api/external/ai/generate`.
- Deployment target: NAS production `/volume1/docker/devpilot`.
- Production URL: `https://devpilot.aicenter.com.tw`.
- Deployed commit: `fbf058b feat: enable external AI gateway providers`.
- Deployment status: completed.
- Source system: `external_project_default`.
- DevPilot-issued external API key: created and handed off separately; value is not stored in this repository.
- External AI Policy: enabled.
- Allowed providers: `openai`, `gemini`, `claude`.
- Allowed models: `gpt-4.1-mini`, `gpt-4o-mini`, `gemini-2.5-flash`, `claude-haiku-4-5-20251001`.
- Conservative MVP limits: `max_tokens_per_request=1000`, `daily_request_limit=100`, `daily_token_limit=50000`, `monthly_budget_usd=10.0`.
- Provider live calls performed during deployment: no.
- Post-deploy smoke:
  - `/ai-handoffs`: `302` to login while unauthenticated.
  - `/api/external/ai/generate`: `405` for HEAD, route present and POST-only.
  - unauthenticated POST to `/api/external/ai/generate`: `403`, route rejects missing DevPilot external auth.

## External AI Policies UI State

- Route: `/admin/external-ai-policies`.
- Latest deployed UI commit: `daa0941 feat: improve external AI model onboarding UI`.
- Deployment status: completed.
- UI-only changes:
  - Gateway MVP preset cards.
  - OpenAI/Gemini/Claude provider tabs.
  - Model cards for active gateway models.
  - Candidate / Future Models section for non-active model roadmap entries.
  - Non-submitting Candidate / Future model cards with front-end-only `Request enable` onboarding guidance.
  - Capabilities rendered as pill/chip choices.
  - Advanced / Future Providers section for non-MVP providers.
  - Live selected summary.
  - Client-side policy table filter.
- Active Gateway Models only: `gpt-4.1-mini`, `gpt-4o-mini`, `gemini-2.5-flash`, `claude-haiku-4-5-20251001`.
- Candidate / Future Models are not active allowlist entries and require Gateway model onboarding before external projects can use them.
- Presets select Active Gateway Models only; they must not enable GPT-5.x, Claude Sonnet, image, video, or other candidate models.
- Post-deploy smoke:
  - `/admin/external-ai-policies`: `302` to login while unauthenticated.
- Provider live calls performed during UI deployment: no.
- Policy data changed during UI deployment: no.

## Active Route Decisions

- AI Handoffs active production route: `/ai-handoffs`.
- AI Handoffs legacy / non-active route: `/admin/devpilot-handoffs`.
- Legacy route `404` status: acceptable.
- Recovery classification: not a production recovery failure.
- Smoke test route: `/ai-handoffs`.
- Optional follow-up: compatibility redirect from `/admin/devpilot-handoffs` to `/ai-handoffs`; requires separate approval, testing, and deployment.

## Current Safe Automation Capabilities

- Docs-only edits.
- Docs-only `git diff --check`.
- Docs-only commit.
- Docs-only push when explicitly requested.
- Read-only route verification.
- Smoke test checklist updates.
- Handoff note updates.
- Operator task classification using `docs/operator_automation_checklist.md`.
- Codex task generation using `docs/codex_task_template.md`.
- Ledger review using `docs/automation_task_ledger.md`.

## Approval-gated Capabilities

- Runtime code changes.
- Route redirects.
- Deploy.
- Restart.
- Build.
- Docker actions.
- NAS / staging / production operations.
- Rollback.
- Provider live calls.
- Secrets / `.env` changes.
- CI/CD behavior changes.

## Recommended Next Phases

Candidate future phases only; none are approved by this document:

- Add a machine-readable automation policy file, for example `docs/automation_policy.yml`.
- Add a docs-only PR / commit checklist.
- Add a route smoke test checklist.
- Add an optional runtime redirect task plan for `/admin/devpilot-handoffs` -> `/ai-handoffs`.
- Add a release readiness scorecard.
- Add an incident classification checklist.
- Add a no-provider-call gateway validation mode, such as `dry_run` or `validate_only`, so future auth/policy smoke tests can validate configured policies without token spend.
- Run separately approved live smoke tests, one provider at a time, for Gemini, OpenAI, and Claude.

## State Update Rules

- Update this file after major automation governance changes.
- Add each completed automation task to `docs/automation_task_ledger.md`.
- Do not mark runtime, deploy, or provider work as completed unless actually performed and approved.
- Do not infer production state from legacy routes without checking the active route.
- Keep route decisions tied to commit references where possible.
- If this state index conflicts with runtime evidence, stop and gather read-only verification before acting.
