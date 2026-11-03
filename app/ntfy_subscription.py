"""Classify subscription failures without exposing credentials."""
import httpx

class PermanentSubscriptionError(RuntimeError):
    """The ntfy subscription cannot recover without configuration changes."""

def validate_subscription_response(response: httpx.Response) -> None:
    if response.status_code in {400, 401, 403, 404, 410, 422}:
        raise PermanentSubscriptionError(
            f"ntfy subscription rejected with HTTP {response.status_code}"
        )
    response.raise_for_status()
    if response.status_code != 200:
        raise PermanentSubscriptionError(
            f"Unexpected ntfy subscription status HTTP {response.status_code}"
        )
