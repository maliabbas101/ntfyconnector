from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.agent_journal import CommandJournal
from app.agent_processor import DemoCommand, process_demo_command

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)
    def account_info(self):
        return SimpleNamespace(login=123, server="Demo", trade_mode=0,
                               trade_allowed=True, trade_expert=True,
                               equity=1000.0, currency="USD")
    def order_send(self, *args, **kwargs):
        raise AssertionError("Order execution must never occur")

def command(**changes):
    data = dict(
        command_id=str(uuid4()), expected_login=123, expected_server="Demo",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        signal=dict(symbol="XAUUSD", side="BUY", reference_price="4042.8",
                    stop_loss="4037", take_profit_1="4056", take_profit_2="4082"),
        policy=dict(max_risk_fraction="0.01", max_volume="1", max_spread="0.5"),
        broker=dict(is_demo=True, trading_enabled=True, equity="1000",
                    volume_min="0.01", volume_max="10", volume_step="0.01",
                    spread="0.2", loss_per_lot_at_stop="580"),
    )
    data.update(changes)
    return DemoCommand(**data)

def test_dry_run_never_executes(tmp_path):
    cmd = command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = process_demo_command(cmd, journal, FakeMT5())
        assert result["state"] == "REJECTED"
        assert result["reason"] == "BROKER_MARKET_DATA_NOT_VERIFIED"
        assert result["execution_enabled"] is False
        assert journal.get(cmd.command_id)["state"] == "REJECTED"
        duplicate = process_demo_command(cmd, journal, FakeMT5())
        assert duplicate["duplicate"] is True

def test_expired_command_rejected(tmp_path):
    cmd = command(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = process_demo_command(cmd, journal, FakeMT5())
        assert result["reason"] == "EXPIRED"

def test_mismatched_account_rejected(tmp_path):
    cmd = command(expected_login=999)
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = process_demo_command(cmd, journal, FakeMT5())
        assert result["reason"] == "ACCOUNT_VERIFICATION_FAILED"
