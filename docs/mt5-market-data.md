# Read-only MT5 market snapshot

`read_demo_snapshot` verifies a pinned MT5 demo account, reads the current bid/ask and symbol lot limits, and asks MT5 `order_calc_profit` for the expected monetary loss of a **one-lot** trade between the current entry quote and stop. It verifies the account again before returning. The result can be evaluated by the pure risk-preflight module.

This does not send orders or establish that an order is safe to send. The next agent integration must add quote freshness, spread units, symbol execution permissions, broker stop/freeze constraints, margin checks, open-position and daily exposure caps, local command authentication, and reconciliation. Some brokers may not accept a one-lot calculation for symbols with restrictive volume limits; those cases must fail closed or use a validated alternative. Do not enable live trading.
