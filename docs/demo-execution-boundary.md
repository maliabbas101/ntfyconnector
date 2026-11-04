# Isolated MT5 demo order executor

`app.demo_executor.execute_demo_once` is an **experimental, explicitly armed**
order-submission primitive. The polling transport can invoke it **only** when
`arm_demo_execution=True`; ordinary polling remains non-executing.
`app.windows_demo_agent` additionally requires the `--arm-demo` flag and
`DEMO_ORDER_EXECUTION_ENABLED=YES_I_ACCEPT_DEMO_ONLY`. The ntfy and cloud
services **never** directly invoke broker order methods.

## Prerequisites

- Operate an MT5 **demo** account only. Pin the exact login and server in each
  command and verify them independently with the local MT5 terminal.
- Verify the signed envelope and the pinned tenant/agent/account identity using
  `verify_bound_command` **before** passing a `DemoCommand` into this module.
- Provision a persistent, private SQLite `CommandJournal` directory. Do not
  delete or move this file between attempts.
- Do not use a shared/recycled command ID. The journal enforces collision
  detection and refuses a second send after an uncertain first attempt.
- The call defaults to `armed=False`. Only an explicit operator action can
  arm the local Windows agent; there is no HTTP route to arm it.

## Safety behavior

1. Persist the command in the durable journal.
2. Reject expired commands or mismatched/live broker accounts.
3. Pull broker-derived quote, equity, volume constraints and stop-loss
   loss-per-lot; refuse excess spread or risk.
4. Reject unacceptable drift from the signed reference price and invalid SL/TP
   sides; use TP1 as the broker-side take-profit. TP2 is **not** managed.
5. Recalculate monetary stop-loss risk at the final quote and selected volume,
   refuse any loss over the configured equity risk budget, then call
   `order_check` and verify the account pin again.
6. Atomically record `EXECUTION_UNKNOWN` **before** the one `order_send` call.
7. Do **not** automatically retry or infer a filled position from an MT5 result.

The persistent `EXECUTION_UNKNOWN` state applies even if `order_send`
returns a success code, fails, times out, or raises. A human must inspect
broker history/positions and provide trustworthy reconciliation evidence before
transitioning the journal to `RECONCILED`. Do not replay the command.

## Not yet production-ready

No verified broker reconciliation against MT5 orders/deals, partial-fill
handling, TP2 management, daily risk caps, customer RBAC/onboarding,
subscription billing, public production deployment, or real Windows MT5
integration testing is present. A development console and local Docker
configuration are available, but neither establishes production readiness.
The order attempt is intentionally left EXECUTION_UNKNOWN until verified.
