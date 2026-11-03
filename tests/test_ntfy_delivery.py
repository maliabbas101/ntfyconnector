import httpx
import pytest
from app.ntfy_delivery import forward_event, PermanentDeliveryError

class Cursor:
    def __init__(self):
        self.last = None
    def acknowledge(self, event_id):
        self.last = event_id

def client_with_status(status):
    return httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, request=request, json={
            "event_id": "stored-1", "status": "VALIDATED",
            "duplicate": False, "execution_enabled": False,
        })
    ))

def test_acknowledge_only_after_success():
    cursor = Cursor()
    with client_with_status(202) as client:
        forward_event(client, "https://api.example.com/ingest", "token",
                      {"external_id": "id-1", "text": "BUY"}, cursor)
    assert cursor.last == "id-1"

@pytest.mark.parametrize("status", [401, 403, 404, 422])
def test_permanent_error_does_not_acknowledge(status):
    cursor = Cursor()
    with client_with_status(status) as client:
        with pytest.raises(PermanentDeliveryError):
            forward_event(client, "https://api.example.com/ingest", "token",
                          {"external_id": "id-1", "text": "BUY"}, cursor)
    assert cursor.last is None

@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_response_does_not_acknowledge(status):
    cursor = Cursor()
    with client_with_status(status) as client:
        with pytest.raises(httpx.HTTPStatusError):
            forward_event(client, "https://api.example.com/ingest", "token",
                          {"external_id": "id-1", "text": "BUY"}, cursor)
    assert cursor.last is None

@pytest.mark.parametrize("receipt", [
    {},
    {"event_id": "stored-1", "status": "VALIDATED", "execution_enabled": True},
    {"event_id": "stored-1", "status": "UNKNOWN", "execution_enabled": False},
    {"event_id": "", "status": "VALIDATED", "execution_enabled": False},
])
def test_invalid_receipt_never_advances_cursor(receipt):
    cursor = Cursor()
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(202, json=receipt, request=request)
    )) as client:
        with pytest.raises(PermanentDeliveryError):
            forward_event(client, "https://api.example.com/ingest", "token",
                          {"external_id": "id-1", "text": "BUY"}, cursor)
    assert cursor.last is None

def test_unexpected_2xx_never_advances_cursor():
    cursor = Cursor()
    with client_with_status(200) as client:
        with pytest.raises(PermanentDeliveryError):
            forward_event(client, "https://api.example.com/ingest", "token",
                          {"external_id": "id-1", "text": "BUY"}, cursor)
    assert cursor.last is None
