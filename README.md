# ntfyconnector

Prototype for converting **ntfy.sh** notifications into authenticated,
risk-checked **MetaTrader 5 demo-only** commands. **Not production-ready.**

## Implemented development pipeline

1. `app.ntfy_bridge` consumes ntfy notifications and forwards durable event IDs.
2. `/v1/ingest/tenants/{tenant_id}/sources/{source_id}` authenticates the
   source token and stores validated events with tenant isolation.
3. `app.signal_dispatcher` creates deterministic signed commands for an
   explicitly enrolled agent; repeat scans do not create new commands.
4. `/v1/agent/commands/next` delivers each command at most once.
5. The Windows agent verifies signature, tenant, agent, account pin and broker
   data. Normal polling rejects without trading. Explicitly armed demo polling
   can attempt **one** MT5 order, then persists `EXECUTION_UNKNOWN`.
6. A local journal and cloud receipt track the outcome without automatic
   replay. Broker reconciliation is still a manual operational step.

## Local development

Requires Python 3.11+.

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
alembic upgrade head
uvicorn app.main:app --reload
```

Alternatively, create a local `.env` from `.env.example`, then run:

```bash
docker compose up --build
```

The API binds to **127.0.0.1:8000** in the Docker configuration.
`GET /health` reports status and `/dev/console` provides a minimal
development page. The console requires a configured tenant submission bearer
token and enrolled agent; it does not arm the Windows executor.

## Provisioning a local test tenant

Generate a fresh tenant UUID and agent UUID. Configure the server variables in
`.env.example`; **generate your own high-entropy bearer tokens and a random
32+ byte HMAC signing secret**. Save bearer token SHA-256 digests, not their
plaintext, in the server environment.

For local SQLite:

```bash
python -m app.provision_source --tenant-id YOUR_TENANT_UUID
```

Save the displayed `SOURCE_ID` and `SOURCE_TOKEN` securely; set
`SOURCE_TENANT_ID` to the same tenant UUID in the bridge environment.
Enroll the agent through trusted local administrative Python using
`CommandQueue(queue_path).enroll_agent(agent_uuid, tenant_uuid)`. The API
does not auto-enroll agents.

Start the bridge with `NTFY_TOPIC`, `SOURCE_ID`, `SOURCE_TOKEN`,
`SOURCE_TENANT_ID`, `NTFY_URL` and an HTTPS `API_URL`. For local-host
development only, `ALLOW_LOCAL_HTTP=1` permits an HTTP API on localhost.
Start `python -m app.ntfy_bridge`.

Run `python -m app.signal_dispatcher` with the server-owned tenant/agent
IDs, queue path, signing key and demo account pin. The dispatcher sends no
orders. Never expose its signing key to tenant clients.

Alternatively, use the authenticated server-signing
`POST /v1/dev/tenants/commands/from-signal` endpoint with a stable
`request_id` UUID and `requested_at` timestamp. The browser
`/dev/console` sends these fields automatically.

## Windows demo agent

See [Windows demo agent guide](docs/windows-demo-agent.md) and
[demo execution boundary](docs/demo-execution-boundary.md). The default
one-shot agent never sends orders. An explicitly armed invocation can make
a single **demo-only** order attempt, after independently verifying the local
terminal/account and calculating broker risk. It is not suitable for
unattended deployment without broker reconciliation, TP2/partial-fill handling,
and real MT5 integration tests.

## Not yet implemented or verified

- Automated, evidence-backed MT5 broker reconciliation and position lifecycle.
- Full customer signup, RBAC, self-service enrollment and subscriptions/billing.
- Production deployment, rate limits, monitoring and key rotation.
- Confirmed complete CI test suite and real Windows demo-terminal tests.
- PostgreSQL FORCE RLS integration tests against a non-owner runtime role.

Development infrastructure and a basic console exist; this is **not a finished
hosted SaaS**. Never use an MT5 live account with this prototype.
