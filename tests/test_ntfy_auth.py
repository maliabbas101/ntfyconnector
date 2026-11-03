import pytest
from app.ntfy_auth import subscription_headers

def test_private_topic_authentication():
    assert subscription_headers("private-token") == {"Authorization": "Bearer private-token"}

def test_public_topic_has_no_auth_header(monkeypatch):
    monkeypatch.delenv("NTFY_ACCESS_TOKEN", raising=False)
    assert subscription_headers() == {}

def test_token_from_environment(monkeypatch):
    monkeypatch.setenv("NTFY_ACCESS_TOKEN", "from-env")
    assert subscription_headers() == {"Authorization": "Bearer from-env"}

@pytest.mark.parametrize("token", [" ", "\nmalicious", "bad\rheader"])
def test_invalid_tokens_rejected(token):
    with pytest.raises(ValueError):
        subscription_headers(token)
