"""Read-only demo MT5 preflight; never sends an order."""
from dataclasses import dataclass
from app.mt5_guard import AccountVerificationError
from app.mt5_market import MarketDataError, read_demo_snapshot
from app.parser import Signal
from app.risk import RiskPolicy, RiskDecision, assess_demo_trade

@dataclass(frozen=True)
class PreflightResult:
    approved_for_review: bool
    reason: str
    volume: str | None = None
    estimated_loss: str | None = None
    execution_enabled: bool = False

def preflight_demo_signal(mt5, signal: Signal, policy: RiskPolicy, *,
                          expected_login: int, expected_server: str) -> PreflightResult:
    """Broker-derived risk evaluation only; approval is NOT authorization to trade."""
    try:
        snapshot = read_demo_snapshot(mt5, signal, expected_login=expected_login,
                                      expected_server=expected_server)
    except (AccountVerificationError, MarketDataError, AttributeError, ValueError):
        return PreflightResult(False, "BROKER_PREFLIGHT_UNAVAILABLE")
    decision = assess_demo_trade(signal, policy, snapshot)
    return PreflightResult(
        approved_for_review=decision.approved,
        reason=decision.reason,
        volume=str(decision.volume) if decision.volume is not None else None,
        estimated_loss=str(decision.estimated_loss)
        if decision.estimated_loss is not None else None,
    )
