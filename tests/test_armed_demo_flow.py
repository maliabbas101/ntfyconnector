"""Signed cloud-to-Windows-agent demo flow with mocked MT5 and HTTP."""
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_api import router
from app.agent_auth import sign_command
from app.agent_identity import AgentIdentity
from app.agent_journal import CommandJournal
from app.agent_transport import poll_once
from app.command_queue import CommandQueue


KEY = b"w" * 32


class Broker:
    ACCOUNT_TRADE_MODE_DEMO = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, live=False):
        self.live = live
        self.sends = []
        self.checks = []

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(login=123, server="Demo",
                               trade_mode=2 if self.live else 0,
                               trade_allowed=True, trade_expert=True,
                               equity=10000.0, currency="USD")

    def symbol_info(self, symbol):
        return SimpleNamespace(visible=True, volume_min=0.01,
                               volume_max=10.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=4042.6, ask=4042.8)

    def order_calc_profit(self, order_type, symbol, lots, entry, sl):
        return -580.0 * lots

    def order_check(self, request):
        self.checks.append(request)
        return SimpleNamespace(retcode=0)

    def order_send(self, request):
        self.sends.append(request)
        return SimpleNamespace(retcode=10009)


def build_envelope(agent, tenant):
    cid = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=4)
    payload = {
        "command_id": cid, "expires_at": expiry.isoformat(),
        "agent_id": agent, "tenant_id": tenant,
        "expected_login": 123, "expected_server": "Demo",
        "signal": {"symbol": "XAUUSD", "side": "BUY",
                   "reference_price": "4042.8", "stop_loss": "4037",
                   "take_profit_1": "4056", "take_profit_2": "4082"},
        "policy": {"max_risk_fraction": "0.01", "max_volume": "1",
                   "max_spread": "0.5"},
        "broker": {"is_demo": True, "trading_enabled": True,
                   "equity": "10000", "volume_min": "0.01",
                   "volume_max": "10", "volume_step": "0.01",
                   "spread": "0.2", "loss_per_lot_at_stop": "580"},
    }
    return {"command_id": cid, "expires_at": expiry.isoformat(),
            "payload": payload, "signature": sign_command(KEY, cid, expiry, payload)}


def test_explicitly_armed_poll_only_sends_once_and_requires_reconciliation(
    monkeypatch, tmp_path
):
    agent, tenant = str(uuid4()), str(uuid4())
    queue_path = str(tmp_path / "cloud.db")
    monkeypatch.setenv("DEMO_AGENT_ID", agent)
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256",
                       hashlib.sha256(b"agent-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", queue_path)
    envelope = build_envelope(agent, tenant)
    with CommandQueue(queue_path) as queue:
        queue.enqueue(agent, envelope)

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as server:
        def transport(request):
            response = server.request(
                request.method, request.url.path,
                headers=dict(request.headers), content=request.content,
                follow_redirects=False)
            return httpx.Response(response.status_code,
                                  headers=dict(response.headers),
                                  content=response.content)
        broker = Broker()
        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            with CommandJournal(str(tmp_path / "journal.db")) as journal:
                args = dict(endpoint="https://agent.example.com",
                            agent_token="agent-secret", signing_secret=KEY,
                            journal=journal, mt5=broker, client=client,
                            identity=AgentIdentity(agent, tenant, 123, "Demo"),
                            arm_demo_execution=True)
                outcome = poll_once(**args)
                assert outcome["status"] == "UNACKNOWLEDGED"
                assert outcome["result"]["state"] == "EXECUTION_UNKNOWN"
                assert len(broker.sends) == 1
                assert journal.get(envelope["command_id"])["state"] == "EXECUTION_UNKNOWN"
                assert poll_once(**args)["status"] == "EMPTY"
                assert len(broker.sends) == 1
    with CommandQueue(queue_path) as queue:
        assert queue.status(envelope["command_id"]) == "DELIVERED"
        assert queue.reported_state(agent, envelope["command_id"]) == "EXECUTION_UNKNOWN"


def test_armed_poll_fails_closed_against_live_account(monkeypatch, tmp_path):
    agent, tenant = str(uuid4()), str(uuid4())
    queue_path = str(tmp_path / "cloud.db")
    monkeypatch.setenv("DEMO_AGENT_ID", agent)
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256",
                       hashlib.sha256(b"agent-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", queue_path)
    envelope = build_envelope(agent, tenant)
    with CommandQueue(queue_path) as queue:
        queue.enqueue(agent, envelope)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as server:
        def transport(request):
            response = server.request(
                request.method, request.url.path,
                headers=dict(request.headers), content=request.content,
                follow_redirects=False)
            return httpx.Response(response.status_code,
                                  headers=dict(response.headers),
                                  content=response.content)
        broker = Broker(live=True)
        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            with CommandJournal(str(tmp_path / "journal.db")) as journal:
                outcome = poll_once(
                    endpoint="https://agent.example.com",
                    agent_token="agent-secret", signing_secret=KEY,
                    journal=journal, mt5=broker, client=client,
                    identity=AgentIdentity(agent, tenant, 123, "Demo"),
                    arm_demo_execution=True)
                assert outcome["status"] == "ACKNOWLEDGED"
                assert outcome["result"]["state"] == "REJECTED"
                assert broker.sends == []
