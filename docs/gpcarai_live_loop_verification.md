# gpcarai Real External Project Live Loop Verification

## Summary

The first real external project live loop was completed for `gpcarai / 購好康派車系統`.

Final status:

```text
GPCARAI_REAL_EXTERNAL_PROJECT_LIVE_LOOP_VERIFIED
```

This verification proved the minimum external project loop:

```text
External Project -> DevPilot External API -> Project Registry -> Events -> Admin Visibility
```

## Project

- Source system: `gpcarai`
- External project ID: `gpcarai-prod`
- Project name: `購好康派車系統`
- Project status: `active`
- App URL: `https://go.carai.tw`
- Primary domain: `go.carai.tw`
- Runtime: `python/docker`
- Runtime path: `/volume1/docker/gkh-dispatch`
- Container name: `gkh-dispatch`
- Compose project: `gkh-dispatch`
- Service name: `gkh-dispatch`
- Host port: `5011`

## Register Result

Project registration was performed using the existing safely stored DevPilot config in `gkh-dispatch`.

Observed correction attempts:

- Initial custom POST attempt returned `403`.
- Register payload correction returned `400` because `host_port` needed to be a string.
- Event attempt before project creation returned `404`.

Final register path:

- Register succeeded with `201 created`.
- Follow-up register update succeeded with `200 updated`.
- Project name encoding was corrected to `購好康派車系統`.
- No duplicate project was created.

## Event Result

One healthcheck event was sent successfully.

- Event send succeeded with `201`.
- Event type: `healthcheck_ok`.
- Status: `success`.
- Message: `External project can reach DevPilot integration endpoint.`

No handoff was sent in this run.

## DevPilot Verification

DevPilot admin visibility was verified:

- `/admin/external-sources/gpcarai`: `200`, project and event visible.
- `/admin/external-integration-diagnostics?source_system=gpcarai`: `200`.
- `/admin/external-projects?source_system=gpcarai`: `200`.
- `/admin/external-projects/gpcarai/gpcarai-prod`: `200`.

Store verification:

- Registry store has one matching `gpcarai-prod` project.
- Events store has one matching `healthcheck_ok` event.

HTTP/error summary:

- Final register/event path succeeded.
- Correction attempts observed: `403`, `400`, `404`.
- No `401`, `422`, or `500` was observed.

## Security Verification

The live loop was verified to avoid secret exposure:

- No raw DevPilot API key was printed.
- No key hash was printed.
- No environment secret value was printed.
- No traceback or application error was observed in checked logs.

## Safety Confirmation

Only the expected external registry/event writes occurred.

No unsafe side effects were observed:

- No handoff sent.
- Provider call count: `0`.
- Worker/task execution call count: `0`.
- Cloudflare call count: `0`.
- Gemini/provider call count: `0`.
- Normal DevPilot project/task/phase/approval counts unchanged.
- No deploy/restart/rebuild.
- No migrations.
- No infrastructure changes.
- No DNS/SSL/Nginx changes.
- No Cloudflare/R2 calls.
- No provider calls.
- No workers.
- No approvals.
- No normal project/task/phase mutation.

## Logs

Checked logs showed:

- DevPilot: no traceback, exception, or error.
- `gkh-dispatch`: no traceback, exception, or error.
