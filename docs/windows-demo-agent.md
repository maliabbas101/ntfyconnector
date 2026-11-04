# One-shot Windows MT5 demo agent

**Experimental. Never connect a live trading account.**

## Prerequisites

- Windows with the MetaTrader 5 terminal installed and signed into a
  **demo** account you control.
- Python 3.11+, the Python package `MetaTrader5` installed locally on
  Windows, and the ntfyconnector package from this repository.
- A trusted HTTPS endpoint with a valid certificate on port 443. The local
  Docker setup on HTTP port 8000 is only for development; it is **not** an
  acceptable remote agent endpoint.
- A UUID agent already enrolled into the server-pinned tenant and a persistent
  journal file location accessible only to the agent user.
- A high-entropy agent bearer token and the server's command **verification**
  HMAC key (at least 32 bytes), provisioned out of band.

## Required environment

```powershell
$env:AGENT_API_URL = "https://your-private-api.example"
$env:AGENT_TOKEN = "<agent bearer token>"
$env:AGENT_SIGNING_KEY_HEX = "<hex-encoded HMAC key>"
$env:AGENT_ID = "<agent UUID>"
$env:AGENT_TENANT_ID = "<tenant UUID>"
$env:MT5_DEMO_LOGIN = "<demo account login number>"
$env:MT5_DEMO_SERVER = "<exact demo server name>"
$env:AGENT_JOURNAL_PATH = "C:\\ntfyconnector\\agent-journal.sqlite"
```

For the default non-executing mode:

```powershell
python -m app.windows_demo_agent
```

This consumes **at most one** pending signed command per invocation. A valid
command is journaled, risk checks run and the command is rejected without
broker order submission.

The experimental armed demo-only mode requires **both** of these operator
actions (never put them in a public web interface):

```powershell
$env:DEMO_ORDER_EXECUTION_ENABLED = "YES_I_ACCEPT_DEMO_ONLY"
python -m app.windows_demo_agent --arm-demo
```

The module verifies the pinned demo account, broker-derived SL risk,
account identity again before sending, and persists `EXECUTION_UNKNOWN`
**before** its one order attempt. It does **not** retry, acknowledge an
uncertain outcome, or assert that a position was filled.

## Reconciliation

When the agent returns `UNACKNOWLEDGED`, the cloud records a reported
`EXECUTION_UNKNOWN` and retains the command as delivered. Inspect MT5
positions and order/deal history using the exact demo account, timestamp,
symbol, comment and trade details. Do not retry the original command.
A later `RECONCILED` journal transition must be based on reliable broker
evidence; then use the terminal-receipt recovery workflow documented in
`docs/delivery-recovery.md`. There is no automated broker-evidence
reconciliation in this prototype.

This is a testing workflow, **not** a production recommendation.
