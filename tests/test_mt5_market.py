from types import SimpleNamespace
import pytest
from app.mt5_market import MarketDataError, read_demo_snapshot
from app.mt5_guard import AccountVerificationError
from app.parser import parse_signal
from app.risk import RiskPolicy, assess_demo_trade

SIGNAL = parse_signal("BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082")

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    def __init__(self):
        self.account = SimpleNamespace(login=123, server="Demo", trade_mode=0,
            trade_allowed=True, trade_expert=True, equity=10000.0, currency="USD")
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True)
        self.info = SimpleNamespace(visible=True, volume_min=0.01,
                                    volume_max=10.0, volume_step=0.01)
        self.tick = SimpleNamespace(bid=4042.8, ask=4043.0)
        self.loss = -600.0
    def account_info(self):
        return self.account
    def terminal_info(self):
        return self.terminal
    def symbol_info(self, symbol):
        return self.info
    def symbol_info_tick(self, symbol):
        return self.tick
    def order_calc_profit(self, *args):
        return self.loss
    def order_send(self, *args):
        raise AssertionError("Must not submit orders")

def snapshot(mt5):
    return read_demo_snapshot(mt5, SIGNAL, expected_login=123, expected_server="Demo")

def test_broker_derived_snapshot_is_risk_evaluable():
    snap = snapshot(FakeMT5())
    result = assess_demo_trade(SIGNAL,
        RiskPolicy(max_risk_fraction="0.01", max_volume="1", max_spread="0.5"), snap)
    assert result.approved
    assert str(result.volume) == "0.16"

def test_live_account_rejected():
    mt5 = FakeMT5()
    mt5.account.trade_mode = 2
    with pytest.raises(AccountVerificationError):
        snapshot(mt5)

@pytest.mark.parametrize("loss", [None, 0, 100, float("nan")])
def test_invalid_loss_rejected(loss):
    mt5 = FakeMT5()
    mt5.loss = loss
    with pytest.raises(MarketDataError):
        snapshot(mt5)

def test_crossed_quote_rejected():
    mt5 = FakeMT5()
    mt5.tick.ask = 4000
    with pytest.raises(MarketDataError):
        snapshot(mt5)

def test_missing_tick_rejected():
    mt5 = FakeMT5()
    mt5.tick = None
    with pytest.raises(MarketDataError):
        snapshot(mt5)
