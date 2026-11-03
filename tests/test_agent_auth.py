from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.agent_auth import (SignedEnvelope, AuthenticationError,
                            sign_command, verify_envelope)

KEY = b"a" * 32
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

def envelope(payload=None, expires=None):
    command_id = str(uuid4())
    expires = expires or NOW + timedelta(minutes=2)
    payload = payload or {"symbol": "XAUUSD", "side": "BUY"}
    signature = sign_command(KEY, command_id, expires, payload)
    return SignedEnvelope(command_id=command_id, expires_at=expires,
                          payload=payload, signature=signature)

def test_valid_signature():
    signed = envelope()
    assert verify_envelope(signed, KEY, now=NOW)["symbol"] == "XAUUSD"

def test_modified_payload_rejected():
    signed = envelope()
    signed.payload["side"] = "SELL"
    with pytest.raises(AuthenticationError):
        verify_envelope(signed, KEY, now=NOW)

def test_expired_rejected():
    signed = envelope()
    with pytest.raises(AuthenticationError):
        verify_envelope(signed, KEY, now=NOW + timedelta(minutes=3))

def test_wrong_key_rejected():
    with pytest.raises(AuthenticationError):
        verify_envelope(envelope(), b"b" * 32, now=NOW)

def test_short_key_rejected():
    with pytest.raises(ValueError):
        sign_command(b"short", str(uuid4()), NOW, {"x": 1})

def test_timezone_normalization():
    signed = envelope()
    assert verify_envelope(signed, KEY, now=NOW + timedelta(seconds=1))
