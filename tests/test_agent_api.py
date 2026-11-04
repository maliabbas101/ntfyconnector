import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.agent_api import router
from app.command_queue import CommandQueue

AGENT_A = "11111111-1111-4111-8111-111111111111"
AGENT_B = "22222222-2222-4222-8222-222222222222"

def setup(monkeypatch, tmp_path):
    path = str(tmp_path / "queue.db")
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_AGENT_ID", AGENT_A)
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
        queue.enqueue(AGENT_B, item)
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
        queue.enqueue(AGENT_A, item)
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


def test_receipt_is_read_only_and_agent_scoped(monkeypatch, tmp_path):
    client, path = setup(monkeypatch, tmp_path)
    mine, other = str(uuid4()), str(uuid4())
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with CommandQueue(path) as queue:
        queue.enqueue(AGENT_A, {"command_id": mine, "expires_at": expiry,
                                  "payload": {}, "signature": "a" * 64})
        queue.enqueue(AGENT_B, {"command_id": other, "expires_at": expiry,
                                  "payload": {}, "signature": "a" * 64})
    url = "/v1/agent/commands/" + mine + "/receipt"
    headers = {"Authorization": "Bearer secret-token"}
    assert client.get(url).status_code == 401
    assert client.get("/v1/agent/commands/" + other + "/receipt",
                      headers=headers).status_code == 404
    assert client.get(url, headers=headers).json() == {
        "status": "PENDING", "journal_state": None, "execution_enabled": False}
    with CommandQueue(path) as queue:
        assert queue.status(mine) == "PENDING"
        queue.next_for_agent(AGENT_A)
        queue.report_journal_state(AGENT_A, mine, "REJECTED")
    assert client.get(url, headers=headers).json() == {
        "status": "DELIVERED", "journal_state": "REJECTED",
        "execution_enabled": False}
    assert client.post("/v1/agent/commands/" + mine + "/ack",
                       headers=headers).status_code == 200
    assert client.get(url, headers=headers).json()["status"] == "ACKNOWLEDGED"


def test_recovery_endpoint_is_scoped_and_read_only(monkeypatch, tmp_path):
    client, path = setup(monkeypatch, tmp_path)
    mine, other = str(uuid4()), str(uuid4())
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with CommandQueue(path) as queue:
        for agent, command_id in ((AGENT_A, mine), (AGENT_B, other)):
            queue.enqueue(agent, {"command_id": command_id, "expires_at": expiry,
                                  "payload": {}, "signature": "a" * 64})
            queue.next_for_agent(agent)
        # A future cutoff makes both deliveries old enough without sleeping.
        assert queue.recover_unacknowledged(
            AGENT_A, now=datetime.now(timezone.utc) + timedelta(minutes=2),
            min_age_seconds=60) == [mine]
    headers = {"Authorization": "Bearer secret-token"}
    url = "/v1/agent/commands/recovery"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers, params={"min_age_seconds": 0}).status_code == 422
    # No old deliveries are requeued by this endpoint.
    assert client.get(url, headers=headers).json() == {
        "command_ids": [], "execution_enabled": False}
    with CommandQueue(path) as queue:
        assert queue.status(mine) == "DELIVERED"
        assert queue.status(other) == "DELIVERED"


def test_empty_agent_token_rejected_even_if_configured_hash_matches(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256", hashlib.sha256(b"").hexdigest())
    response = client.get("/v1/agent/commands/next",
                          headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_malformed_configured_token_digest_fails_closed(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256", "z" * 64)
    response = client.get("/v1/agent/commands/next",
                          headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 503


def test_invalid_configured_agent_id_fails_closed(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("DEMO_AGENT_ID", "not-a-uuid")
    assert client.get("/v1/agent/commands/next",
                      headers={"Authorization": "Bearer secret-token"}).status_code == 503


def test_uppercase_configured_digest_is_accepted(monkeypatch, tmp_path):
    client, _ = setup(monkeypatch, tmp_path)
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256",
                       hashlib.sha256(b"secret-token").hexdigest().upper())
    assert client.get("/v1/agent/commands/next",
                      headers={"Authorization": "Bearer secret-token"}).status_code == 204
