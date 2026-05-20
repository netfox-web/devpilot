# DevPilot Automation State Index

Date: 2026-05-20
Status: active automation state index, docs-only

## Purpose

This file records the current operational state of DevPilot automation governance. It is the quick index for operators and Codex sessions before starting new work.

## Current Automation Status

- Automation governance baseline: established.
- Latest automation governance commit: `206ca75 docs: add automation decision gates`.
- Latest route verification commit: `3d814d0 docs: record AI Handoffs production route verification`.
- Current automation maturity estimate: 80-85%.
- Target next maturity band: 85-90%.
- Production route verification: passed.
- Deployment action required: no.
- Rollback required: no.

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

## State Update Rules

- Update this file after major automation governance changes.
- Add each completed automation task to `docs/automation_task_ledger.md`.
- Do not mark runtime, deploy, or provider work as completed unless actually performed and approved.
- Do not infer production state from legacy routes without checking the active route.
- Keep route decisions tied to commit references where possible.
- If this state index conflicts with runtime evidence, stop and gather read-only verification before acting.
