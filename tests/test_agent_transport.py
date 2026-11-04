from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
import pytest
from app.agent_identity import AgentIdentity
from app.agent_journal import CommandJournal
from app.agent_transport import (TransportConfigurationError,
                                 validate_agent_endpoint, poll_once, recover_terminal_receipt)

IDENTITY = AgentIdentity(str(uuid4()), str(uuid4()), 123, "Demo")

def test_https_endpoint_validation():
    assert validate_agent_endpoint("https://agent.example.com/") == "https://agent.example.com"
    for url in ("http://agent.example.com", "https://user:pass@agent.example.com",
                "https://agent.example.com:8443", "https://agent.example.com?token=x",
                "https://agent.example.com/#fragment",
                "https://agent.example.com:invalid",
                "https://agent.example.com:99999",
                "https://[broken",
                "https://agent.example.com/other",
                "https://agent.example.com//other"):
        with pytest.raises(TransportConfigurationError):
            validate_agent_endpoint(url)

def test_empty_poll_never_touches_terminal(tmp_path):
    def handler(request):
        assert request.url.scheme == "https"
        assert request.headers["Authorization"] == "Bearer agent-token"
        return httpx.Response(204)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            result = poll_once(endpoint="https://agent.example.com",
                               agent_token="agent-token", signing_secret=b"x"*32,
                               journal=journal, mt5=object(), client=client,
                               identity=IDENTITY)
            assert result == {"status": "EMPTY", "execution_enabled": False}

def test_redirect_not_followed(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://attacker.example.com/"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            with pytest.raises(httpx.HTTPStatusError):
                poll_once(endpoint="https://agent.example.com",
                          agent_token="agent-token", signing_secret=b"x"*32,
                          journal=journal, mt5=object(), client=client,
                          identity=IDENTITY)


def test_missing_identity_or_short_key_never_contacts_server(tmp_path):
    def handler(request):
        raise AssertionError("Configuration must be checked before network access")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            base = dict(endpoint="https://agent.example.com", agent_token="token",
                        journal=journal, mt5=object(), client=client)
            with pytest.raises(TransportConfigurationError):
                poll_once(**base, signing_secret=b"x" * 32)
            with pytest.raises(TransportConfigurationError):
                poll_once(**base, signing_secret=b"short", identity=IDENTITY)


def test_recovery_rejects_receipt_without_disabled_execution_flag(tmp_path):
    command_id = str(uuid4())
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={
            "status": "DELIVERED", "journal_state": None,
            "execution_enabled": True})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            journal.receive(command_id, {"test": True})
            journal.reject(command_id, "PREFLIGHT_FAILED")
            with pytest.raises(RuntimeError, match="safety flag"):
                recover_terminal_receipt(
                    endpoint="https://agent.example.com",
                    agent_token="agent-token", journal=journal,
                    command_id=command_id, client=client)
    assert calls == ["GET"]


def test_recovery_invalid_command_id_never_contacts_server(tmp_path):
    def handler(request):
        raise AssertionError("Invalid command ID must fail before HTTP")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            with pytest.raises(ValueError):
                recover_terminal_receipt(
                    endpoint="https://agent.example.com",
                    agent_token="agent-token", journal=journal,
                    command_id="not-a-uuid", client=client)


def test_recovery_unconfigured_token_never_contacts_server(tmp_path):
    def handler(request):
        raise AssertionError("Missing token must fail before HTTP")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            with pytest.raises(TransportConfigurationError, match="token"):
                recover_terminal_receipt(
                    endpoint="https://agent.example.com",
                    agent_token="", journal=journal,
                    command_id=str(uuid4()), client=client)


def test_recovery_unknown_local_command_never_contacts_server(tmp_path):
    def handler(request):
        raise AssertionError("Unknown local command must not contact server")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            result = recover_terminal_receipt(
                endpoint="https://agent.example.com",
                agent_token="agent-token", journal=journal,
                command_id=str(uuid4()), client=client)
            assert result == {
                "status": "MANUAL_RECONCILIATION_REQUIRED",
                "execution_enabled": False}
