"""Full local-development cloud queue -> HTTPS client -> journal -> ACK test."""
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_api import router
from app.agent_auth import sign_command
from app.agent_journal import CommandJournal
from app.agent_transport import poll_once
from app.command_queue import CommandQueue

KEY = b"k" * 32

class FakeDemoMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(
            login=123, server="Demo", trade_mode=0, trade_allowed=True,
            trade_expert=True, equity=10000.0, currency="USD",
        )

    def order_send(self, *args, **kwargs):
        raise AssertionError("End-to-end delivery must never place an order")

def test_queue_to_agent_to_ack(monkeypatch, tmp_path):
    queue_path = str(tmp_path / "cloud.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", queue_path)
    monkeypatch.setenv("DEMO_AGENT_ID", "agent-one")
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256", hashlib.sha256(b"token").hexdigest())

    command_id = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=3)
    payload = {
        "command_id": command_id,
        "expires_at": expiry.isoformat(),
        "expected_login": 123,
        "expected_server": "Demo",
        "signal": {
            "symbol": "XAUUSD", "side": "BUY",
            "reference_price": "4042.8", "stop_loss": "4037",
            "take_profit_1": "4056", "take_profit_2": "4082",
        },
        "policy": {
            "max_risk_fraction": "0.01", "max_volume": "1",
            "max_spread": "0.5",
        },
        "broker": {
            "is_demo": True, "trading_enabled": True, "equity": "10000",
            "volume_min": "0.01", "volume_max": "10",
            "volume_step": "0.01", "spread": "0.2",
            "loss_per_lot_at_stop": "580",
        },
    }
    envelope = {
        "command_id": command_id,
        "expires_at": expiry.isoformat(),
        "payload": payload,
        "signature": sign_command(KEY, command_id, expiry, payload),
    }
    with CommandQueue(queue_path) as queue:
        queue.enqueue("agent-one", envelope)

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as server:
        def handler(request: httpx.Request) -> httpx.Response:
            response = server.request(
                request.method, request.url.path,
                headers=dict(request.headers),
                content=request.content,
                follow_redirects=False,
            )
            return httpx.Response(
                response.status_code, headers=dict(response.headers),
                content=response.content,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with CommandJournal(str(tmp_path / "agent.sqlite")) as journal:
                result = poll_once(
                    endpoint="https://agent.example.com",
                    agent_token="token",
                    signing_secret=KEY,
                    journal=journal,
                    mt5=FakeDemoMT5(),
                    client=client,
                )
                assert result["status"] == "ACKNOWLEDGED"
                assert result["execution_enabled"] is False
                assert journal.get(command_id)["state"] == "REJECTED"
                assert poll_once(
                    endpoint="https://agent.example.com",
                    agent_token="token",
                    signing_secret=KEY,
                    journal=journal,
                    mt5=FakeDemoMT5(),
                    client=client,
                )["status"] == "EMPTY"

    with CommandQueue(queue_path) as queue:
        assert queue.status(command_id) == "ACKNOWLEDGED"\n        assert queue.reported_state("agent-one", command_id) == "REJECTED"
