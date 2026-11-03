"""Read-only MT5 account verification for the future Windows demo agent.

No order submission is available in this module.
"""
from dataclasses import dataclass
from typing import Any

class AccountVerificationError(RuntimeError):
    pass

@dataclass(frozen=True)
class VerifiedDemoAccount:
    login: int
    server: str
    currency: str
    equity: str

def verify_demo_account(mt5: Any, *, expected_login: int,
                        expected_server: str) -> VerifiedDemoAccount:
    """Fail closed unless terminal and account both permit demo trading.

    mt5 is an injected MetaTrader5-compatible module to enable offline tests.
    """
    if not isinstance(expected_login, int) or isinstance(expected_login, bool) or expected_login <= 0:
        raise ValueError("expected_login must be a positive integer")
    if not expected_server or not expected_server.strip():
        raise ValueError("expected_server must be configured")
    terminal = mt5.terminal_info()
    account = mt5.account_info()
    if terminal is None or account is None:
        raise AccountVerificationError("MT5 terminal or account unavailable")
    if getattr(account, "login", None) != expected_login:
        raise AccountVerificationError("MT5 login mismatch")
    if getattr(account, "server", None) != expected_server:
        raise AccountVerificationError("MT5 server mismatch")
    if getattr(account, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise AccountVerificationError("Live or contest account forbidden")
    if not getattr(terminal, "connected", False):
        raise AccountVerificationError("MT5 terminal disconnected")
    if not getattr(terminal, "trade_allowed", False):
        raise AccountVerificationError("Terminal trading disabled")
    if not getattr(account, "trade_allowed", False):
        raise AccountVerificationError("Account trading disabled")
    if not getattr(account, "trade_expert", False):
        raise AccountVerificationError("Expert trading disabled")
    equity = getattr(account, "equity", None)
    if not isinstance(equity, (int, float)) or isinstance(equity, bool) or not (0 < equity < float("inf")):
        raise AccountVerificationError("Invalid account equity")
    currency = getattr(account, "currency", None)
    if not isinstance(currency, str) or not currency:
        raise AccountVerificationError("Account currency unavailable")
    return VerifiedDemoAccount(
        login=expected_login,
        server=expected_server,
        currency=currency,
        equity=str(equity),
    )
