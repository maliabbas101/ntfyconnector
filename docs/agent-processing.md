# Agent command processing (non-executing)

The demo command processor validates command IDs, expiration, account identity, and demo-only account status, while journaling every received command. It deliberately rejects all commands after account verification because broker market data and monetary stop-loss exposure have not yet been independently obtained from MT5.

This is a fail-closed integration milestone, **not** a working demo trade executor. The submitted broker snapshot is untrusted and never used to authorize execution. The future Windows agent must independently obtain quotes, loss-per-lot via MT5 order_calc_profit, margin, symbol trade constraints, and position exposure; then apply risk controls and broker reconciliation before any demo order.

No live trading is supported.
