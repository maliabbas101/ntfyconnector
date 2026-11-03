# Windows MT5 agent — read-only account guard

The agent foundation now includes `verify_demo_account`, a read-only checker that uses the official MetaTrader5 Python API shape. It rejects live and contest accounts, mismatched account IDs or broker servers, disconnected terminals, disabled trading permissions, and invalid account equity.

This checker is designed for use on the customer's Windows computer alongside a locally authenticated MT5 desktop terminal. The expected login and server must come from a trusted agent enrollment process; they must not be taken from arbitrary notification text.

**Current limitations:** There is no running Windows agent, network enrollment, secure command channel, broker order placement, or tested connection to a real demo terminal. The MetaTrader5 package is deliberately not a dependency of the Linux backend. Install and test the official package only in the future Windows agent environment.

Every future command must re-verify the demo account immediately before any broker operation, apply local risk controls, and use the durable command journal. Live trading is prohibited.
