"""Durable last-acknowledged ntfy message cursor for a single bridge instance."""
import sqlite3
from pathlib import Path

class CursorStore:
    def __init__(self, path: str, topic: str):
        self.path = Path(path)
        self.topic = topic
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("CREATE TABLE IF NOT EXISTS cursors (topic TEXT PRIMARY KEY, message_id TEXT NOT NULL)")
        self.db.commit()

    def get(self) -> str | None:
        row = self.db.execute("SELECT message_id FROM cursors WHERE topic = ?", (self.topic,)).fetchone()
        return row[0] if row else None

    def acknowledge(self, message_id: str) -> None:
        if not message_id:
            raise ValueError("Cannot acknowledge an empty event ID")
        with self.db:
            self.db.execute(
                "INSERT INTO cursors(topic, message_id) VALUES (?, ?) "
                "ON CONFLICT(topic) DO UPDATE SET message_id=excluded.message_id",
                (self.topic, message_id),
            )

    def close(self) -> None:
        self.db.close()
