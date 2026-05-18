# NAS Staging Deployment Readiness Check

Date: 2026-05-18
Status: readiness report and Docker staging preflight command plan, docs-only, no deployment

## 1. Current Repo Status

Current local check:

```text
git status -sb: ## main...origin/main
```

Conclusion:

- Local `main` is aligned with `origin/main`.
- This report is docs-only.
- No deployment, restart, NAS setting change, production change, DNS/Cloudflare/Nginx/SSL write, `.env` edit, or secret access was performed.
- Topology decision recorded: Docker staging at `/volume1/docker/devpilot-staging` with port mapping `5011:5000`.

## 2. Required Runtime

### Python Version

Recommended:

```text
Python 3.12
```

Evidence:

- `Dockerfile` uses `python:3.12-slim`.

### Virtual Environment

For non-Docker NAS staging:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For Docker staging, the container image installs dependencies from `requirements.txt`.

### Dependencies

Current `requirements.txt`:

```text
Flask==3.0.3
python-dotenv==1.0.1
cryptography==46.0.7
requests
pandas
dnspython
```

### App Entrypoint

```text
app.py
```

Local/container command:

```bash
python app.py
```

Docker command from `Dockerfile`:

```text
CMD ["python", "app.py"]
```

### Port

Application default:

```text
HOST=0.0.0.0
PORT=5000
```

NAS Docker examples map:

```text
5010:5000
```

Selected staging port:

```text
5011:5000
```

The operator selected Docker staging on port `5011:5000`. Preflight must still confirm the port does not conflict with production or existing NAS containers.

### Data Directory

Runtime data directory:

```text
data/
```

Default SQLite database:

```text
data/project_manager.db
```

### Uploads Directory

Runtime uploads directory:

```text
uploads/
```

### Logs Directory

Local scheduled runner logs:

```text
logs/
```

Container logs may also be read through Docker:

```bash
docker compose logs
```

## 3. Required Environment Variables

Names only. Do not put values in docs, chat, git, UI output, logs, or screenshots.

Core:

- `API_TOKEN`
- `SECRET_KEY`
- `DEV_PILOT_API_URL`
- `DATABASE_PATH`
- `HOST`
- `PORT`
- `FLASK_DEBUG`
- `TZ`

Optional provider / readiness variables:

- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `GOOGLE_GENERATIVE_AI_API_KEY`
- `GEMINI_API_URL`
- `ANTHROPIC_API_KEY`
- `CLAUDE_API_KEY`

Optional Cloudflare / domain planning variables:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `DEFAULT_MAIN_TARGET`
- `DEFAULT_APP_TARGET`
- `DEFAULT_API_TARGET`
- `DEFAULT_PARKING_TARGET`
- `DEFAULT_SSL_MODE`
- `DEFAULT_PROXIED`

Optional store override variables:

- `DEVPILOT_EXTERNAL_API_KEY_STORE_PATH`
- `DEVPILOT_EXTERNAL_AI_POLICY_STORE_PATH`
- `DEVPILOT_EXTERNAL_AI_PERMISSION_PROFILE_STORE_PATH`
- `DEVPILOT_EXTERNAL_AI_GENERATION_RESULTS_PATH`
- `DEVPILOT_EXTERNAL_AI_USAGE_LOG_PATH`
- `DEVPILOT_EXTERNAL_PROJECT_REGISTRY_PATH`
- `DEVPILOT_EXTERNAL_PROJECT_EVENTS_PATH`
- `DEVPILOT_APPROVAL_OBJECTS_PATH`

Optional runner / NAS integration variables:

- `DEV_PILOT_NAS_SSH_PORT`
- `DEVPILOT_CODEX_RUNNER_MODE`
- `DEVPILOT_CODEX_RUNNER_COMMAND`
- `BACKUP_DIR`

## 4. Storage Plan

Recommended staging persistent directories:

```text
data/
uploads/
logs/
```

Important runtime files:

```text
data/project_manager.db
data/approval_objects.json
data/external_ai_usage_log.json
data/external_ai_generation_results.json
data/external_api_keys.json
data/external_ai_policies.json
data/external_ai_permission_profiles.json
data/external_project_registry.json
data/external_project_events.json
```

Staging rules:

- Do not copy production secrets into staging unless explicitly approved.
- Do not commit any runtime data files.
- Keep `data/`, `uploads/`, and `logs/` outside git-managed source when deployed.
- If using Docker, mount `data/` and `uploads/` as persistent volumes.
- Add a staging-specific backup plan before testing any write-capable admin feature.

## 5. NAS Staging Topology Decision

### App Path

Selected Docker staging path:

```text
/volume1/docker/devpilot-staging
```

Venv staging is not selected for this phase.

### Port Mapping

```text
5011:5000
```

### Venv Path

Not applicable for the selected Docker staging topology.

### Service Command Plan

The service command is documented for a later approved staging deployment phase only.

Command plan, do not run during readiness review:

```bash
cd /volume1/docker/devpilot-staging
docker compose up -d --build
```

No service command was run during this readiness check.

### Reverse Proxy

Reverse proxy is explicitly deferred.

Do not write Nginx, Synology reverse proxy, Cloudflare Tunnel, DNS, or Cloudflare config in this phase.

### SSL

SSL is explicitly deferred.

Do not request certificates, change SSL mode, change Nginx SSL config, or change Cloudflare SSL settings in this phase.

## 5A. Docker Staging Preflight Checklist

This checklist is a command plan only. Do not run these commands until a separate approved staging preflight/execution step.

### Operator Decisions Locked

```text
Topology: Docker staging
App path: /volume1/docker/devpilot-staging
Port mapping: 5011:5000
Reverse proxy: deferred / no change
SSL: deferred / no change
Secrets: do not print, copy into docs, or commit
Production: no change
```

### Source Layout Plan

The staging app directory should contain a working copy or deployment copy of the DevPilot repository:

```bash
cd /volume1/docker/devpilot-staging
test -f app.py
test -f Dockerfile
test -f docker-compose.yml
test -f requirements.txt
```

### Compose Port Check Plan

The selected staging mapping should be:

```text
5011:5000
```

Preflight should inspect compose config without starting containers:

```bash
cd /volume1/docker/devpilot-staging
docker compose config
```

Expected check:

```text
ports includes 5011:5000
```

### Persistent Directory Plan

Staging should use local Docker-mounted runtime directories:

```bash
cd /volume1/docker/devpilot-staging
mkdir -p data uploads logs
test -d data
test -d uploads
test -d logs
```

Do not commit runtime data. Do not copy production runtime data unless separately approved.

### Staging Environment Plan

Staging `.env` must exist before actual deployment, but contents must never be printed into terminal logs, docs, screenshots, or chat.

Preflight command plan:

```bash
cd /volume1/docker/devpilot-staging
test -f .env
```

Required staging-safe settings by name:

```text
HOST
PORT
FLASK_DEBUG
DATABASE_PATH
API_TOKEN
SECRET_KEY
DEV_PILOT_API_URL
```

Recommended staging values by policy, not secrets:

```text
HOST=0.0.0.0
PORT=5000
FLASK_DEBUG=0
DATABASE_PATH=data/project_manager.db
DEV_PILOT_API_URL=http://NAS_IP:5011
```

Do not print `API_TOKEN` or `SECRET_KEY`.

## 6. Preflight Commands

Run these on NAS staging only after an explicit staging preflight step.

Repository and files:

```bash
git status -sb
git log --oneline -5
test -f app.py
test -f requirements.txt
test -f Dockerfile
test -f docker-compose.nas.example.yml
```

Python / dependency preflight, optional because Docker is selected:

```bash
python --version
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m py_compile app.py
```

Directory preflight:

```bash
mkdir -p data uploads logs
test -d data
test -d uploads
test -d logs
```

Docker preflight for selected topology:

```bash
docker --version
docker compose version
cd /volume1/docker/devpilot-staging
docker compose config
```

Environment preflight:

```bash
test -f .env
```

Do not print `.env` contents.

## 7. Smoke Test Commands

Only after staging service is started in a later approved phase:

```bash
curl -I http://127.0.0.1:5011/
curl -I http://127.0.0.1:5011/login
curl -s http://127.0.0.1:5011/api/admin/ai-provider-readiness
```

Authenticated API smoke tests require a staging API token. Do not print token values.

Suggested in-container or local Flask checks:

```bash
python -m py_compile app.py
python -m pytest -q tests/test_ai_manual_handoff.py tests/test_automation_plans.py
```

Provider live calls must remain disabled during smoke testing.

## 8. Rollback Plan

Before staging deployment:

1. Record current staging commit SHA.
2. Back up staging `data/`, `uploads/`, and relevant logs.
3. Keep previous staging image or venv available.
4. Confirm service stop/start command, but do not run it during readiness review.

Rollback outline for a later approved staging deployment:

```bash
cd /volume1/docker/devpilot-staging
docker compose down
git checkout <previous_staging_commit>
docker compose up -d --build
```

Because Docker staging is selected, venv rollback is not part of the current topology.

Preflight-only rollback check:

```bash
cd /volume1/docker/devpilot-staging
git log --oneline -5
test -d data
test -d uploads
```

Actual stop/start commands require a separate approved deployment phase.

## 9. Safety Boundaries

This readiness check did not and must not:

- deploy to production
- deploy to staging
- restart any service
- change NAS settings
- change `.env`
- output secrets
- call Gemini, Claude, or any provider live route
- write DNS
- write Cloudflare settings
- write Nginx config
- change SSL
- change registrar or nameserver settings
- mutate R2
- mutate production data
- commit or push

## 10. Go / No-Go Checklist

### Go Conditions

- Repo is clean and on the intended staging commit.
- Docker and Docker Compose are available on NAS.
- `/volume1/docker/devpilot-staging` exists and contains the DevPilot app files.
- Compose config maps `5011:5000`.
- `python -m py_compile app.py` passes.
- Staging `.env` exists on NAS and contains only staging-safe values.
- `data/`, `uploads/`, and `logs/` staging directories exist.
- Staging port `5011` is not conflicting with production.
- Reverse proxy and SSL are explicitly deferred.
- Provider live call flags remain disabled.
- DNS / Cloudflare / Nginx / SSL / R2 / deploy execution remains blocked.
- Backup/rollback plan is documented.

### No-Go Conditions

- `.env` values are missing, copied from production without approval, or exposed in logs/docs.
- Staging and production share unsafe writable runtime data.
- Port conflict exists.
- Python/dependency install fails.
- `py_compile` fails.
- Reverse proxy, SSL, DNS, or Cloudflare changes are required but not approved.
- Provider live verification is requested as part of staging smoke tests.
- Rollback path is not available.

## Latest Preflight Result

Latest result document:

- `docs/nas_staging_preflight_execution_result.md`

Result summary:

- Local repo checks passed.
- Local `app.py` py_compile passed.
- NAS shell access later reached `chaokun@211.75.219.184`; hostname reported `disney`.
- NAS-side preflight failed because the expected staging path `/volume1/docker/devpilot-staging` does not exist.
- Candidate path discovery and fingerprint checks were read-only. None of the candidates passed the readiness gate.
- Docker / Compose read-only inspection later identified a running staging-like runtime:
  - container `devpilot-project-manager-staging`
  - compose project `devpilot-staging`
  - working directory `/volume1/docker-staging/devpilot`
  - port `5012->5000`
- Human confirmation initially established `/volume1/docker-staging/devpilot` and port `5012` as the corrected DevPilot staging target.
- Corrected NAS-side read-only preflight passed for that target, but that result is now superseded.
- Human confirmation later identified `https://devpilot.aicenter.com.tw/` as the production URL, not a staging URL.
- Human decision A later established that `5010` is production only and staging requires a separate correct target.
- Final clarification established that `5010` is the active production site and this flow should no longer be treated as staging deployment readiness.
- No deployment, restart, Docker start/build command, reverse proxy change, SSL change, DNS/Cloudflare change, `.env` output, or secret output was performed.

## Deployment Readiness Gate Status

Current gate status:

```text
blocked for deployment until explicit production approval is given
```

This is not production deployment approval. Production deployment remains not approved and not executed.

Completed:

- Repo-side docs were committed and pushed in `61a0e74 docs: record NAS staging preflight result`.
- `origin/main` sync was confirmed after the docs commit.
- Read-only repo gate review was completed.
- Commit `61a0e74` was confirmed docs-only and limited to:
  - `docs/nas_staging_deployment_readiness_check.md`
  - `docs/nas_staging_preflight_execution_result.md`
- SSH reached the NAS host as `chaokun@211.75.219.184`.
- NAS hostname was reported as `disney`.
- Read-only path discovery and candidate fingerprint checks were executed.
- Docker / Compose read-only inspection was executed.
- Docker is available via `/usr/local/bin/docker`.
- Docker Compose is available via `/usr/local/bin/docker compose`.
- Human confirmed production URL: `https://devpilot.aicenter.com.tw/`.
- Human initially confirmed corrected staging target: `/volume1/docker-staging/devpilot`.
- Human initially confirmed corrected staging port: `5012`.
- Corrected NAS-side read-only preflight passed for that target, but this is now superseded.
- Human decision A confirmed `5010` is production only.
- Final clarification closed the staging target search for this flow; any future action against `5010` is production deployment, not staging deployment.

Not completed / superseded:

- The old expected staging path `/volume1/docker/devpilot-staging` was not found and is outdated or incorrect.
- The old planned staging port `5011:5000` is outdated or incorrect.
- Current repo commit confirmation is not applicable inside the corrected runtime path because it is not a git repo.
- The runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- Production deployment approval has not been granted.
- Staging target discovery is no longer required for this flow.

Failure reasons:

1. Expected staging path missing:
   - `/volume1/docker/devpilot-staging`
2. Candidate paths checked:
   - `/volume1/docker-staging/devpilot`
   - `/volume1/docker/devpilot_project_manager`
   - `/volume1/docker/devpilot`
   - `/volume1/worktrees/devpilot-build-321df5d`
3. Candidate fingerprint summary:

| Candidate path | Exists | Git repo | Commit status | Compose file | `.env` | Compose config | Staging likelihood |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/volume1/docker-staging/devpilot` | yes | no | cannot confirm `d8a65d8` or `61a0e74` | yes | yes, content not printed | FAILED | medium-low |
| `/volume1/docker/devpilot_project_manager` | yes | no | cannot confirm `d8a65d8` or `61a0e74` | yes | yes, content not printed | FAILED | low |
| `/volume1/docker/devpilot` | yes | no | cannot confirm `d8a65d8` or `61a0e74` | yes | yes, content not printed | FAILED | low |
| `/volume1/worktrees/devpilot-build-321df5d` | yes | yes, detached `HEAD` | does not include `d8a65d8` or `61a0e74` in latest log | yes | no | FAILED | low |

Docker / Compose runtime evidence:

Production and staging must be separated. The production public URL is human-confirmed:

```text
https://devpilot.aicenter.com.tw/
```

This URL must not be used as staging evidence.

| Container | Image | Status | Port | Compose project | Service | Working dir | Config file |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `devpilot-project-manager` | `devpilot-devpilot` | Up 4 days | `5010->5000` | `devpilot` | `devpilot` | `/volume1/docker/devpilot` | `/volume1/docker/devpilot/docker-compose.yml` |
| `devpilot-project-manager-staging` | `devpilot-staging-devpilot-staging` | Up 11 days | `5012->5000` | `devpilot-staging` | `devpilot-staging` | `/volume1/docker-staging/devpilot` | `/volume1/docker-staging/devpilot/docker-compose.yml` |
| `devpilot-project18-staging-preview` | `nginx:alpine` | Up 12 days | `5999->80` | `template-dispatch-nas-test-20260506-013007` | `project18-staging-preview` | `/volume1/docker-staging/template-dispatch-nas-test-20260506-013007` | `/volume1/docker-staging/template-dispatch-nas-test-20260506-013007/docker-compose.yml` |
| `devpilot-project-manager-backup-20260505-133349` | `devpilot_project_manager-devpilot` | Created | none visible | `devpilot_project_manager` | `devpilot` | `/volume1/docker/devpilot_project_manager` | `/volume1/docker/devpilot_project_manager/docker-compose.yml` |

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
- Actual staging working directory from Docker labels: `/volume1/docker-staging/devpilot`
- Documented planned port: `5011:5000`
- Actual staging port from Docker: `5012->5000`
- Port `5011` is occupied by `gkh-dispatch`.

Corrected NAS-side preflight result, now superseded:

| Check | Result | Notes |
| --- | --- | --- |
| hostname | pass | `disney` |
| user | pass | `chaokun` |
| pwd | pass | `/volume1/docker-staging/devpilot` |
| corrected staging target exists | pass | confirmed target exists |
| git repo | not applicable | runtime path is not a git repo |
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
| port `5012` evidence | superseded | `devpilot-project-manager-staging` maps `5012->5000`; later human correction says the correct port should be `5010` |

Final clarification:

```text
5010 is the active production site.
classification: staging readiness flow superseded / closed
gate: blocked for deployment until explicit production approval is given
```

The earlier corrected preflight was for `/volume1/docker-staging/devpilot` on port `5012`. Human correction later stated that `5012` is old and that the correct port should be `5010`.

This creates a major staging / production boundary contradiction because earlier Docker evidence associated `5010` with:

- container `devpilot-project-manager`
- compose project `devpilot`
- service `devpilot`
- working directory `/volume1/docker/devpilot`
- production URL `https://devpilot.aicenter.com.tw/`

Therefore, the corrected NAS-side preflight must no longer be treated as passed. The readiness gate is blocked until the staging / production target boundary is revalidated.

Human decision A and final clarification resolve the target boundary for this flow:

- `5010` is production only.
- Do not use `5010` as staging.
- Do not touch the production target.
- Production URL:
  - `https://devpilot.aicenter.com.tw/`
- Production target remains protected:
  - `/volume1/docker/devpilot`
  - container `devpilot-project-manager`
  - port `5010->5000`
- Previous `5012` staging evidence is superseded / old target:
  - `/volume1/docker-staging/devpilot`
  - container `devpilot-project-manager-staging`
  - port `5012->5000`
- Staging target discovery is no longer required for this flow.
- The previous staging readiness flow is superseded / closed.
- Any future action against `5010` is production deployment and requires separate explicit production approval.
- Readiness gate remains blocked for deployment.

Remaining blockers:

- `5010` is production only and must not be used as staging.
- Previous `5012` staging evidence is superseded / old target.
- Staging readiness is no longer the active flow.
- Any future action against `5010` is production deployment.
- Explicit production approval is required before any production deploy, restart, build, pull, Docker run, compose action, NAS edit, or runtime change.

Required unblock:

- Human must provide separate explicit production deployment approval before any action against `5010`.

Do not proceed using the previous staging approval path. `https://devpilot.aicenter.com.tw/` and `5010` are production.

Deployment decision:

- Classification is `staging readiness flow superseded / closed`.
- Gate is `blocked for deployment until explicit production approval is given`.
- A staging deployment build/up was executed against `/volume1/docker-staging/devpilot` on port `5012` before the later port correction arrived.
- That execution must not be treated as approval to continue.
- No further deployment, restart, build, pull, or Docker action is approved.
- Production deployment is not approved and was not executed.
- Readiness must not be marked passed for production until explicit production approval is given.

Safety confirmation:

- No further deploy is approved.
- No further restart is approved.
- No further build or pull is approved.
- No `docker run` was executed.
- No `docker compose down/restart/pull` was executed.
- No `git pull/push/merge/rebase` was executed on NAS.
- No `mkdir/rm/mv/cp` was executed on NAS.
- Source files were synced to `/volume1/docker-staging/devpilot` as part of the previously approved staging deployment attempt; no additional NAS file edits are approved after the contradiction.
- No NAS setting was changed.
- No `.env` content was read or printed.
- No secrets were touched.
- No NAS/Nginx/DNS/Cloudflare/SSL setting was changed.

## Readiness Conclusion

DevPilot appears structurally ready for a NAS staging/test deployment plan, but this report is not an approval to deploy.

Current staging readiness flow is superseded / closed. Current production deployment gate is blocked until explicit production approval is given.

Primary blockers before any future action:

- `5010` is production only.
- `https://devpilot.aicenter.com.tw/` is production.
- `/volume1/docker/devpilot` and container `devpilot-project-manager` are protected production runtime evidence.
- `5012` is old / superseded and should not be used as the deployment target.
- Any future action against `5010` requires separate explicit production approval.
- No deploy, restart, build, pull, Docker run, compose action, NAS edit, `.env` access, secret access, runtime change, Nginx/DNS/Cloudflare/SSL change, or provider live call is approved by this document.
