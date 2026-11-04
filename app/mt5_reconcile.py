"""Read-only broker-history candidates for manually reconciling demo orders.

Absence of a matching deal is never proof that no order executed.
Matching broker comments alone are not sufficient to automatically reconcile.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.mt5_guard import verify_demo_account


class ReconciliationUnavailable(RuntimeError):
    pass


def inspect_uncertain_demo_order(
    mt5, journal, command_id: str, *,
    expected_login: int, expected_server: str,
    lookback_days: int = 7,
) -> dict:
    """Collect candidate broker deal IDs; NEVER mutate the journal or send orders."""
    command_id = str(UUID(command_id))
    if not 1 <= lookback_days <= 30:
        raise ValueError("History window must be between 1 and 30 days")
    local = journal.get(command_id)
    if local is None or local["state"] != "EXECUTION_UNKNOWN":
        raise ReconciliationUnavailable("Only uncertain journal entries can be inspected")
    payload = local["payload"]
    if (payload.get("expected_login") != expected_login or
            payload.get("expected_server") != expected_server):
        raise ReconciliationUnavailable("Journal account identity differs from local pin")
    signal = payload.get("signal")
    if not isinstance(signal, dict) or signal.get("symbol") != "XAUUSD":
        raise ReconciliationUnavailable("Unsupported local journal signal")

    before = verify_demo_account(
        mt5, expected_login=expected_login, expected_server=expected_server)
    now = datetime.now(timezone.utc)
    # MT5 history methods are read-only. Do not call order_send, order_check,
    # order_get or account switching functions during this inspection.
    try:
        deals = mt5.history_deals_get(now - timedelta(days=lookback_days), now)
    except Exception as exc:
        raise ReconciliationUnavailable("Broker deal history unavailable") from exc
    if deals is None:
        raise ReconciliationUnavailable("Broker deal history unavailable")
    after = verify_demo_account(
        mt5, expected_login=expected_login, expected_server=expected_server)
    if after != before:
        raise ReconciliationUnavailable("Demo account changed during inspection")
    comment = "ntfy-" + command_id.replace("-", "")[:24]
    candidates = []
    for deal in deals:
        if getattr(deal, "comment", None) != comment:
            continue
        if getattr(deal, "symbol", None) != signal["symbol"]:
            continue
        ticket = getattr(deal, "ticket", None)
        order = getattr(deal, "order", None)
        if not isinstance(ticket, int) or ticket <= 0:
            continue
        candidates.append({"deal_ticket": ticket,
                           "order_ticket": order if isinstance(order, int) else None})
    return {
        "command_id": command_id,
        "journal_state": "EXECUTION_UNKNOWN",
        "candidate_deals": candidates,
        "candidate_count": len(candidates),
        "needs_operator_review": True,
        "absence_is_not_proof_of_no_execution": True,
        "execution_enabled": False,
    }
