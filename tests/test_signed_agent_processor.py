from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.agent_auth import AuthenticationError, SignedEnvelope, sign_command
from app.agent_journal import CommandJournal
from app.signed_agent_processor import CommandEnvelopeError, process_signed_demo_command

KEY = b"z" * 32

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)
    def account_info(self):
        return SimpleNamespace(login=123, server="Demo", trade_mode=0,
                               trade_allowed=True, trade_expert=True,
                               equity=1000.0, currency="USD")
    def order_send(self, *args, **kwargs):
        raise AssertionError("Orders are forbidden")

class NoTerminal:
    def __getattr__(self, name):
        raise AssertionError("Unauthenticated command accessed MT5")

def make_envelope(*, tamper=False, mismatched_id=False):
    cid = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = dict(
        command_id=str(uuid4()) if mismatched_id else cid,
        expires_at=expiry.isoformat(), expected_login=123,
        expected_server="Demo",
        signal=dict(symbol="XAUUSD", side="BUY", reference_price="4042.8",
                    stop_loss="4037", take_profit_1="4056", take_profit_2="4082"),
        policy=dict(max_risk_fraction="0.01", max_volume="1", max_spread="0.5"),
        broker=dict(is_demo=True, trading_enabled=True, equity="1000",
                    volume_min="0.01", volume_max="10", volume_step="0.01",
                    spread="0.2", loss_per_lot_at_stop="580"),
    )
    signature = sign_command(KEY, cid, expiry, payload)
    if tamper:
        payload["expected_login"] = 999
    return SignedEnvelope(command_id=cid, expires_at=expiry,
                          payload=payload, signature=signature)

def test_signed_command_journaled_but_never_executed(tmp_path):
    envelope = make_envelope()
    with CommandJournal(str(tmp_path / "agent.db")) as journal:
        result = process_signed_demo_command(envelope, KEY, journal, FakeMT5())
        assert result["execution_enabled"] is False
        assert result["state"] == "REJECTED"
        assert journal.get(envelope.command_id)["state"] == "REJECTED"
        duplicate = process_signed_demo_command(envelope, KEY, journal, FakeMT5())
        assert duplicate["duplicate"]

def test_invalid_mac_does_not_touch_journal_or_terminal(tmp_path):
    envelope = make_envelope(tamper=True)
    with CommandJournal(str(tmp_path / "agent.db")) as journal:
        with pytest.raises(AuthenticationError):
            process_signed_demo_command(envelope, KEY, journal, NoTerminal())
        assert journal.get(envelope.command_id) is None

def test_signed_id_mismatch_does_not_touch_journal(tmp_path):
    envelope = make_envelope(mismatched_id=True)
    with CommandJournal(str(tmp_path / "agent.db")) as journal:
        with pytest.raises(CommandEnvelopeError):
            process_signed_demo_command(envelope, KEY, journal, NoTerminal())
        assert journal.get(envelope.command_id) is None

def test_wrong_key_fails_before_mt5(tmp_path):
    envelope = make_envelope()
    with CommandJournal(str(tmp_path / "agent.db")) as journal:
        with pytest.raises(AuthenticationError):
            process_signed_demo_command(envelope, b"x" * 32, journal, NoTerminal())
        assert journal.get(envelope.command_id) is None
