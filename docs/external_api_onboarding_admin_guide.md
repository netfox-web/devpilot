# External API Onboarding Admin Guide

This guide is for onboarding an external system to DevPilot without sharing raw provider keys.

## Step 1: Generate External API Key

Open `Admin -> External API Keys`, enter the external `source_system` and an operator-friendly label, then generate a managed key.

The raw key is shown only once. DevPilot stores only safe metadata: `source_system`, `key_prefix`, `key_hash`, label, timestamps, and revoke status.

## Step 2: Copy Raw Key Once

Copy the generated raw key immediately and place it in the external system's secret manager.

Do not paste the raw key into tickets, docs, screenshots, logs, source code, or policy records.

## Step 3: Select Source Systems

Open `Admin -> External AI Policies` and use the searchable source picker to find one or more active managed source systems.

The picker shows safe metadata only: `source_system`, label, key prefix, and active status. It does not show raw keys or key hashes. Duplicate active keys for the same `source_system` are shown once.

Policies reference only `source_system`. They do not store key ids, raw API keys, or key hashes. If a source does not have a managed key yet, use the manual `source_system` fallback only when intentionally preparing a policy before key generation.

## Step 4: Apply Permission Profile

Choose a permission profile and apply it to the selected source systems. Built-in profiles include:

- `basic-text`: OpenAI `gpt-4.1-mini` for summary, rewrite, and classification with 1000 daily requests.
- `text-multi-provider`: OpenAI, Gemini, and Claude small approved models for summary, classification, rewrite, extraction, and planning.
- `image-basic`: OpenAI, Replicate, and fal image generation with 300 daily requests.
- `image-pro`: higher-volume image generation, editing, variation, prompt rewrite, ad creative, and product image work with 1000 daily requests.
- `video-review-only`: disabled-by-default video governance placeholder. Provider calls remain disabled until a later gateway phase.
- `internal-advanced-draft`: disabled-by-default internal/testing draft profile.

Applying a profile creates or updates the policy for each selected `source_system`; it does not create duplicate policies for the same source.

## Step 5: Manage Permission Profiles

Open `Admin -> External AI Permission Profiles` to create, update, enable, or disable reusable profiles.

Use profile management when a customer or product type needs a repeatable permission group. The page uses controlled provider, model, and capability selectors and rejects unknown values or model/provider mismatches.

Disabled profiles are not available for normal batch apply. Keep high-risk profiles disabled until they have an explicit approval and budget owner.

## Step 6: Advanced Adjustments

Use the advanced manual policy section only when a profile is not enough. The controlled selectors still enforce known providers, model IDs, and capabilities. Keep defaults conservative:

- disabled until intentionally enabled
- streaming disabled
- tool calling disabled
- prompt storage disabled
- response storage disabled
- conservative token, request, and budget limits

Provider/model/capability policy controls future External AI Gateway behavior. It does not call providers by itself.

## Step 7: Review Policy Warnings

External AI Policies and Permission Profiles show advisory warnings for broad or risky settings, including:

- tool calling enabled
- streaming enabled
- full prompt or response storage enabled
- many or nearly all capabilities selected
- video generation or image-to-video capability enabled
- provider selected without a matching model
- high daily request, token, or monthly budget limits

Warnings do not block saving yet, but they should trigger human review before production use.

Do not enable tool calling or full prompt/response storage by default. Tool calling expands execution risk, and full prompt/response storage may create data retention obligations.

Video and image-to-video should be budget-gated because provider cost and generation latency can be materially higher than text requests.

## Step 8: Download Integration Doc

Return to `Admin -> External API Keys` and download the integration document for the key record.

The generated document includes the `source_system`, label, key prefix, endpoint examples, idempotency guidance, and safe code samples. It includes `DEVPILOT_API_KEY=<paste-the-key-shown-once>` as a placeholder and does not include the raw key or key hash.

Send the downloaded document plus the raw key through a secure secret-sharing channel.

## Step 9: Revoke If Needed

Use the revoke action on `Admin -> External API Keys` when a key is no longer needed or may be exposed.

Revoking a key does not remove policy history. If the external system should lose future AI permissions too, disable its External AI Policy separately.

## Key Types

| Item | Purpose | Secret handling |
| --- | --- | --- |
| External system key | Identifies `source_system` and allows approved DevPilot external APIs | Issued by DevPilot, revocable in DevPilot, stored as hash |
| Provider key | Used only by DevPilot internally for OpenAI, Gemini, Claude, Replicate, fal, Runway, Kling, or other providers | Never shared with external systems |
| Source AI policy | Controls provider/model/capability/budget for a `source_system` | Stores policy only, not keys |

External systems receive only DevPilot external API keys. They must never receive `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY`, Replicate keys, fal keys, Runway keys, Kling keys, or other raw provider credentials.
