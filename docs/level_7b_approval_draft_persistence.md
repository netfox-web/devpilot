# Level 7B Approval Draft Persistence

Date: 2026-05-18
Status: implemented draft persistence, no execution

## What Was Added

Level 7B adds persisted draft approval objects for high-risk action planning.

The feature allows an owner/admin to explicitly create a draft approval object from the approval preview shape. It saves the draft for later review, but it does not approve, reject, execute, or route the action into the existing `approval_requests` execution workflow.

## Routes

Admin UI:

```text
GET /admin/approval-objects
GET /admin/approval-objects/<approval_id>
```

Admin API:

```text
GET /api/admin/approval-objects
GET /api/admin/approval-objects/<approval_id>
POST /api/admin/approval-objects/draft
```

## Storage

Runtime storage path:

```text
data/approval_objects.json
```

The store contains draft approval objects only. The data file is runtime state and should not be committed to git.

Tests must use an isolated temporary path for this store.

## Draft-only Boundary

Created approval objects always keep:

```text
status: draft
execution_allowed: false
execution_mode: none
approval_object_created: true
execution_result: null
```

Draft creation appends a safe audit event:

```text
draft_created
```

The audit event records that no execution occurred.

## Not Implemented In Level 7B

Level 7B does not implement:

- approve endpoint
- reject endpoint
- execute endpoint
- rollback endpoint
- approval request workflow handoff
- execution adapters
- provider live calls
- DNS / Cloudflare / Nginx / SSL / R2 / deploy mutation
- worker execution
- project/task/phase/handoff mutation

## Safety Model

Draft creation rejects payloads containing sensitive markers such as:

- `Authorization`
- `Bearer`
- `key_hash`
- `.env`
- raw secret or token markers

Draft objects must not expose raw secrets in UI, API responses, logs, docs, or tests.

## Next Phases

### Level 7C - Approval Inbox

Add a dedicated review inbox for draft approval objects with filtering, stale snapshot warnings, and missing-role indicators.

### Level 7D - Approval Approve/Reject Workflow

Add explicit approve/reject actions with role checks, audit events, and no execution.

### Level 7E - Runner Low-risk Queue Consumption

Allow reviewed low-risk queue patches to be consumed by the scheduled runner under strict task boundaries.

### Level 8 - Limited Execution Adapters

Only after explicit approval, add narrowly scoped execution adapters. Live provider, DNS, Cloudflare, Nginx, SSL, R2, deploy, worker, and production actions require separate implementation phases.

## Non-Goals

This phase does not:

- approve drafts
- reject drafts
- execute drafts
- create `approval_requests`
- call Gemini or Claude
- write usage logs
- write generation results
- deploy
- mutate DNS, Cloudflare, Nginx, SSL, registrar, R2, workers, projects, tasks, phases, handoffs, or production settings
- change `.env`
- touch secrets
