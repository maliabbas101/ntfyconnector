"""Pure demo-trading risk preflight. No broker calls or order placement.

Uses broker-provided monetary loss per one lot for the specific entry/SL.
Never derive pip value from symbol names.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pydantic import BaseModel, Field, model_validator
from app.parser import Signal

class RiskPolicy(BaseModel):
    max_risk_fraction: Decimal = Field(gt=0, le=Decimal("0.02"))
    max_volume: Decimal = Field(gt=0)
    max_spread: Decimal = Field(ge=0)

class BrokerSnapshot(BaseModel):
    is_demo: bool
    trading_enabled: bool
    equity: Decimal = Field(gt=0)
    volume_min: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    spread: Decimal = Field(ge=0)
    loss_per_lot_at_stop: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def check_volume_limits(self):
        if self.volume_max < self.volume_min:
            raise ValueError("Invalid broker volume limits")
        return self

class RiskDecision(BaseModel):
    approved: bool
    reason: str
    volume: Decimal | None = None
    estimated_loss: Decimal | None = None

def assess_demo_trade(signal: Signal, policy: RiskPolicy, broker: BrokerSnapshot) -> RiskDecision:
    if not broker.is_demo:
        return RiskDecision(approved=False, reason="LIVE_ACCOUNT_FORBIDDEN")
    if not broker.trading_enabled:
        return RiskDecision(approved=False, reason="TRADING_DISABLED")
    if signal.symbol != "XAUUSD":
        return RiskDecision(approved=False, reason="SYMBOL_NOT_ALLOWED")
    if broker.spread > policy.max_spread:
        return RiskDecision(approved=False, reason="SPREAD_TOO_HIGH")
    cap = min(policy.max_volume, broker.volume_max)
    budget = broker.equity * policy.max_risk_fraction
    affordable = budget / broker.loss_per_lot_at_stop
    if cap < broker.volume_min or affordable < broker.volume_min:
        return RiskDecision(approved=False, reason="MIN_VOLUME_EXCEEDS_RISK_BUDGET")
    steps = ((min(cap, affordable) - broker.volume_min) / broker.volume_step).to_integral_value(
        rounding=ROUND_DOWN
    )
    volume = broker.volume_min + steps * broker.volume_step
    if volume < broker.volume_min or volume > cap:
        return RiskDecision(approved=False, reason="INVALID_VOLUME")
    estimated_loss = volume * broker.loss_per_lot_at_stop
    if estimated_loss > budget:
        return RiskDecision(approved=False, reason="RISK_BUDGET_EXCEEDED")
    return RiskDecision(approved=True, reason="DEMO_PREFLIGHT_ONLY",
                        volume=volume, estimated_loss=estimated_loss)
