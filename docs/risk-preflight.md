# Demo risk preflight (non-executing)

`assess_demo_trade` is a deterministic policy evaluator. It rejects live accounts, disabled trading, excess spreads, unsupported symbols, and trade sizes below the broker's minimum volume. It computes the maximum affordable volume from equity, risk fraction, and **broker-calculated loss per lot at the stop**, then rounds down to the broker's volume increment.

This is **not an order executor**. The broker snapshot must come from a trusted local MT5 demo agent; never accept it as authoritative from an untrusted cloud caller. Before any order is placed, the agent must independently re-check the live tick, spread, stop/freeze levels, margin, broker account type, execution permissions, order expiry, idempotency, and actual stop-loss monetary loss using broker APIs. It must reject if any check fails.

This implementation does not model commissions, slippage, currency conversion, multi-position exposure, or daily drawdown. Therefore it is not sufficient to enable trading by itself.
