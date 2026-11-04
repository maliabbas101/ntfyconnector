import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.agent_api import router
from app.command_queue import CommandQueue

def setup(monkeypatch, tmp_path):
    path = str(tmp_path / "queue.db")
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_AGENT_ID", "agent-a")
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256",
                       hashlib.sha256(b"secret-token").hexdigest())
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), path

def test_auth_required_and_agent_scoped(monkeypatch, tmp_path):
    client, path = setup(monkeypatch, tmp_path)
    item = {"command_id": str(uuid4()),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "payload": {"demo": True}, "signature": "a" * 64}
    with CommandQueue(path) as queue:
        queue.enqueue("agent-b", item)
    assert client.get("/v1/agent/commands/next").status_code == 401
    assert client.get("/v1/agent/commands/next",
                      headers={"Authorization": "Bearer wrong"}).status_code == 401
    response = client.get("/v1/agent/commands/next",
                          headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 204

def test_delivery_and_ack(monkeypatch, tmp_path):
    client, path = setup(monkeypatch, tmp_path)
    item = {"command_id": str(uuid4()),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "payload": {"demo": True}, "signature": "a" * 64}
    with CommandQueue(path) as queue:
        queue.enqueue("agent-a", item)
    headers = {"Authorization": "Bearer secret-token"}
    response = client.get("/v1/agent/commands/next", headers=headers)
    assert response.status_code == 200
    assert response.json() == item
    ack_url = "/v1/agent/commands/" + item["command_id"] + "/ack"
    report_url = "/v1/agent/commands/" + item["command_id"] + "/journal-state"
    assert client.post(ack_url, headers=headers).status_code == 404
    assert client.post(report_url, headers=headers,
                       json={"state": "RECEIVED"}).status_code == 200
    assert client.post(ack_url, headers=headers).status_code == 404
    assert client.post(report_url, headers=headers,
                       json={"state": "REJECTED"}).status_code == 200
    assert client.post(ack_url, headers=headers).status_code == 200
    assert client.post(ack_url, headers=headers).status_code == 200

def test_disabled_by_default(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    monkeypatch.delenv("DEMO_AGENT_TOKEN_SHA256")
    assert client.get("/v1/agent/commands/next").status_code == 503
