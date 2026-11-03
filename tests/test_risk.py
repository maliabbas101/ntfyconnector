from decimal import Decimal
from app.parser import parse_signal
from app.risk import RiskPolicy, BrokerSnapshot, assess_demo_trade

SIGNAL = parse_signal("BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082")

def snapshot(**overrides):
    values = dict(is_demo=True, trading_enabled=True, equity="10000",
                  volume_min="0.01", volume_max="10", volume_step="0.01",
                  spread="0.2", loss_per_lot_at_stop="580")
    values.update(overrides)
    return BrokerSnapshot(**values)

def policy(**overrides):
    values = dict(max_risk_fraction="0.01", max_volume="1", max_spread="0.5")
    values.update(overrides)
    return RiskPolicy(**values)

def test_demo_risk_rounds_down():
    result = assess_demo_trade(SIGNAL, policy(), snapshot())
    assert result.approved
    assert result.volume == Decimal("0.17")
    assert result.estimated_loss == Decimal("98.60")

def test_live_account_always_denied():
    result = assess_demo_trade(SIGNAL, policy(), snapshot(is_demo=False))
    assert not result.approved
    assert result.reason == "LIVE_ACCOUNT_FORBIDDEN"

def test_disabled_account_denied():
    assert not assess_demo_trade(SIGNAL, policy(), snapshot(trading_enabled=False)).approved

def test_spread_denied():
    assert assess_demo_trade(SIGNAL, policy(), snapshot(spread="0.6")).reason == "SPREAD_TOO_HIGH"

def test_minimum_volume_exceeds_budget():
    result = assess_demo_trade(SIGNAL, policy(), snapshot(loss_per_lot_at_stop="20000"))
    assert result.reason == "MIN_VOLUME_EXCEEDS_RISK_BUDGET"

def test_broker_step_and_volume_cap():
    result = assess_demo_trade(SIGNAL, policy(max_volume="0.13"),
                               snapshot(volume_min="0.03", volume_step="0.05"))
    assert result.approved
    assert result.volume == Decimal("0.13")
