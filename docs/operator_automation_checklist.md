# Operator Automation Checklist

Date: 2026-05-20
Status: operator checklist, docs-only

Use this checklist before sending a DevPilot task to Codex. Classify the task with `docs/automation_decision_gates.md` first.

## Related Automation Docs

- `docs/automation_task_ledger.md` records completed automation tasks and final states.
- `docs/automation_state_index.md` records the current automation operating state.
- `docs/automation_operating_runbook.md` describes the operator/Codex workflow.
- `docs/automation_maturity_scorecard.md` tracks progress toward safe 90%+ automation.

## Pre-task Questions

- Is this docs-only?
- Is this read-only?
- Does this touch runtime code?
- Does this require route changes?
- Does this require deploy, restart, build, or Docker?
- Does this touch NAS, staging, or production?
- Does this touch secrets or `.env`?
- Does this require provider live calls?
- Can Codex commit?
- Can Codex push?
- What should Codex report back?

## Recommended Default Decisions

| Task type | Default decision |
| --- | --- |
| docs-only | Codex may edit, verify, commit, and push if explicitly requested. |
| read-only smoke test | Codex may run read-only commands only. |
| runtime change | Codex may prepare a patch only after explicit approval. |
| deploy / rollback | Explicit approval required. |
| secrets / provider calls | Explicit approval required. |

## Operator Prompt Checklist

When creating a task, specify:

- Repo path.
- Branch expectation.
- Task class.
- Allowed files.
- Forbidden files.
- Whether commit is allowed.
- Whether push is allowed.
- Whether runtime code may change.
- Whether deployment, restart, build, Docker, NAS, staging, production, secrets, `.env`, or provider live calls are forbidden.
- Required verification commands.
- Required final report format.

## Default Safety Language

Use this language when uncertain:

```text
If the task requires runtime code changes, deploy, restart, build, Docker, NAS/staging/production mutation, secrets, .env, provider live calls, rollback, or ambiguous route behavior changes, stop and report instead of proceeding.
```

## AI Handoffs Route Reminder

- Active production route: `/ai-handoffs`
- Legacy / non-active route: `/admin/devpilot-handoffs`
- A `404` from `/admin/devpilot-handoffs` is acceptable.
- This is not a production recovery failure.
- Smoke tests should use `/ai-handoffs`.
- A compatibility redirect is a separate runtime task requiring separate approval, testing, and deployment.
