"""Fail-closed, non-executing MT5 demo command processor.

No broker order methods are called by this module.
"""
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from app.agent_journal import CommandJournal
from app.mt5_guard import AccountVerificationError, verify_demo_account
from app.parser import Signal
from app.risk import BrokerSnapshot, RiskPolicy

class DemoCommand(BaseModel):
    command_id: str
    expected_login: int = Field(gt=0)
    expected_server: str = Field(min_length=1, max_length=200)
    expires_at: datetime
    signal: Signal
    policy: RiskPolicy
    broker: BrokerSnapshot

    @model_validator(mode="after")
    def validate_command(self):
        self.command_id = str(UUID(self.command_id))
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("Command expiry must include a timezone")
        return self

def process_demo_command(command: DemoCommand, journal: CommandJournal, mt5) -> dict:
    """Persist a command and record its preflight outcome; never execute it."""
    payload = command.model_dump(mode="json")
    state = journal.receive(command.command_id, payload)
    if state != "RECEIVED":
        return {"command_id": command.command_id, "state": state,
                "execution_enabled": False, "duplicate": True}
    if command.expires_at <= datetime.now(timezone.utc):
        journal.reject(command.command_id, "EXPIRED")
        return {"command_id": command.command_id, "state": "REJECTED",
                "reason": "EXPIRED", "execution_enabled": False}
    try:
        verify_demo_account(
            mt5, expected_login=command.expected_login,
            expected_server=command.expected_server,
        )
    except AccountVerificationError:
        journal.reject(command.command_id, "ACCOUNT_VERIFICATION_FAILED")
        return {"command_id": command.command_id, "state": "REJECTED",
                "reason": "ACCOUNT_VERIFICATION_FAILED", "execution_enabled": False}
    # Never trust a caller's account-type/permission/equity claims. For now,
    # refuse to approve a command because broker market data is not independently
    # retrieved from MT5. A future agent must calculate loss-per-lot locally.
    journal.reject(command.command_id, "BROKER_MARKET_DATA_NOT_VERIFIED")
    return {"command_id": command.command_id, "state": "REJECTED",
            "reason": "BROKER_MARKET_DATA_NOT_VERIFIED", "execution_enabled": False}
