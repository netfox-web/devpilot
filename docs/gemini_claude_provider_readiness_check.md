# Gemini and Claude Provider Readiness Check

Date: 2026-05-15
Status: implementation readiness check

## Purpose

This checklist defines how to decide whether Gemini and Claude are ready to be enabled in DevPilot provider-governed workflows.

It is intentionally a readiness check, not an activation step. Passing this checklist does not deploy code, call providers, expose keys, enable customer traffic, or change production settings.

## Scope

Providers covered:

- Gemini
- Claude

Related DevPilot surfaces:

- `/admin/ai-provider-secrets`
- `/admin/ai-providers`
- `/admin/external-ai-policies`
- `/api/external/ai/generate`
- External AI usage and audit records

## Readiness States

Use one of these states when recording provider readiness:

| State | Meaning |
| --- | --- |
| `not_configured` | No usable provider credential is configured in runtime or managed secret storage. |
| `configured_not_verified` | A credential appears configured, but no approved live provider check has been run. |
| `policy_ready` | Source policy, model allowlist, budget limits, and audit expectations are configured. |
| `verified_with_mock` | DevPilot behavior is covered with mocked provider calls only. |
| `verified_live` | A separately approved live provider check has passed. |
| `blocked` | A missing credential, policy mismatch, budget issue, network issue, or safety concern blocks enablement. |

Default state should be `not_configured` or `configured_not_verified`.

## Gemini Readiness Checklist

Credential visibility:

- Runtime inspection recognizes `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
- Admin UI shows only masked key metadata.
- Raw key value is not printed in UI, logs, API responses, exports, or test output.
- Missing key state is handled without app errors.

Policy:

- Gemini is present only in approved source policies.
- Gemini model IDs are allowed only when `gemini` is an allowed provider.
- Token, request, budget, streaming, tool-use, and storage limits are explicit.
- Defaults fail closed when source policy is missing or disabled.

Provider behavior:

- Mocked Gemini success path is covered before any live check.
- Mocked Gemini failure path records a safe structured error.
- Idempotent replay does not duplicate a completed provider call.
- Usage logging records provider, model, status, source system, and request metadata without secrets.

Enablement gate:

- Live Gemini checks require a separate explicit approval.
- Live checks must use a low-risk prompt and a low-cost model.
- Live checks must confirm no task, project, approval, deploy, DNS, SSL, Nginx, Cloudflare, R2, or infrastructure mutation occurred.

## Claude Readiness Checklist

Credential visibility:

- Runtime inspection recognizes `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`.
- Admin UI shows only masked key metadata.
- Raw key value is not printed in UI, logs, API responses, exports, or test output.
- Missing key state is handled without app errors.

Policy:

- Claude is present only in approved source policies.
- Claude model IDs are allowed only when `claude` is an allowed provider.
- Token, request, budget, streaming, tool-use, and storage limits are explicit.
- Defaults fail closed when source policy is missing or disabled.

Provider behavior:

- Mocked Claude success path is covered before any live check.
- Mocked Claude failure path records a safe structured error.
- Idempotent replay does not duplicate a completed provider call.
- Usage logging records provider, model, status, source system, and request metadata without secrets.
- External AI Generate supports `provider: "claude"` with `model: "claude-3-5-haiku"` as a mocked/tested gateway path only.
- The Claude External AI Generate function must remain non-live until a later explicit live-provider phase.

Enablement gate:

- Live Claude checks require a separate explicit approval.
- Live checks must use a low-risk prompt and a low-cost model.
- Live checks must confirm no task, project, approval, deploy, DNS, SSL, Nginx, Cloudflare, R2, or infrastructure mutation occurred.

## Shared Verification Commands

For docs-only updates to this checklist:

```powershell
git diff --check
git status -sb
```

For code changes that affect provider policy, provider routing, usage logging, or admin provider pages, run the relevant unit tests and record exact commands in the handoff status.

## Safety Boundaries

- Do not deploy.
- Do not modify `.env` files.
- Do not print or copy raw provider keys.
- Do not call Gemini or Claude unless a later phase explicitly approves a live check.
- Do not enable provider access for external systems without source policy approval.
- Do not create worker execution, task mutation, project mutation, approval mutation, or infrastructure mutation as part of readiness documentation.

## Handoff Note

When this checklist is used, update `docs/ai_coding_agent_handoff_status.md` with:

- Provider checked.
- Readiness state.
- Files reviewed.
- Files changed.
- Verification commands and results.
- Confirmation that no secrets, runtime code, deployment, or provider live call occurred unless separately approved.
