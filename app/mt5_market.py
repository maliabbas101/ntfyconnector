"""Read-only broker-derived MT5 market snapshot for demo risk evaluation."""
from decimal import Decimal, InvalidOperation
from typing import Any
from app.mt5_guard import verify_demo_account
from app.parser import Signal
from app.risk import BrokerSnapshot

class MarketDataError(RuntimeError):
    pass

def _positive(value, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MarketDataError(f"Invalid {label}") from exc
    if not number.is_finite() or number <= 0:
        raise MarketDataError(f"Invalid {label}")
    return number

def read_demo_snapshot(mt5: Any, signal: Signal, *,
                       expected_login: int, expected_server: str) -> BrokerSnapshot:
    """Read MT5 quote, volume limits, and monetary loss for one lot.

    No trade is sent. Re-check account after data collection to detect switches.
    """
    account = verify_demo_account(mt5, expected_login=expected_login,
                                  expected_server=expected_server)
    info = mt5.symbol_info(signal.symbol)
    tick = mt5.symbol_info_tick(signal.symbol)
    if info is None or tick is None or not getattr(info, "visible", False):
        raise MarketDataError("Symbol or tick unavailable")
    bid = _positive(getattr(tick, "bid", None), "bid")
    ask = _positive(getattr(tick, "ask", None), "ask")
    if ask < bid:
        raise MarketDataError("Crossed quote")
    entry = ask if signal.side == "BUY" else bid
    if (signal.side == "BUY" and signal.stop_loss >= entry) or (
        signal.side == "SELL" and signal.stop_loss <= entry
    ):
        raise MarketDataError("Stop loss invalid for current market quote")
    order_type = mt5.ORDER_TYPE_BUY if signal.side == "BUY" else mt5.ORDER_TYPE_SELL
    loss = mt5.order_calc_profit(order_type, signal.symbol, 1.0,
                                 float(entry), float(signal.stop_loss))
    if loss is None:
        raise MarketDataError("Broker loss calculation unavailable")
    loss_decimal = Decimal(str(loss))
    if not loss_decimal.is_finite() or loss_decimal >= 0:
        raise MarketDataError("Broker did not report a loss at stop")
    volume_min = _positive(getattr(info, "volume_min", None), "volume_min")
    volume_max = _positive(getattr(info, "volume_max", None), "volume_max")
    volume_step = _positive(getattr(info, "volume_step", None), "volume_step")
    if volume_max < volume_min:
        raise MarketDataError("Invalid volume range")
    # Detect a broker account switch during data collection.
    verified_again = verify_demo_account(mt5, expected_login=expected_login,
                                         expected_server=expected_server)
    if verified_again != account:
        raise MarketDataError("Account changed while reading market data")
    return BrokerSnapshot(
        is_demo=True, trading_enabled=True, equity=account.equity,
        volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
        spread=ask - bid, loss_per_lot_at_stop=-loss_decimal,
    )
