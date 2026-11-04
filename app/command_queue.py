"""Durable, non-executing agent command queue.

SQLite implementation for local development; no automatic trade creation.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

class QueueConflict(ValueError):
    pass

class CommandQueue:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS agent_commands (
            command_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            envelope TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING','DELIVERED','ACKNOWLEDGED','EXPIRED')),
            delivered_at TEXT
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_agent_commands_pending ON "
                        "agent_commands(agent_id,status,expires_at)")

    def enqueue(self, agent_id: str, envelope: dict) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id required")
        command_id = str(UUID(envelope["command_id"]))
        expiry = datetime.fromisoformat(envelope["expires_at"])
        if expiry.tzinfo is None or expiry.utcoffset() is None:
            raise ValueError("Timezone-aware expiry required")
        serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                                allow_nan=False)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT OR IGNORE INTO agent_commands "
                "(command_id,agent_id,envelope,expires_at,status) VALUES (?,?,?,?,'PENDING')",
                (command_id, agent_id, serialized,
                 expiry.astimezone(timezone.utc).isoformat()))
            row = self.db.execute(
                "SELECT agent_id,envelope FROM agent_commands WHERE command_id=?",
                (command_id,)).fetchone()
            if row != (agent_id, serialized):
                raise QueueConflict("Command ID reused with different content or agent")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def next_for_agent(self, agent_id: str, *, now: datetime | None = None) -> dict | None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Timezone-aware time required")
        timestamp = current.astimezone(timezone.utc).isoformat()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "UPDATE agent_commands SET status='EXPIRED' "
                "WHERE agent_id=? AND status='PENDING' AND expires_at<=?",
                (agent_id, timestamp))
            row = self.db.execute(
                "SELECT command_id,envelope FROM agent_commands "
                "WHERE agent_id=? AND status='PENDING' AND expires_at>? "
                "ORDER BY expires_at,command_id LIMIT 1",
                (agent_id, timestamp)).fetchone()
            if row is None:
                self.db.commit()
                return None
            self.db.execute(
                "UPDATE agent_commands SET status='DELIVERED',delivered_at=? "
                "WHERE command_id=? AND status='PENDING'",
                (timestamp, row[0]))
            self.db.commit()
            return json.loads(row[1])
        except BaseException:
            self.db.rollback()
            raise

    def recover_unacknowledged(self, agent_id: str, *, now: datetime | None = None,
                               min_age_seconds: int = 60) -> list[str]:
        """List uncertain deliveries for manual reconciliation; never requeue.

        A lost GET response is indistinguishable from a command received by an
        agent that later lost its ACK. Neither case permits blind redelivery.
        """
        if min_age_seconds < 1:
            raise ValueError("min_age_seconds must be positive")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Timezone-aware time required")
        cutoff = (current.astimezone(timezone.utc)
                  - timedelta(seconds=min_age_seconds)).isoformat()
        rows = self.db.execute(
            "SELECT command_id FROM agent_commands "
            "WHERE agent_id=? AND status='DELIVERED' AND delivered_at<=? "
            "ORDER BY delivered_at,command_id",
            (agent_id, cutoff)).fetchall()
        return [row[0] for row in rows]

    def acknowledge(self, agent_id: str, command_id: str) -> bool:
        command_id = str(UUID(command_id))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = self.db.execute(
                "UPDATE agent_commands SET status='ACKNOWLEDGED' "
                "WHERE agent_id=? AND command_id=? AND status='DELIVERED'",
                (agent_id, command_id))
            if result.rowcount == 1:
                self.db.commit()
                return True
            # A lost HTTP response must not make an already-durable ACK fail.
            # Do not acknowledge PENDING or EXPIRED commands.
            row = self.db.execute(
                "SELECT status FROM agent_commands WHERE agent_id=? AND command_id=?",
                (agent_id, command_id)).fetchone()
            self.db.commit()
            return row is not None and row[0] == "ACKNOWLEDGED"
        except BaseException:
            self.db.rollback()
            raise

    def status(self, command_id: str) -> str | None:
        row = self.db.execute("SELECT status FROM agent_commands WHERE command_id=?",
                              (str(UUID(command_id)),)).fetchone()
        return row[0] if row else None

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
