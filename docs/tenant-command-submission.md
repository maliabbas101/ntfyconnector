# Development-only tenant-scoped command submission

**Not a production customer authentication or billing system.**

The tenant ID is pinned by the server configuration, not taken from the
request. Every submission requires:

```
Authorization: Bearer <tenant-submission-token>
```

Server environment:

- `DEMO_COMMAND_TENANT_ID`: tenant UUID
- `DEMO_COMMAND_SUBMIT_TOKEN_SHA256`: SHA-256 hex digest of bearer token
- `DEMO_COMMAND_SIGNING_KEY_HEX`: server-held 32+ byte HMAC signing key
- `DEMO_COMMAND_QUEUE_PATH`: durable SQLite queue path
- `DEMO_COMMAND_AGENT_LOGIN`: positive pinned **demo** login
- `DEMO_COMMAND_AGENT_SERVER`: exact pinned demo server name
- Optional risk limits: `DEMO_COMMAND_MAX_RISK_FRACTION` (default 0.005),
  `DEMO_COMMAND_MAX_VOLUME` (default 0.1), and
  `DEMO_COMMAND_MAX_SPREAD` (default 0.5)

Explicitly enroll an agent before submission:

```bash
python -m app.provision_agent --tenant-id YOUR_TENANT_UUID \
  --agent-id YOUR_AGENT_UUID --queue-path ./commands.sqlite
```

## Recommended: server-signed alert submission

`POST /v1/dev/tenants/commands/from-signal` accepts:

```json
{
  "agent_id": "11111111-1111-4111-8111-111111111111",
  "request_id": "22222222-2222-4222-8222-222222222222",
  "requested_at": "2026-11-04T12:00:00+00:00",
  "text": "BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082"
}
```

Generate a new UUID and UTC timestamp for each deliberate submission. A request
timestamp must be within 60 seconds of the server clock. Retries must **reuse
the same** `request_id`, `requested_at`, agent ID and alert text. The server
constructs a deterministic command UUID, validates risk policy and signal,
signs the five-minute command, and queues it only for an enrolled agent.
Conflicting reuse of an idempotency key fails HTTP 409; repeated identical
submissions reuse the same command.

The response contains only queue status, command ID, expiry and
`execution_enabled: false`. The signing key is never exposed.

## Legacy development endpoint

`POST /v1/dev/tenants/commands` accepts an already-signed
`{"agent_id":"<UUID>","envelope":{...}}`. This compatibility endpoint is
intended for trusted tooling already possessing the signing key, **not**
ordinary tenant clients. It verifies signature, expiry, tenant/agent ID and
enrollment.

`GET /v1/dev/tenants/overview` returns enrollment counts and recent command
delivery states for the configured tenant, without signed payloads or
credentials. The static `/dev/console` page uses these two authenticated
endpoints. Its bearer token is held in browser memory only.

## Limitations

No automatic user signup, RBAC, billing, public rate limiting, secret rotation,
or production tenant self-service is provided. The cloud never executes
trades; only an explicitly armed and locally verified Windows demo agent
can attempt one. Legacy `CommandQueue.enqueue` bypasses enrollment checks
and must remain restricted to trusted fixture/operator code.
