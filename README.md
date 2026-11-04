# ntfyconnector

Multi-tenant ntfy.sh signal intake and MetaTrader 5 **demo-only** automation prototype.

## Current status

**Not production-ready.** The FastAPI service, ntfy stream bridge, signed
command transport, SQLite agent journal, and read-only broker risk checks are
implemented. HTTP polling deliberately processes commands without sending
broker orders.

An **isolated experimental demo-order primitive** is available in
`app/demo_executor.py`, but it is not connected to the ntfy-to-agent flow
and is disarmed by default. See [demo execution boundary](docs/demo-execution-boundary.md).
Do not deploy it for unattended execution.

## Local development

Requires Python 3.11+.

```bash
python -m pip install -e '.[dev]'
pytest -q
uvicorn app.main:app --reload
```

The API exposes `GET /health` and `POST /v1/signals/validate`.
The additional source ingestion, agent polling and development command
submission routes require their documented credentials/configuration.

## Safety and limitations

- Never connect this experimental build to a live MT5 account.
- Agent command processing is **non-executing**; the isolated demo executor
  requires an explicit `armed=True` call, verified demo account and a durable
  journal.
- Duplicate or uncertain execution commands must never be automatically
  replayed.
- There is no complete dashboard, subscription billing, production deployment,
  Windows MT5 end-to-end test, or live-broker verification.
- PostgreSQL row-level security and source-authentication access require a
  production integration review before multi-tenant launch.

Current engineering scope is a prototype, **not a finished SaaS**.
