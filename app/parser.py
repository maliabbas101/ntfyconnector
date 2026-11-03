"""Strict, deterministic Forex alert parser. No broker operations."""
import re
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, model_validator

NUMBER = r"(\d+(?:\.\d+)?)"

class Signal(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    reference_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal

    @model_validator(mode="after")
    def validate_levels(self):
        p, sl, a, b = self.reference_price, self.stop_loss, self.take_profit_1, self.take_profit_2
        if not all(x > 0 for x in (p, sl, a, b)):
            raise ValueError("Prices must be positive")
        if not ((sl < p < a < b) if self.side == "BUY" else (sl > p > a > b)):
            raise ValueError("Invalid SL/TP ordering")
        return self

def parse_signal(text: str) -> Signal:
    if len(text) > 8192:
        raise ValueError("Message too long")
    header = re.search(r"\b(BUY|SELL)\s+(XAUUSD)\s+CMP\s*:?\s*" + NUMBER + r"\b", text, re.I)
    sl = re.search(r"\bSL\s*:\s*" + NUMBER + r"\b", text, re.I)
    tp1 = re.search(r"\bTP[-\s]*1\s*:\s*" + NUMBER + r"\b", text, re.I)
    tp2 = re.search(r"\bTP[-\s]*2\s*:\s*" + NUMBER + r"\b", text, re.I)
    if not all((header, sl, tp1, tp2)):
        raise ValueError("Missing or unsupported signal fields")
    if len(re.findall(r"\b(?:BUY|SELL)\s+XAUUSD\s+CMP\b", text, re.I)) != 1:
        raise ValueError("Ambiguous multiple signals")
    return Signal(
        side=header.group(1).upper(), symbol=header.group(2).upper(),
        reference_price=Decimal(header.group(3)),
        stop_loss=Decimal(sl.group(1)),
        take_profit_1=Decimal(tp1.group(1)),
        take_profit_2=Decimal(tp2.group(1)),
    )
