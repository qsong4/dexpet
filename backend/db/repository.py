"""Repository helpers for DexPet SQLite store."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- sessions / messages ---

    def create_session(self, title: str = "default") -> str:
        session_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
        self.conn.commit()
        return session_id

    def ensure_session(self, session_id: str | None) -> str:
        if session_id:
            row = self.conn.execute(
                "SELECT id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row:
                return session_id
        return self.create_session()

    def add_message(self, session_id: str, role: str, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, _now()),
        )
        self.conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_messages(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def list_messages_between(self, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        """Messages with created_at in [start_iso, end_iso), all sessions."""
        rows = self.conn.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM messages
            WHERE created_at >= ? AND created_at < ?
            ORDER BY id ASC
            """,
            (start_iso, end_iso),
        ).fetchall()
        return [dict(r) for r in rows]

    def latest_message_created_at(self) -> str | None:
        row = self.conn.execute(
            "SELECT created_at FROM messages ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["created_at"] if row else None

    def clear_session_messages(self, session_id: str) -> int:
        """Delete all messages and session summary for a session. Returns deleted count."""
        cur = self.conn.execute(
            "DELETE FROM messages WHERE session_id = ?",
            (session_id,),
        )
        deleted = int(cur.rowcount)
        self.conn.execute(
            "DELETE FROM pet_state WHERE key = ?",
            (f"summary:{session_id}",),
        )
        self.conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )
        self.conn.commit()
        return deleted

    # --- reminders ---

    def create_reminder(self, message: str, fire_at: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO reminders (message, fire_at, status, created_at) VALUES (?, ?, 'pending', ?)",
            (message, fire_at, _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_reminders(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM reminders WHERE status = ? ORDER BY fire_at",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM reminders ORDER BY fire_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_reminder(self, reminder_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_reminder_done(self, reminder_id: int) -> None:
        self.conn.execute(
            "UPDATE reminders SET status = 'done' WHERE id = ?",
            (reminder_id,),
        )
        self.conn.commit()

    # --- stock watches ---

    def create_stock_watch(
        self,
        symbol: str,
        name: str,
        metric: str,
        op: str,
        threshold: float,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO stock_watches
            (symbol, name, metric, op, threshold, status, last_triggered_at, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', NULL, ?)
            """,
            (symbol, name, metric, op, float(threshold), _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_stock_watches(self, status: str | None = "active") -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM stock_watches WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM stock_watches ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stock_watch(self, watch_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM stock_watches WHERE id = ?",
            (watch_id,),
        ).fetchone()
        return dict(row) if row else None

    def cancel_stock_watch(self, watch_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE stock_watches SET status = 'cancelled' WHERE id = ? AND status = 'active'",
            (watch_id,),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def touch_stock_watch_triggered(self, watch_id: int, when: str | None = None) -> None:
        self.conn.execute(
            "UPDATE stock_watches SET last_triggered_at = ? WHERE id = ?",
            (when or _now(), watch_id),
        )
        self.conn.commit()

    # --- pet state / settings ---

    def get_pet_state(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM pet_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_pet_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO pet_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_setting_json(self, key: str, default: Any = None) -> Any:
        raw = self.get_setting(key)
        if raw is None:
            return default
        return json.loads(raw)

    def set_setting_json(self, key: str, value: Any) -> None:
        self.set_setting(key, json.dumps(value))
