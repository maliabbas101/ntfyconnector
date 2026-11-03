import httpx
import pytest
from app.ntfy_subscription import (
    PermanentSubscriptionError, validate_subscription_response,
)

@pytest.mark.parametrize("code", [400, 401, 403, 404, 410, 422])
def test_permanent_subscription_failure(code):
    response = httpx.Response(code, request=httpx.Request("GET", "https://ntfy.sh/t/json"))
    with pytest.raises(PermanentSubscriptionError, match=str(code)):
        validate_subscription_response(response)

@pytest.mark.parametrize("code", [429, 500, 503])
def test_transient_subscription_failure(code):
    response = httpx.Response(code, request=httpx.Request("GET", "https://ntfy.sh/t/json"))
    with pytest.raises(httpx.HTTPStatusError):
        validate_subscription_response(response)

def test_success():
    response = httpx.Response(200, request=httpx.Request("GET", "https://ntfy.sh/t/json"))
    validate_subscription_response(response)

def test_unexpected_success_status():
    response = httpx.Response(204, request=httpx.Request("GET", "https://ntfy.sh/t/json"))
    with pytest.raises(PermanentSubscriptionError):
        validate_subscription_response(response)
