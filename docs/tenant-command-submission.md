# Development-only tenant-scoped command submission

`POST /v1/dev/tenants/commands` accepts `{"agent_id":"<UUID>","envelope":{...}}` with an `Authorization: Bearer <submit-token>` header. This endpoint is disabled unless all of these server-side environment variables are set:

- `DEMO_COMMAND_TENANT_ID`: UUID identifying the **one** allowed tenant
- `DEMO_COMMAND_SUBMIT_TOKEN_SHA256`: SHA-256 hex digest of a separately provisioned submission token
- `DEMO_COMMAND_SIGNING_KEY_HEX`: at least 32 bytes of command HMAC key, hex encoded
- `DEMO_COMMAND_QUEUE_PATH`: local SQLite queue path

An operator must first enroll the agent with `CommandQueue.enroll_agent(agent_id, tenant_id)` using trusted local administrative code. The route verifies bearer authentication, server-pinned tenant identity, enrollment, HMAC signature, command ID, expiry, and signed agent/tenant identity. It does not accept a caller-provided tenant ID. Repeating the same signed command is idempotent; conflicting command IDs fail.

**Limitations:** This is a single-tenant development endpoint, not a multi-user SaaS authentication or RBAC implementation. The signing key must never be sent to clients. The legacy `enqueue` method still bypasses these checks and must remain restricted to trusted local code. This endpoint queues signed commands only; it does not execute trades. Do not expose it to the public internet without production authorization, auditing, rate limits, and key lifecycle controls.
