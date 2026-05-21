# External AI Gateway Admin Guide

Date: 2026-05-21
Status: production gateway active for policy-gated MVP text models

## Purpose

DevPilot is becoming the unified key, provider, policy, and usage governance center for external AI integrations.

External systems should receive DevPilot external API keys only. They must never receive raw OpenAI, Gemini, Claude, or other provider credentials.

## Current State

Production-verified capabilities:

- External systems can create and read AI handoffs through DevPilot.
- External API keys can be generated and revoked in DevPilot admin UI.
- External handoff APIs cannot call providers, run workers, mutate tasks/projects, or create approval requests.

Current gateway status:

- `POST /api/external/ai/generate` is active for policy-gated text generation.
- Active Gateway Models are OpenAI `gpt-4.1-mini` / `gpt-4o-mini`, Gemini `gemini-2.5-flash`, and Claude `claude-haiku-4-5-20251001`.
- Candidate / Future Models shown in the policy UI are planning entries only and are not directly selectable for production source policies.
- Any new model must complete Gateway model onboarding before external projects may call it.

## Admin Surfaces

### External API Key Manager

Path:

```text
/admin/external-api-keys
```

Purpose:

- Identifies `source_system`.
- Authenticates external systems.
- Generates DevPilot external API keys.
- Revokes external API keys.
- Stores key hash and prefix only.
- Shows raw generated key only once.

### Provider Config Inspection

Path:

```text
/admin/ai-providers
```

Purpose:

- Shows whether provider credentials appear configured.
- Checks DevPilot managed encrypted AI keys first, then common env vars.
- Shows safe prefix only.
- Does not print full keys.
- Does not call OpenAI, Gemini, Claude, or any provider.
- Does not validate provider keys over the network.
- Does not create, reveal, or modify provider keys.

Checked env vars:

| Provider | Env vars |
| --- | --- |
| OpenAI | `OPENAI_API_KEY` |
| Gemini | `GEMINI_API_KEY`, `GOOGLE_API_KEY` |
| Claude | `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` |

Managed key mapping:

| Provider | Managed AI key provider |
| --- | --- |
| OpenAI | `openai` |
| Gemini | `google` |
| Claude | `anthropic` |

### Source AI Policy Manager

Path:

```text
/admin/external-ai-policies
```

Storage:

```text
data/external_ai_policies.json
```

Purpose:

- Defines what each `source_system` may use in the future gateway.
- Stores allowlists and limits.
- Defaults to safe/disabled.
- Does not call providers.
- Does not execute workers.
- Does not mutate projects or tasks.

Policy controls:

- Allowed providers.
- Allowed models.
- Allowed capabilities.
- Max tokens per request.
- Daily request limit.
- Daily token limit.
- Monthly budget.
- Streaming allowed or denied.
- Tool calling allowed or denied.
- Prompt/response storage policy.
- Enabled/disabled status.

Model selection boundary:

- The policy page is the External AI Gateway MVP allowlist editor, not a full provider model catalog.
- Active Gateway Models can be selected into a policy.
- Candidate / Future Models cannot be submitted as `allowed_models` until onboarding is complete.
- Onboarding gates: backend allowlist, adapter compatibility, tests/docs, NAS deployment approval, and one-provider-at-a-time live smoke approval.

## Key And Policy Layer Comparison

| Layer | What it does | Who receives it | Safety notes |
| --- | --- | --- | --- |
| External system key | Identifies `source_system`; can call allowed DevPilot external APIs; can be revoked in DevPilot. | External system. | Stored as hash in DevPilot when managed by the admin UI. |
| Provider key | Lets DevPilot call OpenAI, Gemini, Claude, or another provider. | DevPilot runtime only. | Must never be shared with external systems or returned in API responses. |
| Source AI policy | Controls provider/model/capability/budget for a `source_system`. | DevPilot admin/governance layer. | Defaults should be disabled and empty until explicitly configured. |

## External System Guidance

External systems should use these headers for DevPilot external APIs:

```text
X-DevPilot-Source-System
X-DevPilot-Api-Key
X-DevPilot-Request-Id
X-DevPilot-Idempotency-Key
```

External systems should not:

- Ask for raw OpenAI/Gemini/Claude keys.
- Store provider keys.
- Call provider APIs directly using DevPilot-owned credentials.
- Assume all models are available.
- Assume unlimited token or cost budget.
- Expect worker execution, project mutation, deployment, DNS, or infrastructure changes from gateway calls.

## Future Gateway Behavior

Future generate/chat endpoints should be:

- Policy-gated.
- Budget-limited.
- Audited.
- Source-isolated.
- Idempotency-aware.
- Non-mutating by default.

Expected first enabled endpoint:

```text
POST /api/external/ai/generate
```

Initial recommended scope:

- One provider.
- One model.
- Non-streaming.
- Strict source allowlist.
- No tool calling.
- No worker execution.
- No file writes.
- No project/task mutation.

## Safety Rules

- Provider keys must never be shared with external systems.
- Provider keys must never be printed in logs, UI, API responses, or exports.
- External systems receive DevPilot external API keys only.
- Source AI policies must fail closed.
- No provider calls are enabled until a separate implementation and production verification phase.
- No deploy, restart, migration, DNS, SSL, Nginx, Cloudflare, redirect, or infrastructure change is implied by this groundwork.
