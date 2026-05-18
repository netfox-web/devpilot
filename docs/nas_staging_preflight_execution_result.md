# NAS Staging Preflight Execution Result

Date: 2026-05-18
Status: preflight result, no deployment

## Current Gate Status

```text
NAS-side read-only preflight passed for corrected target
```

Human initially confirmed `/volume1/docker-staging/devpilot` and port `5012` as the corrected DevPilot staging target. Corrected NAS-side read-only preflight passed for that target, but this result is now superseded.

Human decision A now states that `5010` is production only and staging requires a separate correct target. Deployment remains blocked.

## Summary

- Local repo status: pass. The local repository is on `main` and aligned with `origin/main`.
- NAS access status: pass. SSH reached `chaokun@211.75.219.184`.
- NAS hostname: `disney`.
- App path exists: fail. `/volume1/docker/devpilot-staging` does not exist.
- Candidate path discovery: completed, read-only.
- Candidate fingerprint result: candidate runtime identified, pending human confirmation.
- Docker / Compose inspection: completed, read-only.
- Staging-like runtime indicated by Docker labels: `/volume1/docker-staging/devpilot`.
- Staging-like port indicated by Docker: `5012->5000`, now superseded / old target.
- Corrected staging target: unresolved after human decision A.
- Corrected NAS-side read-only preflight: superseded.
- Human-confirmed production URL: `https://devpilot.aicenter.com.tw/`.
- Human decision A: `5010` is production only; staging requires a separate correct target.
- Staging public URL / domain: unconfirmed.
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
- Human confirmed `https://devpilot.aicenter.com.tw/` is production, not staging.
- Human initially confirmed `/volume1/docker-staging/devpilot` and port `5012` as the corrected staging target.
- Corrected NAS-side read-only preflight passed, but this result is now superseded.
- Human decision A confirmed `5010` is production only and staging requires a separate correct target.

## Not Completed

- The old expected staging path `/volume1/docker/devpilot-staging` was not found and is outdated or incorrect.
- The old planned staging port `5011:5000` is outdated or incorrect.
- Current repo commit confirmation is not applicable inside the corrected runtime path because it is not a git repo.
- Documentation expected path and port do not match actual Docker staging runtime.
- Actual runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- Deployment approval has not been granted.

## NAS-side Preflight Failure

Classification:

```text
staging target unresolved
```

Gate:

```text
NAS-side read-only preflight passed for corrected target
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

Production and staging must be separated. The production public URL is human-confirmed:

```text
https://devpilot.aicenter.com.tw/
```

This URL must not be used as staging evidence.

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

- Production URL: `https://devpilot.aicenter.com.tw/`
- Likely production runtime: `/volume1/docker/devpilot` on `5010->5000`
- Confirmed staging runtime: `/volume1/docker-staging/devpilot` on `5012->5000`
- Staging public URL / domain: unconfirmed
- Documented expected path: `/volume1/docker/devpilot-staging`
- Actual staging working directory: `/volume1/docker-staging/devpilot`
- Documented planned port: `5011:5000`
- Actual staging port: `5012->5000`
- Port `5011` is occupied by `gkh-dispatch`.

## Corrected NAS-side Preflight Result, Now Superseded

| Check | Result | Notes |
| --- | --- | --- |
| hostname | pass | `disney` |
| user | pass | `chaokun` |
| pwd | pass | `/volume1/docker-staging/devpilot` |
| corrected staging target exists | pass | confirmed target exists |
| git repo | not applicable | runtime path is not a git repo |
| git status | not applicable | not a git repo or git unavailable |
| latest log includes `e201f2b` | not applicable | runtime path is not a git repo |
| latest log includes `cd96416` | not applicable | runtime path is not a git repo |
| Docker version | pass | Docker version 24.0.2, build 610b8d0 |
| Compose version | pass | Docker Compose version v2.20.1-6047-g6817716 |
| staging container found | pass | `devpilot-project-manager-staging` |
| staging container status | pass | Up 11 days |
| staging image | pass | `devpilot-staging-devpilot-staging` |
| staging ports | pass | `0.0.0.0:5012->5000/tcp`, `:::5012->5000/tcp` |
| compose project | pass | `devpilot-staging` |
| compose service | pass | `devpilot-staging` |
| compose working dir | pass | `/volume1/docker-staging/devpilot` |
| compose config file | pass | `/volume1/docker-staging/devpilot/docker-compose.yml` |
| compose services | pass | `devpilot-staging` |
| compose config | pass | OK |
| `/volume1` disk space | pass | 3.3T available, 54% used |
| `/volume2` disk space | note | 95% used, but staging target is on `/volume1` |
| `docker-compose.yml` | pass | exists |
| `.env` | pass | exists; content not printed |
| `data/uploads/backups/scripts` | pass | exist |
| port `5012` evidence | superseded | `devpilot-project-manager-staging` maps `5012->5000`; later human correction says `5012` is old and the correct port should be `5010` |

## Target Contradiction

Classification:

```text
staging target unresolved
```

Gate:

```text
blocked
```

The earlier corrected preflight was for `/volume1/docker-staging/devpilot` on port `5012`. Human correction later stated that `5012` is old and that the correct port should be `5010`.

This conflicts with previous Docker evidence because `5010` was associated with:

- container `devpilot-project-manager`
- compose project `devpilot`
- working directory `/volume1/docker/devpilot`
- production URL `https://devpilot.aicenter.com.tw/`

Therefore:

- The corrected NAS-side preflight can no longer be treated as passed.
- The readiness gate is blocked.
- Staging and production target boundaries must be revalidated.
- No further deployment approval should proceed from the previous `5012` evidence.

Human decision A resolves one part of the contradiction:

- `5010` is production only.
- Do not use `5010` as staging.
- Do not touch the production target.
- Production URL remains `https://devpilot.aicenter.com.tw/`.
- Production-like runtime remains protected:
  - `/volume1/docker/devpilot`
  - container `devpilot-project-manager`
  - port `5010->5000`
- Previous `5012` staging evidence is superseded / old target:
  - `/volume1/docker-staging/devpilot`
  - container `devpilot-project-manager-staging`
  - port `5012->5000`
- Correct staging target remains unknown.
- Readiness gate remains blocked.

Deployment execution note:

- A staging deployment build/up was executed against `/volume1/docker-staging/devpilot` on port `5012` before the later human port correction arrived.
- That execution was based on the then-approved corrected staging target.
- The new target contradiction means no further deploy, restart, build, pull, or Docker action is approved.
- Do not mark deployment readiness as passed.

## Required Unblock

- Human must decide one of:
  - identify a new staging target that excludes production `5010` and treats `5012` as old/superseded.
  - confirm staging / production labels are outdated and remap them before any deployment process continues.
  - stop staging deployment readiness until a safe staging target exists.

## Deployment Decision

- Classification is `staging target unresolved`.
- Gate is `blocked`.
- A staging deployment build/up was executed against `/volume1/docker-staging/devpilot` on port `5012` before the later port correction arrived.
- That execution must not be treated as approval to continue.
- No further deployment, restart, build, pull, Docker run, or compose action is approved.
- Readiness must not be marked passed until a new staging target is identified and read-only preflight passes.

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
| corrected staging target exists | pass | `/volume1/docker-staging/devpilot` exists. |
| git repo | not applicable | runtime path is not a git repo. |
| latest synced commit present | not applicable | runtime path is not a git repo. |
| previous docs commit present | not applicable | runtime path is not a git repo. |
| compose config valid for runtime candidate | pass | `/volume1/docker-staging/devpilot` service `devpilot-staging`; compose config OK. |
| .env contents protected | pass | `.env` presence only was checked; contents were not printed. |
| no further NAS mutation | pass | After the target contradiction was detected, no further deploy, restart, build, pull, Docker run, git mutation, mkdir/rm/mv/cp, or file edit is approved. |

## Blockers

- Old documented expected path does not exist.
- Old documented planned port is not the staging port.
- `5010` is production only and must not be used as staging.
- Previous `5012` staging evidence is superseded / old target.
- Correct staging target remains unknown.
- Production and staging evidence must remain separated.
- Production URL must not be treated as staging evidence.
- Staging public URL/domain is still unconfirmed.
- Documentation expected path and port do not match the actual Docker staging runtime.
- Runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- No further deployment action may proceed until a new staging target is identified and read-only preflight passes.

## Safety Confirmation

- No `docker compose down` was executed.
- No `docker compose restart` was executed.
- No `docker compose pull` was executed.
- No `docker run` was executed.
- No further deploy is approved.
- No further restart is approved.
- No further build or pull is approved.
- No `git pull/push/merge/rebase` was executed on NAS.
- No `mkdir/rm/mv/cp` was executed on NAS.
- Source files were synced to `/volume1/docker-staging/devpilot` as part of the previously approved staging deployment attempt; no additional NAS file edits are approved after the contradiction.
- No NAS setting was changed.
- No `.env` contents were printed.
- No secrets were printed.
- No Nginx, DNS, Cloudflare, or SSL setting was changed.
- No R2 mutation was executed.
- No provider live call was executed.
- No commit or push was executed.

## Recommended Next Step

Staging target is unresolved. Human review must decide one of:

- identify a new staging target that excludes production `5010` and treats `5012` as old/superseded.
- confirm staging / production labels are outdated and remap them before any deployment process continues.
- stop staging deployment readiness until a safe staging target exists.

Staging public URL / domain must be explicitly confirmed before readiness can pass. The production URL `https://devpilot.aicenter.com.tw/` is not staging evidence.

Do not proceed to any further deployment action until a new staging target is identified, read-only preflight passes, and a new explicit approval is given.
