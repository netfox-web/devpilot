# External AI Generate API Slice 5A Production Verification

## Summary

Phase 3 Slice 5A introduced the first minimal External AI Gateway provider-call path for DevPilot.

Relevant commits:

- `ea8c6c9 feat: add minimal external Gemini generate API`
- `f01bc11 docs: add integration toolbox resources`

Production deployment: PASS

Production functional verification: PASS

Historical note: this release note records the first Slice 5A Gemini-only production verification. The current External AI Gateway MVP boundary is broader and policy-gated: OpenAI `gpt-4.1-mini` / `gpt-4o-mini`, Gemini `gemini-2.5-flash`, and Claude `claude-haiku-4-5-20251001`. Candidate / Future Models shown in the admin UI are not active allowlist entries until Gateway model onboarding, NAS deployment approval, and a single-provider live smoke approval are complete.

## Verified Behavior

Deployment passed and the production Docker runtime loaded the Slice 5A code.

Functional verification passed using the app test-client inside the production container. No real Gemini, OpenAI, Claude, Replicate, or fal provider call was made during verification. The success path used a patched fake Gemini key and mocked `call_gemini_generate`.

Auth checks passed:

- Missing external key rejected.
- Wrong external key rejected.

Policy fail-closed behavior was verified:

- No policy rejected.
- Disabled policy rejected.
- Provider not allowed rejected.
- Model not allowed rejected.
- Capability not allowed rejected.
- `tools=true` rejected.
- `streaming=true` rejected.
- Oversized prompt rejected.

Provider configuration behavior was verified:

- Missing `GEMINI_API_KEY` / `GOOGLE_API_KEY` returns `provider_not_configured`.
- Provider keys were not printed or exposed.

Mocked success behavior was verified:

- Valid source policy.
- Patched fake Gemini key.
- Mocked `call_gemini_generate`.
- Response returned `ok=true`.
- Response used `provider=gemini`.
- Response used `model=gemini-1.5-flash`.
- `execution_allowed=false`.
- `side_effects=false`.

Idempotency was verified:

- Repeating the same `source_system + idempotency_key` returned `idempotent_replay=true`.
- Mocked provider was called only once.
- The replay returned the same completed result without a second provider call.

Usage/result logging was verified:

- Completed result stored.
- Usage entry stored.
- `prompt_hash` present.
- `response_hash` present.
- Prompt and response summaries were truncated/safe.
- Full prompt and response were not stored by default.
- Fake provider key was not stored.

Cleanup passed:

- Disposable policy/result/usage records removed.
- Leftovers: `0`.
- JSON stores remained valid.

Logs were clean:

- No traceback.
- No application errors.

## Safety Confirmation

Functional verification did not perform:

- Rebuild.
- Restart.
- Deploy.
- Migrations.
- Infrastructure changes.
- Real provider calls.
- Worker execution.
- Approval creation.
- Normal task/project/phase mutation.

## Slice 5A MVP Limits At Time Of Verification

Slice 5A remains intentionally narrow:

- At Slice 5A verification time, Gemini only.
- `gemini-1.5-flash` only.
- Text only.
- Non-streaming only.
- No tool calling.
- No image generation.
- No video generation.
- No worker execution.
- No project/task mutation.
- No raw provider key exposure.
