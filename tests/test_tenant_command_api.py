import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agent_auth import sign_command
from app.command_queue import CommandQueue
from app.main import app

KEY = b"t" * 32


def test_dev_submission_enforces_tenant_and_agent(monkeypatch, tmp_path):
    tenant, agent, other = str(uuid4()), str(uuid4()), str(uuid4())
    path = str(tmp_path / "queue.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_TENANT_ID", tenant)
    monkeypatch.setenv("DEMO_COMMAND_SUBMIT_TOKEN_SHA256",
                       hashlib.sha256(b"submit-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_SIGNING_KEY_HEX", KEY.hex())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    with CommandQueue(path) as queue:
        queue.enroll_agent(agent, tenant)
        queue.enroll_agent(other, str(uuid4()))
    cid = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {"agent_id": agent, "tenant_id": tenant,
               "command_id": cid, "expires_at": expiry.isoformat()}
    envelope = {"command_id": cid, "expires_at": expiry.isoformat(),
                "payload": payload,
                "signature": sign_command(KEY, cid, expiry, payload)}
    client = TestClient(app)
    url = "/v1/dev/tenants/commands"
    body = {"agent_id": agent, "envelope": envelope}
    auth = {"Authorization": "Bearer submit-secret"}
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json=body,
                       headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post(url, json=dict(body, agent_id=other),
                       headers=auth).status_code == 409
    altered = dict(envelope, payload=dict(payload, tenant_id=str(uuid4())))
    assert client.post(url, json=dict(body, envelope=altered),
                       headers=auth).status_code == 409
    assert client.post(url, json=body, headers=auth).status_code == 202
    assert client.post(url, json=body, headers=auth).status_code == 202
    with CommandQueue(path) as queue:
        assert queue.next_for_agent(other) is None
        assert queue.next_for_agent(agent) == envelope


def test_server_signs_validated_signal_without_exposing_signing_key(monkeypatch, tmp_path):
    from app.agent_auth import SignedEnvelope, verify_envelope
    tenant, agent = str(uuid4()), str(uuid4())
    path = str(tmp_path / "queue.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_TENANT_ID", tenant)
    monkeypatch.setenv("DEMO_COMMAND_SUBMIT_TOKEN_SHA256",
                       hashlib.sha256(b"submit-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_SIGNING_KEY_HEX", KEY.hex())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_COMMAND_AGENT_LOGIN", "123")
    monkeypatch.setenv("DEMO_COMMAND_AGENT_SERVER", "Demo")
    with CommandQueue(path) as queue:
        queue.enroll_agent(agent, tenant)

    client = TestClient(app)
    url = "/v1/dev/tenants/commands/from-signal"
    headers = {"Authorization": "Bearer submit-secret"}
    body = {
        "agent_id": agent,
        "request_id": str(uuid4()),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "text": "BUY XAUUSD CMP 4042.8\\nSL: 4037\\nTP-1: 4056\\nTP-2: 4082",
    }
    response = client.post(url, headers=headers, json=body)
    assert response.status_code == 202
    assert "signature" not in response.json()
    assert "payload" not in response.json()
    command_id = response.json()["command_id"]
    assert client.post(url, headers=headers, json=body).json()["command_id"] == command_id
    assert client.post(url, headers=headers,
                       json=dict(body, text="SELL XAUUSD CMP 4042.8\\nSL: 4050\\nTP-1: 4030\\nTP-2: 4020")).status_code == 409
    with CommandQueue(path) as queue:
        envelope = queue.next_for_agent(agent)
        assert envelope["command_id"] == command_id
        payload = verify_envelope(SignedEnvelope.model_validate(envelope), KEY)
        assert payload["tenant_id"] == tenant
        assert payload["expected_login"] == 123
        assert payload["expected_server"] == "Demo"
        assert payload["signal"]["symbol"] == "XAUUSD"
        assert payload["broker"]["is_demo"] is False


def test_server_signed_submission_requires_enrollment_and_valid_signal(
    monkeypatch, tmp_path
):
    tenant, agent = str(uuid4()), str(uuid4())
    path = str(tmp_path / "queue.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_TENANT_ID", tenant)
    monkeypatch.setenv("DEMO_COMMAND_SUBMIT_TOKEN_SHA256",
                       hashlib.sha256(b"submit-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_SIGNING_KEY_HEX", KEY.hex())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_COMMAND_AGENT_LOGIN", "123")
    monkeypatch.setenv("DEMO_COMMAND_AGENT_SERVER", "Demo")
    client = TestClient(app)
    url = "/v1/dev/tenants/commands/from-signal"
    headers = {"Authorization": "Bearer submit-secret"}
    good = {"agent_id": agent,
            "request_id": str(uuid4()),
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "text": "BUY XAUUSD CMP 4042.8\\nSL: 4037\\nTP-1: 4056\\nTP-2: 4082"}
    assert client.post(url, headers=headers, json=good).status_code == 409
    assert client.post(url, headers=headers,
                       json=dict(good, text="garbage")).status_code == 422
    with CommandQueue(path) as queue:
        assert queue.next_for_agent(agent) is None
