# NAS Staging Deployment Readiness Check

Date: 2026-05-18
Status: readiness report, docs-only, no deployment

## 1. Current Repo Status

Current local check:

```text
git status -sb: ## main...origin/main
```

Conclusion:

- Local `main` is aligned with `origin/main`.
- This report is docs-only.
- No deployment, restart, NAS setting change, production change, DNS/Cloudflare/Nginx/SSL write, `.env` edit, or secret access was performed.

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

Recommended staging port:

```text
5011:5000
```

Final staging port must be chosen by the operator to avoid conflicting with production or existing DevPilot containers.

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

## 5. NAS Staging Topology Proposal

### App Path

Option A, Docker staging:

```text
/volume1/docker/devpilot-staging
```

Option B, venv staging:

```text
/volume1/apps/devpilot-staging
```

### Venv Path

If using venv staging:

```text
/volume1/apps/devpilot-staging/.venv
```

### Service Command

Docker proposal:

```bash
docker compose up -d --build
```

Venv proposal:

```bash
cd /volume1/apps/devpilot-staging
. .venv/bin/activate
HOST=0.0.0.0 PORT=5011 FLASK_DEBUG=0 python app.py
```

No service command was run during this readiness check.

### Reverse Proxy Pending

Reverse proxy is pending.

Do not write Nginx, Synology reverse proxy, or Cloudflare Tunnel config until a separate approved staging deployment phase.

### SSL Pending

SSL is pending.

Do not request certificates, change SSL mode, change Nginx SSL config, or change Cloudflare SSL settings during readiness review.

## 6. Preflight Commands

Run these on NAS staging only after an explicit staging preparation step.

Repository and files:

```bash
git status -sb
git log --oneline -5
test -f app.py
test -f requirements.txt
test -f Dockerfile
test -f docker-compose.nas.example.yml
```

Python / dependency preflight:

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

Docker preflight, if Docker is used:

```bash
docker --version
docker compose version
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
docker compose down
git checkout <previous_staging_commit>
docker compose up -d --build
```

For venv staging:

```bash
git checkout <previous_staging_commit>
. .venv/bin/activate
python -m pip install -r requirements.txt
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
- Python 3.12 or Docker build path is available.
- `requirements.txt` installs successfully.
- `python -m py_compile app.py` passes.
- Staging `.env` exists on NAS and contains only staging-safe values.
- `data/`, `uploads/`, and `logs/` staging directories exist.
- Staging port is selected and not conflicting with production.
- Reverse proxy and SSL are explicitly deferred or separately approved.
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

## Readiness Conclusion

DevPilot appears structurally ready for a NAS staging/test deployment plan, but this report is not an approval to deploy.

Current readiness is conditional go for planning and preflight only.

Primary blockers before actual staging deployment:

- Choose Docker versus venv topology.
- Choose staging port and app path.
- Prepare staging-only `.env` without exposing values.
- Confirm persistent storage and backup/rollback plan.
- Decide whether reverse proxy and SSL are deferred or handled in a separate approved phase.
