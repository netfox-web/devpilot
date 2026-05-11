# Domain Pages Performance Release Note

## Scope

This note records the production verification for Domain Pages Performance Phase 1.

## Deploy Commit

- Commit: `321df5d`
- Full intent: improve read-only performance for `/domains`, `/domain-readiness`, and `/domain-action-plan`.

## Image Tags

- `devpilot-devpilot:321df5d`
- `devpilot-devpilot:latest`

## Rollback Image

- Image tag: `devpilot-devpilot:rollback-pre-321df5d-20260511200820`
- Saved image archive: `/volume1/docker/devpilot/backups/devpilot-image-rollback-pre-321df5d-20260511200820.tar`

## Verification Results

| Route | Result |
| --- | --- |
| `/domains` | `0.529662s` |
| `/domain-readiness?refresh=1` | `9.210411s` |
| `/domain-readiness` cached | `0.015045s` |
| `/domain-action-plan` | `0.063399s` |
| `/api/domains/<zone_id>/records` live | `0.751124s` |
| `/api/domains/<zone_id>/records` cached | `~0.007s` |

## Confirmed Behavior

- `/domains` lazy-loads DNS records instead of loading all zone records during first render.
- `records_deferred=true` was confirmed for 60 zones.
- The `View records` action uses the read-only endpoint `/api/domains/<zone_id>/records`.
- Domain readiness cache metadata is visible and uses TTL `60s`.
- `/domain-action-plan` reuses the domain readiness cache.

## Remaining Slow Path

- `/domain-readiness?refresh=1` live checks still take around `9s`.
- This is expected for Phase 1 because refresh mode performs read-only DNS, HTTP, HTTPS, TLS, and backend health probes.

## Explicit Non-Actions

- No Cloudflare write.
- No DNS write.
- No SSL write.
- No redirect write.
- No Nginx write.
- No `cf_batch.py` execution.
- No `cf_batch_devpilot_bridge.py` execution.
- No `--apply` or `--confirm-real-write`.
