# AI Handoff External API Release Note

## Scope

This note records production deployment and verification for AI-to-AI Manual Handoff Phase 3 Slice 2C: External API Contract + Auth Boundary.

Integration contract: `docs/ai_handoff_external_api_contract.md`

## Deploy Commit

- Commit: `a25f94c`
- Message: `feat: add external AI handoff API boundary`

## Production Result

- Production verification: `PASS`.
- Logs were clean with no verification tracebacks or application errors.
- Disposable verification records were cleaned up with leftovers `0`.

## Verified External API Behavior

| Area | Result |
| --- | --- |
| Missing external API key returns `403` | `PASS` |
| Wrong external API key returns `403` | `PASS` |
| Valid source/key returns `200` | `PASS` |
| `POST /api/external/tasks/<task_id>/handoffs` returns `201` | `PASS` |
| Repeated POST with same idempotency key returns existing handoff | `PASS` |
| `GET /api/external/ai-handoffs` | `PASS` |
| `GET /api/external/handoffs/<handoff_id>` | `PASS` |

External create produced a pending handoff with `conversation_ref = ai-task:<task_id>` and stored `source_system`, `external_ref`, `request_id`, `idempotency_key`, `actor_type`, and `actor_id` in `api_payload`.

Idempotency replay returned `200`, `idempotent_replay = true`, the same `handoff_id`, and did not create a duplicate.

## Source Isolation

- A source can only see its own records by default.
- A forced `source_system` query did not leak other sources.
- Detail lookup for another source returned `404`.
- With `DEVPILOT_EXTERNAL_API_ALLOW_ALL_SOURCES=1` and `include_all_sources=true`, both test sources were visible.

## Safety Verification

Confirmed unchanged:

- Task status.
- Project status.
- Phase status.
- Project next steps.
- Project progress.
- Approval count.

Confirmed not called:

- Provider path.
- Worker path.
- Legacy `save_handoff`.

External API remains create/read/audit only. No external accept, complete, or reject endpoints were added.

## Cleanup

Removed disposable production records:

- Project: `29`
- Phase: `48`
- Task: `8`
- Handoff logs: `92`, `93`

Cleanup result: `PASS`, leftovers `0`.

## Explicit Non-Actions

- No DB migration.
- No task/project mutation.
- No provider call.
- No worker execution.
- No approval request creation.
- No DNS, SSL, Nginx, Cloudflare, redirect, Docker config, or infrastructure change.
