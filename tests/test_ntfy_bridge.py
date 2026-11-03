import json
import pytest
from app.ntfy_bridge import normalize_ntfy_line, require_https

def test_normalize_message():
    line = json.dumps({"id": "ntfy-123", "event": "message", "topic": "alerts", "message": "BUY XAUUSD CMP 4042.8"})
    assert normalize_ntfy_line(line, "alerts") == {"external_id": "ntfy-123", "text": "BUY XAUUSD CMP 4042.8"}

@pytest.mark.parametrize("payload", [
    {"event": "open", "topic": "alerts"},
    {"id": "1", "event": "message", "topic": "other", "message": "hello"},
    {"id": "1", "event": "message", "topic": "alerts", "message": ""},
    {"id": "1", "event": "message", "topic": "alerts", "message": "x" * 8193},
])
def test_ignore_non_message_events(payload):
    assert normalize_ntfy_line(json.dumps(payload), "alerts") is None

def test_invalid_json():
    assert normalize_ntfy_line("not-json", "alerts") is None

def test_https_required():
    assert require_https("https://ntfy.sh/") == "https://ntfy.sh"
    with pytest.raises(ValueError):
        require_https("http://example.com")
    assert require_https("http://localhost:8000", allow_local_http=True) == "http://localhost:8000"
