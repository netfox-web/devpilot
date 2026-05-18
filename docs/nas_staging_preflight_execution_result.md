# NAS Staging Preflight Execution Result

Date: 2026-05-18
Status: preflight result, no deployment

## Current Gate Status

```text
blocked: candidate runtime path identified, pending human confirmation
```

The deployment readiness gate must remain blocked. NAS-side read-only checks reached the NAS host and Docker labels identified an actual staging runtime at `/volume1/docker-staging/devpilot`, but the documented path and port do not match that runtime and the latest synced repo commit is not confirmed inside the runtime path.

## Summary

- Local repo status: pass. The local repository is on `main` and aligned with `origin/main`.
- NAS access status: pass. SSH reached `chaokun@211.75.219.184`.
- NAS hostname: `disney`.
- App path exists: fail. `/volume1/docker/devpilot-staging` does not exist.
- Candidate path discovery: completed, read-only.
- Candidate fingerprint result: candidate runtime identified, pending human confirmation.
- Docker / Compose inspection: completed, read-only.
- Actual staging runtime indicated by Docker labels: `/volume1/docker-staging/devpilot`.
- Actual staging port indicated by Docker: `5012->5000`.
- `.env` content: not printed.
- Compose config result summary: OK for `/volume1/docker/devpilot`, `/volume1/docker/devpilot_project_manager`, and `/volume1/docker-staging/devpilot`; failed for `/volume1/worktrees/devpilot-build-321df5d`.
- `py_compile` result: pass. `app.py` compiled successfully from the local repo.

## Completed

- Repo-side docs were committed and pushed in `61a0e74 docs: record NAS staging preflight result`.
- `origin/main` sync was confirmed.
- Read-only repo gate review was completed.
- Commit `61a0e74` was confirmed docs-only.
- SSH reached the NAS host as `chaokun@211.75.219.184`.
- NAS hostname was reported as `disney`.
- Expected path check was executed and failed.
- Read-only path discovery and candidate fingerprint checks were executed.
- Docker / Compose read-only inspection was executed.
- Docker is available via `/usr/local/bin/docker`.
- Docker Compose is available via `/usr/local/bin/docker compose`.
- Docker labels identified `devpilot-project-manager-staging` as the running staging container.

## Not Completed

- The expected staging path `/volume1/docker/devpilot-staging` was not found.
- No candidate path confirmed the latest synced commit `d8a65d8`.
- No candidate path confirmed the previous commit `61a0e74`.
- Documentation expected path and port do not match actual Docker staging runtime.
- Actual runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- NAS-side readiness was not marked passed.

## NAS-side Preflight Failure

Classification:

```text
candidate runtime path identified, pending human confirmation
```

Gate:

```text
blocked
```

Deployment:

- not approved
- not executed
- must not proceed

Failure reasons:

1. Expected staging path missing:
   - `/volume1/docker/devpilot-staging`
2. Candidate paths checked:
   - `/volume1/docker-staging/devpilot`
   - `/volume1/docker/devpilot_project_manager`
   - `/volume1/docker/devpilot`
   - `/volume1/worktrees/devpilot-build-321df5d`

## Candidate Fingerprint Summary

| Candidate path | Exists | Git repo | Git status / commit evidence | Compose file | `.env` | Compose config | Staging likelihood |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/volume1/docker-staging/devpilot` | yes | no | cannot confirm `d8a65d8` or `61a0e74` | yes | yes, content not printed | FAILED | medium-low |
| `/volume1/docker/devpilot_project_manager` | yes | no | cannot confirm `d8a65d8` or `61a0e74` | yes | yes, content not printed | FAILED | low |
| `/volume1/docker/devpilot` | yes | no | cannot confirm `d8a65d8` or `61a0e74` | yes | yes, content not printed | FAILED | low |
| `/volume1/worktrees/devpilot-build-321df5d` | yes | yes | `## HEAD (no branch)`; latest log does not include `d8a65d8` or `61a0e74` | yes | no | FAILED | low |

## Docker / Compose Runtime Evidence

Docker / Compose:

- Docker available: yes, via `/usr/local/bin/docker`
- Compose available: yes, via `/usr/local/bin/docker compose`
- `docker` is not in the SSH user's default PATH, but the binary exists at `/usr/local/bin/docker`.

Actual staging runtime identified:

| Field | Value |
| --- | --- |
| container | `devpilot-project-manager-staging` |
| image | `devpilot-staging-devpilot-staging` |
| status | Up 11 days |
| port | `5012->5000` |
| compose project | `devpilot-staging` |
| service | `devpilot-staging` |
| working_dir | `/volume1/docker-staging/devpilot` |
| config_files | `/volume1/docker-staging/devpilot/docker-compose.yml` |

Mounts:

- `/volume1/docker-staging/devpilot/data -> /app/data`
- `/volume1/docker-staging/devpilot/uploads -> /app/uploads`
- `/volume1/docker-staging/devpilot/backups -> /app/backups`
- `/volume1/docker-staging/devpilot/scripts -> /app/scripts`

Related DevPilot containers:

| Container | Image | Status | Port | Compose project | Working dir |
| --- | --- | --- | --- | --- | --- |
| `devpilot-project-manager` | `devpilot-devpilot` | Up 4 days | `5010->5000` | `devpilot` | `/volume1/docker/devpilot` |
| `devpilot-project-manager-staging` | `devpilot-staging-devpilot-staging` | Up 11 days | `5012->5000` | `devpilot-staging` | `/volume1/docker-staging/devpilot` |
| `devpilot-project18-staging-preview` | `nginx:alpine` | Up 12 days | `5999->80` | `template-dispatch-nas-test-20260506-013007` | `/volume1/docker-staging/template-dispatch-nas-test-20260506-013007` |
| `devpilot-project-manager-backup-20260505-133349` | `devpilot_project_manager-devpilot` | Created | none visible | `devpilot_project_manager` | `/volume1/docker/devpilot_project_manager` |

Candidate compose checks using the full Docker binary path:

| Candidate path | Services | Compose config |
| --- | --- | --- |
| `/volume1/docker/devpilot` | `devpilot` | OK |
| `/volume1/docker/devpilot_project_manager` | `devpilot` | OK |
| `/volume1/docker-staging/devpilot` | `devpilot-staging` | OK |
| `/volume1/worktrees/devpilot-build-321df5d` | unavailable | FAILED |

Important mismatch:

- Documented expected path: `/volume1/docker/devpilot-staging`
- Actual staging working directory: `/volume1/docker-staging/devpilot`
- Documented planned port: `5011:5000`
- Actual staging port: `5012->5000`
- Port `5011` is occupied by `gkh-dispatch`.

## Required Unblock

- Human must decide one of:
  - confirm `/volume1/docker-staging/devpilot` and port `5012` as the real NAS staging target, then rerun read-only preflight using this corrected target,
  - update deployment docs from `/volume1/docker/devpilot-staging:5011` to `/volume1/docker-staging/devpilot:5012` if this is the intended staging environment,
  - provision the originally documented path `/volume1/docker/devpilot-staging` through an approved setup process,
  - stop deployment readiness until path/port ownership is resolved.

## Deployment Decision

- Deployment is not approved.
- Deployment was not executed.
- Readiness must not be marked passed.
- Deployment must not proceed.

## Checks

| Check | Result | Notes |
| --- | --- | --- |
| local main aligned | pass | `git status -sb` returned `## main...origin/main`. |
| local branch is main | pass | `git branch --show-current` returned `main`. |
| local recent commits readable | pass | Latest commit is `b2cdc50 docs: add NAS staging Docker preflight plan`. |
| local stash listed | pass | Existing stashes were listed and not applied or deleted. |
| app.py exists | pass | Local `app.py` exists. |
| Dockerfile exists | pass | Local `Dockerfile` exists. |
| requirements.txt exists | pass | Local `requirements.txt` exists. |
| docker-compose.nas.example.yml exists | pass | Local NAS compose example exists. |
| readiness doc exists | pass | `docs/nas_staging_deployment_readiness_check.md` exists. |
| py_compile app.py | pass | Local compile check completed successfully. |
| NAS shell access | pass | SSH reached `chaokun@211.75.219.184`; hostname `disney`. |
| expected staging path exists | fail | `/volume1/docker/devpilot-staging` does not exist. |
| candidate path discovery | pass | Read-only discovery completed. |
| candidate runtime path identified | pass | Docker labels identify `/volume1/docker-staging/devpilot` as the running `devpilot-staging` compose working directory. |
| latest synced commit present | fail | No candidate confirmed `d8a65d8`. |
| previous docs commit present | fail | No candidate confirmed `61a0e74`. |
| compose config valid for runtime candidate | pass | `/volume1/docker-staging/devpilot` service `devpilot-staging`; compose config OK. |
| .env contents protected | pass | `.env` presence only was checked; contents were not printed. |
| no NAS mutation | pass | No deploy, restart, build, pull, Docker run, git mutation, mkdir/rm/mv/cp, or file edit was executed. |

## Blockers

- Expected path does not exist.
- No candidate confirms latest synced commit `d8a65d8`.
- No candidate confirms previous commit `61a0e74`.
- Documentation expected path and port do not match the actual Docker staging runtime.
- Runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- Correct staging target still requires human confirmation.

## Safety Confirmation

- No `docker compose up` was executed.
- No `docker compose down` was executed.
- No `docker compose restart` was executed.
- No `docker compose build` or image build was executed.
- No `docker compose pull` was executed.
- No `docker run` was executed.
- No deployment was executed.
- No service restart was executed.
- No `git pull/push/merge/rebase` was executed on NAS.
- No `mkdir/rm/mv/cp` was executed on NAS.
- No file edits were made on NAS.
- No NAS setting was changed.
- No `.env` contents were printed.
- No secrets were printed.
- No Nginx, DNS, Cloudflare, or SSL setting was changed.
- No R2 mutation was executed.
- No provider live call was executed.
- No commit or push was executed.

## Recommended Next Step

Preflight is blocked because a candidate runtime path was identified but not yet confirmed as the intended staging target. Human review must decide one of:

- confirm `/volume1/docker-staging/devpilot` and port `5012` as the real NAS staging target, then rerun read-only preflight using this corrected target,
- update deployment docs from `/volume1/docker/devpilot-staging:5011` to `/volume1/docker-staging/devpilot:5012` if this is the intended staging environment,
- provision the originally documented path `/volume1/docker/devpilot-staging` through an approved setup process,
- stop deployment readiness until path/port ownership is resolved.

Do not mark readiness as passed and do not proceed to deployment approval until a human-confirmed staging path passes read-only preflight.
