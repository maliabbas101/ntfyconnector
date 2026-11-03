from types import SimpleNamespace
from app.agent_preflight import preflight_demo_signal
from app.parser import parse_signal
from app.risk import RiskPolicy

signal = parse_signal("BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082")
policy = RiskPolicy(max_risk_fraction="0.01", max_volume="1", max_spread="0.5")

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    def __init__(self):
        self.mode = 0
    def account_info(self):
        return SimpleNamespace(login=123, server="Demo", trade_mode=self.mode,
                               trade_allowed=True, trade_expert=True,
                               equity=10000.0, currency="USD")
    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)
    def symbol_info(self, symbol):
        return SimpleNamespace(visible=True, volume_min=0.01,
                               volume_max=10.0, volume_step=0.01)
    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=4042.8, ask=4043.0)
    def order_calc_profit(self, *args):
        return -600.0
    def order_send(self, *args):
        raise AssertionError("Order execution forbidden")

def test_broker_risk_preflight_is_nonexecuting():
    result = preflight_demo_signal(FakeMT5(), signal, policy,
                                   expected_login=123, expected_server="Demo")
    assert result.approved_for_review
    assert result.volume == "0.16"
    assert result.execution_enabled is False

def test_live_account_fails_closed():
    mt5 = FakeMT5()
    mt5.mode = 2
    result = preflight_demo_signal(mt5, signal, policy,
                                   expected_login=123, expected_server="Demo")
    assert not result.approved_for_review
    assert result.reason == "BROKER_PREFLIGHT_UNAVAILABLE"

def test_missing_mt5_methods_fails_closed():
    result = preflight_demo_signal(object(), signal, policy,
                                   expected_login=123, expected_server="Demo")
    assert not result.approved_for_review
