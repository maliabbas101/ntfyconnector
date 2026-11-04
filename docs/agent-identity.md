# Agent identity pinning

The `AgentIdentity` and `verify_bound_command` helpers enforce signed agent UUID, tenant UUID, and MT5 login/server against local immutable configuration. Authentication and identity checks happen before journal or terminal access. The outbound polling client now requires a pinned identity before processing a command.

The development queue additionally rejects enqueueing an envelope whose payload includes an `agent_id` different from its queue owner. This is defense in depth, **not a substitute for verifying the envelope signature at enqueue time**. The queue still supports legacy unbound test payloads; production command creation must require authenticated, versioned, fully bound envelopes and verify tenant ownership server-side.

Enrollment, secret rotation, multi-tenant cloud authorization, and live MT5 validation remain outstanding. Trading stays disabled.

## Strict development enqueue path

`CommandQueue.enroll_agent(agent_id, tenant_id)` pins an agent to a tenant; attempts to reassign it fail. `enqueue_bound(agent_id, tenant_id, envelope, signing_secret)` verifies the HMAC, expiry, command ID, and signed tenant/agent identity before placing a command in the queue. Existing `enqueue` remains a legacy, unauthenticated development API and **must not be exposed to untrusted producers**. No production tenant authorization API or enrollment credentials are provided yet. The strict method checks local enrollment but does not authenticate who called it; callers must be trusted server-side code.
