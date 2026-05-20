# DevPilot Automation Decision Gates

Date: 2026-05-20
Status: active governance guidance, docs-only

## Related Automation Docs

- `docs/automation_task_ledger.md` records completed automation tasks and final states.
- `docs/automation_state_index.md` records the current automation operating state.
- `docs/automation_operating_runbook.md` describes the operator/Codex workflow.
- `docs/automation_maturity_scorecard.md` tracks progress toward safe 90%+ automation.

## Purpose

This document defines safe automation rules for DevPilot tasks so docs-only updates, read-only verification, runtime changes, deploys, rollback, and production recovery are handled consistently.

The goal is to let Codex and operators move faster without blurring approval boundaries. Low-risk work can be handled with a standard checklist. High-risk work must stop at an explicit gate before it touches production, infrastructure, secrets, provider live calls, or runtime behavior.

## Automation Maturity

Current maturity estimate:

| Area | Estimate |
| --- | --- |
| Overall workflow | 70-80% automated |
| Docs-only updates | 85-90% |
| Smoke test / read-only verification | 70-80% |
| Runtime code changes | 50-60% |
| Deploy / rollback | 30-40% |
| Production incident recovery | 40-50% |

The target is to move toward 90%+ automation while preserving explicit approval gates for risky production actions.

## Task Classes

### Class A - Docs-only Update

Allowed without additional approval:

- Modify docs, checklists, runbooks, release notes, and handoff notes.
- Run `git diff --check`.
- Run `git status`.
- Commit docs-only changes.
- Push docs-only commits to `main` when explicitly requested by the operator.

Forbidden:

- Runtime code changes.
- Build, deploy, or restart.
- Docker commands.
- NAS or staging access.
- Secrets or `.env` changes.
- Provider live calls.

### Class B - Read-only Verification / Smoke Test

Allowed:

- `curl -I` or other HEAD/header checks.
- Status checks.
- Read-only git checks.
- Log review when logs are already local and safe to inspect.
- Route verification.

Forbidden:

- Runtime code changes.
- Deploy, restart, or rollback.
- Database writes.
- Docker changes.
- Secrets or `.env` changes.
- Provider live calls unless explicitly approved.

### Class C - Runtime Code Change

Allowed only after explicit approval:

- Prepare a patch.
- Modify app code.
- Add redirects.
- Change routes.
- Update tests.
- Run local tests if safe.

Requires explicit approval before:

- Commit.
- Push.
- Deploy.
- Restart.
- Docker action.
- Production verification involving provider live calls.

### Class D - Deploy / Restart / Docker / NAS / Staging Operation

Always requires explicit approval.

Includes:

- `docker compose`.
- Docker restart.
- Docker pull.
- Docker build.
- NAS access.
- Staging or production server changes.
- Service restart.
- Release promotion.
- Rollback.

### Class E - Production Recovery / Rollback

Always requires explicit approval.

Rules:

- First classify whether the issue is actually a recovery failure.
- Verify the active route, active source, and expected behavior before acting.
- Do not treat legacy route `404` as a recovery failure without confirming the active route.
- Prepare a recovery plan before action.
- Do not rollback unless rollback is explicitly approved.

### Class F - Provider Live Call / Secrets / .env

Always requires explicit approval.

Includes:

- Provider API live calls.
- OpenAI, Gemini, Claude, or other provider calls from the app environment.
- Secrets rotation.
- `.env` edit.
- Credential inspection.
- Production config changes.

## Default Execution Matrix

| Task type | Auto-edit allowed | Auto-commit allowed | Auto-push allowed | Requires approval | Notes |
| --- | --- | --- | --- | --- | --- |
| docs-only | yes | yes, when explicitly requested | yes, when explicitly requested | no additional approval beyond task request | Must remain docs-only. |
| read-only smoke test | no | no | no | no, if strictly read-only | Must not log in, mutate data, or call providers unless approved. |
| runtime code change | only after explicit approval | no, unless explicitly requested | no, unless explicitly requested | yes | Includes app code, routes, templates, tests, and behavior changes. |
| route redirect | only after explicit approval | no, unless explicitly requested | no, unless explicitly requested | yes | Redirects are runtime behavior changes. |
| deploy | no | no | no | yes | Includes production and staging deploys. |
| rollback | no | no | no | yes | Must include rollback target and safety plan. |
| provider live call | no | no | no | yes | Mocked or docs-only provider work is separate from live calls. |
| secrets / `.env` | no | no | no | yes | Do not read, print, rotate, or edit secrets without approval. |
| NAS / staging operation | no | no | no | yes | Even read-only NAS access should be explicitly scoped. |

## AI Handoffs Route Precedent

The confirmed AI Handoffs production route is:

- Active production route: `/ai-handoffs`
- Legacy / non-active route: `/admin/devpilot-handoffs`

Decision:

- `/admin/devpilot-handoffs` returning `404` is acceptable.
- This is not a production recovery failure.
- Smoke tests must use `/ai-handoffs` as the active route.
- Unauthenticated access to `/ai-handoffs` should redirect to login.
- Authenticated access should show the AI Handoffs page.

Follow-up candidate:

- Add a compatibility redirect from `/admin/devpilot-handoffs` to `/ai-handoffs`.

The redirect is a runtime code change and requires separate approval, testing, and deployment.

## Required Codex Report Format

Every Codex task should report:

- Summary.
- Files changed.
- Commands run.
- Verification result.
- Safety confirmation.
- Commit hash, if committed.
- Final `git status -sb`.
- Latest `git log --oneline -5`, if committed.
- Explicit confirmation whether runtime code changed.
- Explicit confirmation whether deploy, restart, build, Docker, NAS, staging, secrets, `.env`, or provider live calls occurred.

## Stop Conditions

Codex must stop and report instead of continuing if:

- Unexpected dirty working tree exists before edits.
- Runtime files change during a docs-only task.
- Secrets or `.env` would be touched.
- Deploy, restart, build, Docker, NAS, or staging command would be needed.
- Provider live call would be needed.
- Route or runtime behavior change would be needed.
- Task scope becomes ambiguous or unsafe.
