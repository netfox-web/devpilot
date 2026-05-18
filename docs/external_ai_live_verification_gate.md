# External AI Live Verification Gate

Date: 2026-05-18
Audience: product owner, engineering owner, operations owner, security reviewer
Status: approval gate draft, docs-only

## Purpose

Define the explicit approval gate required before any live Gemini or Claude verification call is allowed from DevPilot.

This document does not approve live verification by itself. It describes prerequisites, constraints, abort conditions, logging expectations, and non-goals for a future separately approved one-call verification phase.

## Live Verification Prerequisites

Before any live provider call is allowed, all prerequisites must be satisfied:

- Product owner approval is recorded.
- Engineering owner approval is recorded.
- Operations owner approval is recorded.
- Security/secrets reviewer approval is recorded.
- The exact provider, model, prompt, source system, and route are documented.
- The target environment is confirmed.
- The relevant provider credential is already present in runtime configuration.
- No raw key is copied into docs, chat, logs, tests, frontend output, or Git.
- The provider readiness dashboard/API confirms `live_call_enabled: false` before the test phase begins.
- Mock verification for the same provider path has passed.
- The runbook confirms no deploy, DNS, SSL, Nginx, Cloudflare, R2, registrar, or production setting changes are included.
- A rollback/abort owner is named, even though the expected verification is one read-only provider request.

## Gemini One-Call Verification Plan

Goal:

- Verify that DevPilot can execute exactly one low-risk Gemini request through the approved gateway path after explicit approval.

Draft request constraints:

- Provider: `gemini`
- Model: lowest-cost approved Gemini text model, currently expected `gemini-1.5-flash`
- Prompt: a harmless fixed prompt such as `Return exactly OK.`
- Max output: minimal
- Temperature: low
- Request count: exactly `1`
- Tool calls: disabled
- Streaming: disabled
- Storage: prompt/response storage disabled unless separately approved

Expected success result:

- One provider call attempted.
- Response is short and non-sensitive.
- Usage metadata is recorded without secrets.
- No task, project, approval, deployment, DNS, SSL, Nginx, Cloudflare, R2, or infrastructure mutation occurs.

Expected failure result:

- Safe structured error is recorded.
- No retry loop starts automatically.
- No fallback provider is called automatically.
- No raw provider error containing secrets is displayed.

## Claude One-Call Verification Plan

Goal:

- Verify that DevPilot can execute exactly one low-risk Claude request through a future approved live Claude gateway path.

Current boundary:

- Claude External AI Generate support is currently mock/test oriented.
- The live Claude call path must remain disabled until a separate implementation and approval phase explicitly enables it.

Draft request constraints for a future live phase:

- Provider: `claude`
- Model: lowest-cost approved Claude text model, currently expected `claude-3-5-haiku` or a later approved replacement
- Prompt: a harmless fixed prompt such as `Return exactly OK.`
- Max output: minimal
- Temperature: low
- Request count: exactly `1`
- Tool calls: disabled
- Streaming: disabled
- Storage: prompt/response storage disabled unless separately approved

Expected success result:

- One provider call attempted.
- Response is short and non-sensitive.
- Usage metadata is recorded without secrets.
- No task, project, approval, deployment, DNS, SSL, Nginx, Cloudflare, R2, or infrastructure mutation occurs.

Expected failure result:

- Safe structured error is recorded.
- No retry loop starts automatically.
- Gemini is not called as fallback unless separately approved.
- No raw provider error containing secrets is displayed.

## Required Approvals

Minimum approvals before live verification:

| Approval | Required owner | Required content |
| --- | --- | --- |
| Product approval | Product owner | Why live verification is needed and which provider is being tested. |
| Engineering approval | Engineering owner | Exact code path, endpoint, model, and expected payload. |
| Operations approval | Operations owner | Target environment, time window, abort owner, and no-deploy confirmation. |
| Security approval | Security/secrets reviewer | Secret handling, logging boundary, and redaction confirmation. |

Approval record should include:

- provider
- model
- prompt
- route
- environment
- expected request count
- budget cap
- token cap
- storage policy
- abort conditions
- responsible operator

## Budget, Token, and Request Constraints

Default constraints:

- Provider calls: maximum `1` per approved verification ticket.
- Prompt tokens: minimum practical prompt only.
- Output tokens: cap at a small value, such as `16` or nearest provider-supported equivalent.
- Budget: fixed small cap approved before execution.
- Retries: disabled unless a separate approval explicitly allows one retry.
- Fallback providers: disabled.
- Parallel calls: disabled.
- Streaming: disabled.
- Tool calling: disabled.
- Long context prompts: forbidden.
- User/customer data: forbidden.

## Safety Boundaries

Live verification must not:

- deploy code
- modify `.env`
- read, print, copy, hash, or expose raw secrets
- expose `Authorization`, `Bearer`, provider key, or `key_hash`
- change production settings
- create or modify DNS records
- change Cloudflare settings
- change SSL mode or certificates
- write Nginx config
- change registrar nameservers
- upload or mutate R2 objects
- mutate projects, tasks, phases, handoffs, approvals, or deployment jobs
- trigger worker execution
- call more than the approved provider/model
- use real customer data

## Abort Conditions

Abort before the call if:

- Any required approval is missing.
- The current branch/worktree is unexpected for the verification run.
- The exact provider/model/prompt is not documented.
- Credential status is unknown.
- The code path could trigger deploy, DNS, infrastructure, task, project, approval, or worker mutation.
- Logging redaction cannot be confirmed.
- Budget or token caps are not configured.
- The provider call count cannot be constrained to exactly one.

Abort during/after the call if:

- More than one provider request is attempted.
- A retry loop starts unexpectedly.
- A fallback provider is invoked.
- Any raw secret or auth header appears in logs or output.
- Any mutation outside usage/audit logging is observed.
- The response contains unexpected sensitive content.
- Network/provider errors include unsafe raw payloads.

## Logging Expectations

Allowed log fields:

- provider id
- model id
- timestamp
- request id
- source system
- status
- safe error code
- token usage, if returned
- estimated cost, if available
- duration
- `provider_calls_executed: true`
- `live_verified: true|false`

Forbidden log fields:

- raw provider key
- `Authorization`
- `Bearer`
- `key_hash`
- full request headers
- full raw provider response if it may contain sensitive metadata
- customer/user confidential data
- `.env` values

The verification record should explicitly state:

- whether exactly one provider call was attempted
- whether the call succeeded
- whether live verification passed
- whether any mutation occurred
- whether any secret was exposed
- whether abort conditions were triggered

## Explicit Non-Goals

This gate does not:

- approve live provider calls
- implement live Claude support
- change Gemini or Claude provider code
- create a dashboard
- deploy anything
- change `.env`
- touch secrets
- enable production traffic
- grant external systems provider access
- create DNS, redirects, SSL, Nginx, Cloudflare, R2, or registrar changes
- create worker execution
- mutate projects, tasks, phases, handoffs, approvals, or deployment jobs
- define long-running reliability testing
- define load testing
- define fallback routing
- define customer data processing

Any live verification must be requested as a separate explicit phase after this gate is reviewed and approved.
