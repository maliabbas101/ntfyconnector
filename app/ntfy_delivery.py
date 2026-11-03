"""Delivery semantics for forwarding ntfy events to ingestion.

A notification is acknowledged only when ingestion confirms persistence.
"""
import httpx

class PermanentDeliveryError(RuntimeError):
    """Operator intervention required; do not advance the cursor."""

def forward_event(client: httpx.Client, destination: str, token: str,
                  payload: dict, cursor) -> None:
    response = client.post(
        destination,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code in (400, 401, 403, 404, 413, 422):
        raise PermanentDeliveryError(
            f"Ingestion rejected notification with HTTP {response.status_code}"
        )
    response.raise_for_status()
    if response.status_code != 202:
        raise PermanentDeliveryError(
            f"Unexpected ingestion success status: HTTP {response.status_code}"
        )
    try:
        receipt = response.json()
    except ValueError as exc:
        raise PermanentDeliveryError("Ingestion returned a malformed receipt") from exc
    if not isinstance(receipt, dict) or receipt.get("execution_enabled") is not False:
        raise PermanentDeliveryError("Ingestion receipt lacks dry-run confirmation")
    if not isinstance(receipt.get("event_id"), str) or not receipt["event_id"]:
        raise PermanentDeliveryError("Ingestion receipt lacks event ID")
    if receipt.get("status") not in {"VALIDATED", "REJECTED"}:
        raise PermanentDeliveryError("Ingestion receipt has unexpected status")
    cursor.acknowledge(payload["external_id"])
