"""Crash-safe local command journal for a future customer-hosted MT5 agent.

Commands are never automatically retried after an ambiguous execution attempt.
This module does not submit broker orders.
"""
import json
import sqlite3
from pathlib import Path
from uuid import UUID

class CommandConflict(ValueError):
    pass

class CommandJournal:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=10)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS commands ("
                        "command_id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                        "state TEXT NOT NULL CHECK(state IN "
                        "('RECEIVED','REJECTED','EXECUTION_UNKNOWN','RECONCILED')), "
                        "result TEXT)")
        self.db.commit()

    def receive(self, command_id: str, payload: dict) -> str:
        command_id = str(UUID(command_id))
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO commands(command_id,payload,state) "
                            "VALUES(?,?,'RECEIVED')", (command_id, serialized))
            row = self.db.execute("SELECT payload,state FROM commands WHERE command_id=?",
                                  (command_id,)).fetchone()
            if row[0] != serialized:
                raise CommandConflict("Command ID reused with a different payload")
            return row[1]

    def mark_execution_unknown(self, command_id: str) -> None:
        """Persist uncertainty *before* any external broker request is attempted."""
        with self.db:
            result = self.db.execute(
                "UPDATE commands SET state='EXECUTION_UNKNOWN' "
                "WHERE command_id=? AND state='RECEIVED'", (str(UUID(command_id)),))
            if result.rowcount != 1:
                raise CommandConflict("Command cannot enter execution-unknown state")

    def reject(self, command_id: str, reason: str) -> None:
        with self.db:
            result = self.db.execute(
                "UPDATE commands SET state='REJECTED', result=? "
                "WHERE command_id=? AND state='RECEIVED'",
                (reason, str(UUID(command_id))))
            if result.rowcount != 1:
                raise CommandConflict("Command cannot be rejected from its current state")

    def reconcile(self, command_id: str, broker_evidence: str) -> None:
        if not broker_evidence:
            raise ValueError("Broker evidence is required")
        with self.db:
            result = self.db.execute(
                "UPDATE commands SET state='RECONCILED', result=? "
                "WHERE command_id=? AND state='EXECUTION_UNKNOWN'",
                (broker_evidence, str(UUID(command_id))))
            if result.rowcount != 1:
                raise CommandConflict("Only uncertain commands can be reconciled")

    def get(self, command_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT payload,state,result FROM commands WHERE command_id=?",
            (str(UUID(command_id)),)).fetchone()
        if row is None:
            return None
        return {"payload": json.loads(row[0]), "state": row[1], "result": row[2]}

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
