from datetime import datetime, timedelta, timezone
from uuid import uuid4
import httpx
import pytest
from app.agent_journal import CommandJournal
from app.agent_transport import (TransportConfigurationError,
                                 validate_agent_endpoint, poll_once)

def test_https_endpoint_validation():
    assert validate_agent_endpoint("https://agent.example.com/") == "https://agent.example.com"
    for url in ("http://agent.example.com", "https://user:pass@agent.example.com",
                "https://agent.example.com:8443", "https://agent.example.com?token=x",
                "https://agent.example.com/#fragment"):
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
                               journal=journal, mt5=object(), client=client)
            assert result == {"status": "EMPTY", "execution_enabled": False}

def test_redirect_not_followed(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://attacker.example.com/"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with CommandJournal(str(tmp_path / "journal.db")) as journal:
            with pytest.raises(httpx.HTTPStatusError):
                poll_once(endpoint="https://agent.example.com",
                          agent_token="agent-token", signing_secret=b"x"*32,
                          journal=journal, mt5=object(), client=client)
