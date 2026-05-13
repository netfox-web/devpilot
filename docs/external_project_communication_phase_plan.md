# External Project Communication Phase Plan

## Objective

DevPilot should become the central project registry, status hub, and communication router for AI-related projects.

External AI systems should be able to report what they are doing, discover approved shared context, and coordinate with related projects through DevPilot instead of rebuilding separate status, event, handoff, and communication logic in every project.

## Why Centralize Project Communication

- Avoid each project rebuilding status, event, handoff, and coordination logic.
- DevPilot already knows `source_system`, project metadata, domains, repository details, deployment target, runtime paths, containers, and project events.
- Cross-project coordination becomes easier because DevPilot can map project identity, status, dependencies, and ownership in one place.
- Permission and audit boundaries are safer when shared visibility flows through DevPilot instead of direct project-to-project secrets.
- External systems can use one common integration pattern: DevPilot-issued external API keys, source policies, registry records, events, and future communication APIs.

## Proposed Capabilities

- Project relationship map for owned, dependent, upstream, downstream, and integration relationships.
- Project dependencies that show which projects rely on other services, domains, APIs, data feeds, or deployment targets.
- Project-to-project messages for structured coordination without sharing raw project secrets.
- Project event subscriptions so one project can watch another project's approved status events.
- Cross-project handoff requests for human or AI review when work needs to move between systems.
- Shared context lookup for approved metadata such as status, app URL, repository, domain readiness, and latest event summary.
- Admin review timeline that combines registry updates, events, messages, relationships, and handoffs.
- Communication audit log for every cross-project read, write, relationship change, and message.

## Proposed Future Endpoints

```http
POST /api/external/projects/<external_project_id>/messages
GET /api/external/projects/<external_project_id>/messages
POST /api/external/projects/<external_project_id>/relationships
GET /api/external/projects/<external_project_id>/relationships
GET /api/external/projects/<external_project_id>/context
POST /api/external/projects/<external_project_id>/subscriptions
```

Endpoint behavior should remain metadata-first and policy-gated. These endpoints should not execute work directly.

## Permission Model

- Default source isolation remains the baseline: a `source_system` can see only its own projects unless a relationship or admin policy allows more.
- Cross-project visibility requires an explicit relationship before another source can read shared project context.
- Shared visibility should be admin-approved for production relationships.
- External systems must never share raw DevPilot external API keys with each other.
- Provider keys must never be exposed to external systems.
- Deploy, DNS, provider, and worker execution are disabled by default and must not be triggered by communication APIs.
- Shared context should be allowlisted by field, for example status, app URL, latest event summary, domain status, or dependency state.

## Data Model Direction

Prefer file-backed stores first, matching the External Project Registry approach and avoiding a DB migration in the initial slices:

- `data/external_project_relationships.json`
- `data/external_project_messages.json`
- `data/external_project_subscriptions.json`

Relationship records should include source project, target project, relationship type, visibility level, approval status, created/updated timestamps, and notes.

Message records should include sender source/project, recipient source/project, message type, subject, body or safe payload summary, status, request/idempotency IDs, and timestamps.

Subscription records should include subscriber project, target project, event filters, delivery mode, enabled state, and audit timestamps. Webhook delivery should remain disabled by default until a later explicit phase.

## Safety Boundaries

Communication APIs must not:

- Trigger deployments.
- Change DNS, Cloudflare, SSL, Nginx, or redirects.
- Run workers.
- Call AI providers.
- Mutate unrelated project or task state.
- Create approvals automatically unless a later phase explicitly adds that behavior.
- Expose raw external API keys, provider keys, infrastructure secrets, or stored hashes.

## Rollout Slices

- Slice 4C: planning doc only.
- Slice 4D: read-only relationship registry.
- Slice 4E: project-to-project message API.
- Slice 4F: admin communication timeline.
- Slice 4G: event subscriptions / webhooks, disabled by default.
- Slice 4H: cross-project handoff workflow.
- Later: policy-gated automation after relationship, permission, budget, audit, and approval boundaries are proven.

## Tests Plan

- Source isolation by default.
- Relationship visibility only after approved relationship exists.
- Message create/read behavior.
- No external API key or provider key leakage.
- No infrastructure writes.
- No provider calls.
- No worker execution.
- Audit log created for cross-project communication.
- Invalid project/source rejected.
- Disabled or unapproved relationships cannot read shared context.
- Malformed relationship/message/subscription store files do not crash admin or API routes.

## Open Questions

- Should relationships require admin approval before any cross-project visibility?
- Which projects should communicate first?
- Should event subscriptions start as pull-only before adding webhooks?
- What data can be shared cross-project by default?
- Should DevPilot summarize project context for the AI Gateway later?
- Should message bodies be stored fully, summarized, or hashed by default?
- Should relationship changes create approval requests in a later phase?
