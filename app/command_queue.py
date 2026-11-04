"""Durable, non-executing agent command queue.

SQLite implementation for local development; no automatic trade creation.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
from app.agent_auth import SignedEnvelope, verify_envelope

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
        self.db.execute("""CREATE TABLE IF NOT EXISTS agent_command_reports (
            command_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL,
            journal_state TEXT NOT NULL CHECK(journal_state IN
                ('RECEIVED','REJECTED','EXECUTION_UNKNOWN','RECONCILED')),
            reported_at TEXT NOT NULL
        )""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS agent_enrollments (
            agent_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_agent_commands_pending ON "
                        "agent_commands(agent_id,status,expires_at)")

    def enroll_agent(self, agent_id: str, tenant_id: str) -> None:
        """Explicit development enrollment; cannot transfer an existing agent."""
        agent_id, tenant_id = str(UUID(agent_id)), str(UUID(tenant_id))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT OR IGNORE INTO agent_enrollments(agent_id,tenant_id) VALUES (?,?)",
                (agent_id, tenant_id))
            row = self.db.execute(
                "SELECT tenant_id FROM agent_enrollments WHERE agent_id=?",
                (agent_id,)).fetchone()
            if row[0] != tenant_id:
                raise QueueConflict("Agent already belongs to another tenant")
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def enqueue_bound(self, agent_id: str, tenant_id: str,
                      envelope: dict, signing_secret: bytes) -> None:
        """Require enrollment and authenticated tenant/agent routing.

        The legacy enqueue method remains for development fixtures only.
        """
        agent_id, tenant_id = str(UUID(agent_id)), str(UUID(tenant_id))
        signed = SignedEnvelope.model_validate(envelope)
        payload = verify_envelope(signed, signing_secret)
        if payload.get("agent_id") != agent_id or payload.get("tenant_id") != tenant_id:
            raise QueueConflict("Signed command identity does not match routing")
        if payload.get("command_id") != signed.command_id:
            raise QueueConflict("Signed command ID mismatch")
        try:
            payload_expiry = datetime.fromisoformat(str(payload.get("expires_at")))
        except (ValueError, TypeError) as exc:
            raise QueueConflict("Invalid signed command expiry") from exc
        if payload_expiry.tzinfo is None or payload_expiry.utcoffset() is None:
            raise QueueConflict("Signed command expiry must be timezone-aware")
        if payload_expiry != signed.expires_at:
            raise QueueConflict("Signed command expiry mismatch")
        row = self.db.execute(
            "SELECT tenant_id FROM agent_enrollments WHERE agent_id=?",
            (agent_id,)).fetchone()
        if row is None or row[0] != tenant_id:
            raise QueueConflict("Agent not enrolled in tenant")
        self.enqueue(agent_id, envelope)

    def enqueue(self, agent_id: str, envelope: dict) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id required")
        command_id = str(UUID(envelope["command_id"]))
        # Defense in depth: do not route a signed payload to a different
        # agent, even if an upstream producer selected the wrong queue.
        payload = envelope.get("payload")
        if isinstance(payload, dict) and "agent_id" in payload:
            if payload["agent_id"] != agent_id:
                raise QueueConflict("Signed payload agent differs from queue owner")
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
                 expiry.astimezone(timezone.utc).isoformat(timespec="microseconds")))
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
        timestamp = current.astimezone(timezone.utc).isoformat(timespec="microseconds")
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
                  - timedelta(seconds=min_age_seconds)).isoformat(timespec="microseconds")
        rows = self.db.execute(
            "SELECT command_id FROM agent_commands "
            "WHERE agent_id=? AND status='DELIVERED' AND delivered_at<=? "
            "ORDER BY delivered_at,command_id",
            (agent_id, cutoff)).fetchall()
        return [row[0] for row in rows]

    def acknowledge_reported(self, agent_id: str, command_id: str) -> bool:
        """ACK only a delivered command with a terminal agent journal claim.

        This does not verify broker execution and does not redeliver commands.
        """
        command_id = str(UUID(command_id))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT c.status, r.journal_state FROM agent_commands c "
                "LEFT JOIN agent_command_reports r "
                "ON r.command_id=c.command_id AND r.agent_id=c.agent_id "
                "WHERE c.agent_id=? AND c.command_id=?",
                (agent_id, command_id)).fetchone()
            if row is None:
                self.db.commit()
                return False
            status, reported = row
            # Legacy queue.acknowledge() can mark a delivery acknowledged
            # without an agent journal report. Never treat that as a valid
            # reported acknowledgment in the agent-facing protocol.
            if status == "ACKNOWLEDGED":
                self.db.commit()
                return reported in ("REJECTED", "RECONCILED")
            if status != "DELIVERED" or reported not in ("REJECTED", "RECONCILED"):
                self.db.commit()
                return False
            self.db.execute(
                "UPDATE agent_commands SET status='ACKNOWLEDGED' "
                "WHERE agent_id=? AND command_id=? AND status='DELIVERED'",
                (agent_id, command_id))
            self.db.commit()
            return True
        except BaseException:
            self.db.rollback()
            raise

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

    def report_journal_state(self, agent_id: str, command_id: str,
                             journal_state: str) -> bool:
        """Store an authenticated claim, not proof of broker execution."""
        command_id = str(UUID(command_id))
        allowed = {"RECEIVED", "REJECTED", "EXECUTION_UNKNOWN", "RECONCILED"}
        if journal_state not in allowed:
            raise ValueError("Invalid journal state")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT status FROM agent_commands WHERE agent_id=? AND command_id=?",
                (agent_id, command_id)).fetchone()
            if row is None or row[0] not in ("DELIVERED", "ACKNOWLEDGED"):
                self.db.commit()
                return False
            old_row = self.db.execute(
                "SELECT journal_state FROM agent_command_reports WHERE command_id=?",
                (command_id,)).fetchone()
            old = old_row[0] if old_row else None
            if old == journal_state:
                self.db.commit()
                return True
            transitions = {
                None: {"RECEIVED", "REJECTED", "EXECUTION_UNKNOWN"},
                "RECEIVED": {"REJECTED", "EXECUTION_UNKNOWN"},
                "EXECUTION_UNKNOWN": {"RECONCILED"},
                "REJECTED": set(),
                "RECONCILED": set(),
            }
            if journal_state not in transitions[old]:
                raise QueueConflict("Invalid or conflicting journal transition")
            self.db.execute(
                "INSERT INTO agent_command_reports "
                "(command_id,agent_id,journal_state,reported_at) VALUES (?,?,?,?) "
                "ON CONFLICT(command_id) DO UPDATE SET "
                "journal_state=excluded.journal_state,reported_at=excluded.reported_at",
                (command_id, agent_id, journal_state,
                 datetime.now(timezone.utc).isoformat()))
            self.db.commit()
            return True
        except BaseException:
            self.db.rollback()
            raise

    def reported_state(self, agent_id: str, command_id: str) -> str | None:
        row = self.db.execute(
            "SELECT journal_state FROM agent_command_reports "
            "WHERE agent_id=? AND command_id=?",
            (agent_id, str(UUID(command_id)))).fetchone()
        return row[0] if row else None

    def delivery_receipt(self, agent_id: str, command_id: str) -> dict | None:
        """Read delivery status scoped to the authenticated agent.

        A missing or differently owned command is indistinguishable.
        This never returns the signed payload and never requeues a command.
        """
        row = self.db.execute(
            "SELECT c.status, r.journal_state FROM agent_commands c "
            "LEFT JOIN agent_command_reports r "
            "ON r.command_id=c.command_id AND r.agent_id=c.agent_id "
            "WHERE c.agent_id=? AND c.command_id=?",
            (agent_id, str(UUID(command_id)))).fetchone()
        if row is None:
            return None
        return {"status": row[0], "journal_state": row[1],
                "execution_enabled": False}

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
