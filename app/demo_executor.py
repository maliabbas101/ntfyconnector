"""Explicitly armed, demo-account-only MT5 order submission.

NOT wired into HTTP polling. The caller must authenticate the signed command
and pin the agent identity before invoking this function. No automatic retry.
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.agent_journal import CommandConflict
from app.agent_preflight import preflight_demo_signal
from app.mt5_guard import AccountVerificationError, verify_demo_account


def execute_demo_once(command, journal, mt5, *, armed: bool = False) -> dict:
    """Submit at most one demo order; persist uncertainty BEFORE order_send.

    An ambiguous broker response is intentionally not retried. The returned
    EXECUTION_UNKNOWN is a reconciliation obligation, not confirmation of fill.
    """
    cid = command.command_id
    if not armed:
        return {"command_id": cid, "state": "NOT_ARMED",
                "execution_enabled": False}

    # Durable idempotency comes before any side effect.
    state = journal.receive(cid, command.model_dump(mode="json"))
    if state != "RECEIVED":
        return {"command_id": cid, "state": state,
                "duplicate": True, "execution_enabled": False}

    def reject(reason):
        journal.reject(cid, reason)
        return {"command_id": cid, "state": "REJECTED",
                "reason": reason, "execution_enabled": False}

    if command.expires_at <= datetime.now(timezone.utc):
        return reject("EXPIRED")
    try:
        account = verify_demo_account(
            mt5, expected_login=command.expected_login,
            expected_server=command.expected_server)
        preflight = preflight_demo_signal(
            mt5, command.signal, command.policy,
            expected_login=command.expected_login,
            expected_server=command.expected_server)
        if not preflight.approved_for_review or preflight.volume is None:
            return reject("BROKER_PREFLIGHT_FAILED")
        tick = mt5.symbol_info_tick(command.signal.symbol)
        if tick is None:
            return reject("QUOTE_UNAVAILABLE")
        entry = Decimal(str(tick.ask if command.signal.side == "BUY" else tick.bid))
        if not entry.is_finite() or entry <= 0:
            return reject("INVALID_QUOTE")
        # Refuse price drift from the signed signal. Never silently chase price.
        if abs(entry - command.signal.reference_price) > command.policy.max_spread:
            return reject("PRICE_DRIFT")
        if command.signal.side == "BUY":
            if not (command.signal.stop_loss < entry < command.signal.take_profit_1):
                return reject("INVALID_STOPS")
            order_type = mt5.ORDER_TYPE_BUY
        else:
            if not (command.signal.take_profit_1 < entry < command.signal.stop_loss):
                return reject("INVALID_STOPS")
            order_type = mt5.ORDER_TYPE_SELL

        # Recalculate worst-case stop loss using the FINAL price and volume.
        # Preflight may have used an earlier quote; never spend beyond budget.
        stop_result = mt5.order_calc_profit(
            order_type, command.signal.symbol, float(preflight.volume),
            float(entry), float(command.signal.stop_loss))
        if stop_result is None:
            return reject("FINAL_RISK_UNAVAILABLE")
        stop_loss_amount = Decimal(str(stop_result))
        risk_budget = Decimal(account.equity) * command.policy.max_risk_fraction
        if (not stop_loss_amount.is_finite() or stop_loss_amount >= 0
                or -stop_loss_amount > risk_budget):
            return reject("FINAL_RISK_EXCEEDED")
        # Detect changes between quote/preflight and the last safe point.
        if verify_demo_account(
            mt5, expected_login=command.expected_login,
            expected_server=command.expected_server) != account:
            return reject("ACCOUNT_CHANGED")
        if command.expires_at <= datetime.now(timezone.utc):
            return reject("EXPIRED")
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": command.signal.symbol,
            "volume": float(preflight.volume),
            "type": order_type,
            "price": float(entry),
            "sl": float(command.signal.stop_loss),
            "tp": float(command.signal.take_profit_1),
            "deviation": 0,
            "comment": "ntfy-" + cid.replace("-", "")[:24],
        }
        check = mt5.order_check(request)
        if check is None or getattr(check, "retcode", None) != 0:
            return reject("BROKER_ORDER_CHECK_FAILED")
        if verify_demo_account(
            mt5, expected_login=command.expected_login,
            expected_server=command.expected_server) != account:
            return reject("ACCOUNT_CHANGED")
    except (AccountVerificationError, AttributeError, TypeError, ValueError,
            ArithmeticError):
        return reject("BROKER_PREFLIGHT_UNAVAILABLE")

    # There MUST be no additional broker request after uncertain state begins,
    # except this single order_send. Never infer a fill from its return value.
    journal.mark_execution_unknown(cid)
    try:
        mt5.order_send(request)
    except Exception:
        pass
    return {"command_id": cid, "state": "EXECUTION_UNKNOWN",
            "reason": "BROKER_RECONCILIATION_REQUIRED",
            "execution_enabled": True}
