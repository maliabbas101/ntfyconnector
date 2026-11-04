"""Windows MT5 agent one-shot CLI; safe by default and no automatic retries.

Install MetaTrader5 separately on the Windows host and sign in to the
specific demo account. Explicit arming requires BOTH a CLI flag and env opt-in.
"""
import argparse
import os
import sys

import httpx

from app.agent_identity import AgentIdentity
from app.agent_journal import CommandJournal
from app.agent_transport import poll_once


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Process one signed demo command")
    parser.add_argument("--arm-demo", action="store_true",
                        help="allow one demo-only order attempt after all checks")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("MT5 agent requires a Windows host")
    arm = args.arm_demo and os.getenv("DEMO_ORDER_EXECUTION_ENABLED") == (
        "YES_I_ACCEPT_DEMO_ONLY")
    if args.arm_demo and not arm:
        parser.error("Explicit DEMO_ORDER_EXECUTION_ENABLED opt-in required")
    endpoint = os.environ["AGENT_API_URL"]
    token = os.environ["AGENT_TOKEN"]
    key = bytes.fromhex(os.environ["AGENT_SIGNING_KEY_HEX"])
    identity = AgentIdentity(
        agent_id=os.environ["AGENT_ID"],
        tenant_id=os.environ["AGENT_TENANT_ID"],
        expected_login=int(os.environ["MT5_DEMO_LOGIN"]),
        expected_server=os.environ["MT5_DEMO_SERVER"])
    journal_path = os.environ["AGENT_JOURNAL_PATH"]
    if not journal_path or journal_path == ":memory:":
        parser.error("A persistent AGENT_JOURNAL_PATH is required")
    import MetaTrader5 as mt5  # only available on the Windows machine
    if not mt5.initialize():
        parser.error("Could not initialize MT5 terminal")
    try:
        with CommandJournal(journal_path) as journal:
            with httpx.Client(trust_env=False) as client:
                result = poll_once(
                    endpoint=endpoint, agent_token=token, signing_secret=key,
                    journal=journal, mt5=mt5, client=client,
                    identity=identity, arm_demo_execution=arm)
        # Never print credentials, full command payload, or order numbers.
        print("Agent outcome:", result["status"])
        return 0 if result["status"] in ("EMPTY", "ACKNOWLEDGED",
                                         "UNACKNOWLEDGED") else 2
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
