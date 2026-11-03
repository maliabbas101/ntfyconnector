from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.agent_auth import sign_command
from app.agent_journal import CommandJournal
from app.agent_transport import poll_once

KEY = b"m" * 32

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)
    def account_info(self):
        return SimpleNamespace(login=123, server="Demo", trade_mode=0,
                               trade_allowed=True, trade_expert=True,
                               equity=1000.0, currency="USD")
    def order_send(self, *args, **kwargs):
        raise AssertionError("Broker execution forbidden")

def signed_envelope():
    cid = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=2)
    payload = {
        "command_id": cid, "expires_at": expiry.isoformat(),
        "expected_login": 123, "expected_server": "Demo",
        "signal": {"symbol": "XAUUSD", "side": "BUY",
                   "reference_price": "4042.8", "stop_loss": "4037",
                   "take_profit_1": "4056", "take_profit_2": "4082"},
        "policy": {"max_risk_fraction": "0.01", "max_volume": "1", "max_spread": "0.5"},
        "broker": {"is_demo": True, "trading_enabled": True,
                   "equity": "1000", "volume_min": "0.01", "volume_max": "10",
                   "volume_step": "0.01", "spread": "0.2",
                   "loss_per_lot_at_stop": "580"},
    }
    return {"command_id": cid, "expires_at": expiry.isoformat(),
            "payload": payload, "signature": sign_command(KEY, cid, expiry, payload)}

def test_signed_command_acknowledged_after_journal(tmp_path):
    envelope = signed_envelope()
    seen = []
    def handler(request):
        seen.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json=envelope)
        assert request.url.path.endswith(envelope["command_id"] + "/ack")
        return httpx.Response(200, json={"status": "ACKNOWLEDGED"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            result = poll_once(endpoint="https://agent.example.com",
                               agent_token="token", signing_secret=KEY,
                               journal=journal, mt5=FakeMT5(), client=client)
            assert result["status"] == "ACKNOWLEDGED"
            assert journal.get(envelope["command_id"])["state"] == "REJECTED"
            assert seen == ["GET", "POST"]

def test_invalid_signature_never_acknowledged(tmp_path):
    envelope = signed_envelope()
    envelope["payload"]["expected_login"] = 999
    seen = []
    def handler(request):
        seen.append(request.method)
        return httpx.Response(200, json=envelope)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            with pytest.raises(ValueError):
                poll_once(endpoint="https://agent.example.com",
                          agent_token="token", signing_secret=KEY,
                          journal=journal, mt5=FakeMT5(), client=client)
            assert seen == ["GET"]
            assert journal.get(envelope["command_id"]) is None
