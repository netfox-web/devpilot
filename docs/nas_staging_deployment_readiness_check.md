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
- Docker / Compose read-only inspection later identified a running staging runtime:
  - container `devpilot-project-manager-staging`
  - compose project `devpilot-staging`
  - working directory `/volume1/docker-staging/devpilot`
  - port `5012->5000`
- No deployment, restart, Docker start/build command, reverse proxy change, SSL change, DNS/Cloudflare change, `.env` output, or secret output was performed.

## Deployment Readiness Gate Status

Current gate status:

```text
blocked: candidate runtime path identified, pending human confirmation
```

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

Not completed:

- The expected staging path `/volume1/docker/devpilot-staging` was not found.
- No candidate path confirmed the latest synced commit `d8a65d8`.
- No candidate path confirmed the previous docs commit `61a0e74`.
- The actual runtime path has not been confirmed by a human as the intended staging target.
- The runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- NAS staging readiness was not marked passed.

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

- Documented expected path: `/volume1/docker/devpilot-staging`
- Actual staging working directory from Docker labels: `/volume1/docker-staging/devpilot`
- Documented planned port: `5011:5000`
- Actual staging port from Docker: `5012->5000`
- Port `5011` is occupied by `gkh-dispatch`.

Remaining blockers:

- Expected path does not exist.
- No candidate confirms latest synced commit `d8a65d8`.
- No candidate confirms previous commit `61a0e74`.
- Documentation expected path and port do not match the actual Docker staging runtime.
- Runtime path appears to be a copied deployment rather than a confirmed synced git worktree.
- Correct staging target still requires human confirmation.

Required unblock:

- Human must decide one of:
  - confirm `/volume1/docker-staging/devpilot` and port `5012` as the real NAS staging target, then rerun read-only preflight using this corrected target,
  - update deployment docs from `/volume1/docker/devpilot-staging:5011` to `/volume1/docker-staging/devpilot:5012` if this is the intended staging environment,
  - provision the originally documented path `/volume1/docker/devpilot-staging` through an approved setup process,
  - stop deployment readiness until path/port ownership is resolved.

Deployment decision:

- Deployment is not approved.
- Deployment was not executed.
- Readiness must not be marked passed.
- Deployment must not proceed.

Safety confirmation:

- No deploy was executed.
- No restart was executed.
- No build or pull was executed.
- No `docker run` was executed.
- No `docker compose up/down/restart/build/pull` was executed.
- No `git pull/push/merge/rebase` was executed on NAS.
- No `mkdir/rm/mv/cp` was executed on NAS.
- No file edits were made on NAS.
- No NAS setting was changed.
- No `.env` content was read or printed.
- No secrets were touched.
- No NAS/Nginx/DNS/Cloudflare/SSL setting was changed.

## Readiness Conclusion

DevPilot appears structurally ready for a NAS staging/test deployment plan, but this report is not an approval to deploy.

Current readiness is conditional go for planning and preflight only.

Primary blockers before actual staging deployment:

- Verify `/volume1/docker/devpilot-staging` exists and contains the intended commit.
- Verify Docker Compose config maps `5011:5000`.
- Prepare staging-only `.env` without exposing values.
- Confirm persistent storage and backup/rollback plan.
- Confirm reverse proxy and SSL remain deferred for the first staging/test instance.
