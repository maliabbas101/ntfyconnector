"""Delivery semantics for forwarding ntfy events to ingestion.

Do not acknowledge events after a failed response.
"""
import httpx

class PermanentDeliveryError(RuntimeError):
    """Configuration/authentication error that requires operator intervention."""

def forward_event(client: httpx.Client, destination: str, token: str,
                  payload: dict, cursor) -> None:
    try:
        response = client.post(
            destination,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError:
        raise
    if response.status_code in (401, 403, 404, 422):
        raise PermanentDeliveryError(
            f"Ingestion rejected notification with HTTP {response.status_code}"
        )
    response.raise_for_status()
    cursor.acknowledge(payload["external_id"])
