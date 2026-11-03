# Demo preflight integration

`preflight_demo_signal` combines read-only MT5 account verification, broker-derived quotes and one-lot stop-loss calculations, and the deterministic risk policy. Results are explicitly marked `execution_enabled: false`. `approved_for_review` means only that these limited checks passed; it is **not** authorization to place an order.

The existing command processor still rejects commands. Before execution can be enabled, implement trusted command authentication, quote-age validation, broker stop/freeze levels, margin and exposure limits, account binding, journaling and reconciliation, and Windows demo-terminal integration tests. No live trading.
