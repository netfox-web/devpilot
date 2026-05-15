# Managed GitHub API Status Check Verification

This note records the local verification and push confirmation for the managed
GitHub API key resolver and safe GitHub status-check endpoint.

Final status:

```text
MANAGED_GITHUB_API_STATUS_CHECK_VERIFIED
```

## Commit

- Repository: `netfox-web/devpilot`
- Commit: `1d7eb1e feat: add managed GitHub API status check`
- Local `main` matched `origin/main` after push.
- Remote `main` latest commit was confirmed as `1d7eb1e`.
- GitHub connector `fetch_commit` verification succeeded.

## Objective

Allow DevPilot to use a managed GitHub API key from the existing `/api-keys`
system for server-side GitHub status checks, without exposing the raw token to
the browser, API response, logs, audit metadata, or documentation.

## Feature Scope

Implemented server-side GitHub status-check support using the existing managed
API key center.

Functions and endpoint:

- `get_active_github_api_token()`
- `redact_github_response_text(text)`
- `github_request(...)`
- `record_github_status_check_usage(...)`
- `GET /api/admin/github/status`

The status endpoint is protected with:

```text
@require_api_roles("owner", "admin")
```

## Managed Key Behavior

- Uses the existing managed `/api-keys` table.
- Selects rows with `provider=github` and `status=active`.
- Prefers rows with `environment=production`.
- Decrypts the managed encrypted value only inside server-side helper code.
- Returns safe metadata only:
  - `name`
  - `environment`
  - `masked`
  - `status`
- Returns `api_key_id` internally so the status endpoint can record safe audit
  usage.
- Does not return raw token values.
- Does not write raw token values to logs or responses.
- Records safe `api_key_audit` action `status_check` without storing secrets.

Failure modes are explicit and secret-free:

- `github_token_not_configured`
- `github_token_decrypt_failed`
- `github_token_empty`
- `github_path_must_start_with_slash`

## Status Endpoint Behavior

`GET /api/admin/github/status` performs a safe GitHub status check:

- Calls `GET /user`.
- Calls `GET /rate_limit`.
- Returns safe API key metadata.
- Returns GitHub account `login` and `id`.
- Returns rate limit `limit`, `remaining`, and `reset`.
- Redacts GitHub API errors before returning them.

Successful response shape:

```json
{
  "ok": true,
  "api_key": {
    "name": "GitHub Production",
    "environment": "production",
    "masked": "ghp****safe",
    "status": "active"
  },
  "github": {
    "login": "netfox-web",
    "id": 12345
  },
  "rate_limit": {
    "limit": 5000,
    "remaining": 4999,
    "reset": 1900000000
  }
}
```

The response intentionally excludes:

- raw token
- `Authorization` header
- `Bearer` token
- encrypted value
- key hash / fingerprint internals

## Local Verification

Commands run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_github_admin_status.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m py_compile app.py
git diff --check
```

Results:

- Focused GitHub status tests: `6 passed`.
- Full pytest suite: `114 passed, 28 subtests passed`.
- `app.py` compile: passed.
- `git diff --check`: passed with CRLF warning only.

## Test Coverage

Focused tests verified:

- Missing managed GitHub key returns `github_token_not_configured`.
- Successful resolver result includes safe metadata and `api_key_id`.
- `github_request(...)` rejects paths that do not start with `/`.
- Status endpoint returns safe metadata, GitHub identity, and rate limit data.
- Status endpoint passes `api_key_id` into safe audit usage recording.
- GitHub HTTP errors are redacted before response.
- Bearer token and GitHub token-like strings are not exposed.

## Security Verification

- No raw GitHub token output.
- No `Authorization` header output.
- No `Bearer` token output.
- No provider secret output.
- No `.env` changes.
- No npm commands.
- No provider live call was required for tests; GitHub request behavior was mocked.
- Redaction tests confirmed token-like strings are removed from returned error text.

## Non-Goals

This slice did not add:

- GitHub repository mutation.
- GitHub write operations.
- GitHub webhook handling.
- GitHub OAuth flow.
- Token creation or rotation UI.
- Any new secret storage table.
- Any migration.
- Any deployment or infrastructure action.

## Safety Confirmation

This note is documentation-only. It records the managed GitHub API status check
verification and does not introduce app behavior, deployment, restart, rebuild,
migration, infrastructure change, DNS/SSL/Nginx/Cloudflare/R2 change, provider
call, worker/task execution, project/task/phase/approval mutation, or secret
output.
