# Isolated MT5 demo order executor

`app.demo_executor.execute_demo_once` is an **experimental, explicitly armed**
order-submission primitive. It is **not connected** to the polling endpoint,
tenant command submission, ntfy bridge, or production API.

## Prerequisites

- Operate an MT5 **demo** account only. Pin the exact login and server in each
  command and verify them independently with the local MT5 terminal.
- Verify the signed envelope and the pinned tenant/agent/account identity using
  `verify_bound_command` **before** passing a `DemoCommand` into this module.
- Provision a persistent, private SQLite `CommandJournal` directory. Do not
  delete or move this file between attempts.
- Do not use a shared/recycled command ID. The journal enforces collision
  detection and refuses a second send after an uncertain first attempt.
- The call defaults to `armed=False`. Only a deliberate, separate operator
  action can pass `armed=True`; there is no HTTP route to arm it.

## Safety behavior

1. Persist the command in the durable journal.
2. Reject expired commands or mismatched/live broker accounts.
3. Pull broker-derived quote, equity, volume constraints and stop-loss
   loss-per-lot; refuse excess spread or risk.
4. Reject unacceptable drift from the signed reference price and invalid SL/TP
   sides; use TP1 as the broker-side take-profit. TP2 is **not** managed.
5. Call `order_check` and verify account pin again.
6. Atomically record `EXECUTION_UNKNOWN` **before** the one `order_send` call.
7. Do **not** automatically retry or infer a filled position from an MT5 result.

The persistent `EXECUTION_UNKNOWN` state applies even if `order_send`
returns a success code, fails, times out, or raises. A human must inspect
broker history/positions and provide trustworthy reconciliation evidence before
transitioning the journal to `RECONCILED`. Do not replay the command.

## Not yet production-ready

No automated reconciliation against MT5 orders/deals, slippage adaptation,
partial-fill processing, TP2 position management, daily risk caps, operator
dashboard, billing, deployment, tenant account enrollment, or Windows MT5
integration testing is present. These are prerequisites for an operational SaaS.
The executor alone does not make ntfy-to-MT5 execution functional end to end.
