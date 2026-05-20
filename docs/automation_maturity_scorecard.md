# DevPilot Automation Maturity Scorecard

Date: 2026-05-20
Status: active maturity scorecard, docs-only

## Purpose

This scorecard tracks progress toward safe 90%+ automation for DevPilot tasks while preserving approval gates for risky actions.

## Current Score

| Area | Current score |
| --- | --- |
| Overall | 80-85% |
| Docs-only | 90% |
| Read-only smoke tests | 80% |
| Runtime code changes | 60% |
| Deploy / rollback | 40% |
| Production recovery | 50% |
| Provider / secrets operations | 20-30% |

## Why Not 100%

The workflow should not aim for fully autonomous production mutation.

Reasons:

- Production actions must remain approval-gated.
- Secrets and provider live calls are high risk.
- Runtime behavior changes require testing.
- Deploy and rollback can cause outages.
- Active route and active source must be verified before recovery classification.
- NAS / Docker / production operations require exact target confirmation.

## What Improved In Recent Phases

- AI Handoffs route verification precedent was documented.
- Automation decision gates were added.
- Codex task template was added.
- Operator automation checklist was added.
- Automation ledger, state index, operating runbook, and maturity scorecard were added by this phase.

## What Would Move To 85-90%

- Machine-readable automation policy.
- Automatic docs-only ledger update.
- Consistent route smoke checklist.
- Task classification before every Codex prompt.
- Release readiness scorecard.
- Incident classification checklist.

## What Should Remain Approval-gated Even At 90%+

- Production deploy.
- Production rollback.
- Docker / NAS / staging / production operations.
- Secrets / `.env`.
- Provider live calls.
- Runtime route changes.
- CI/CD changes.

## Review Cadence

Review this scorecard after:

- Major automation governance updates.
- Production recovery events.
- New deploy or rollback runbooks.
- New provider live-call workflow.
- Any incident where task classification was ambiguous.
