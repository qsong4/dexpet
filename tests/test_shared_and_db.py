"""Tests for shared message schemas and SQLite repository."""

from __future__ import annotations

import tempfile
from pathlib import Path

from shared.messages import Envelope, MessageType, UserMessagePayload
from backend.db.schema import connect, init_db
from backend.db.repository import Repository


def test_envelope_roundtrip():
    env = Envelope(
        type=MessageType.USER_MESSAGE,
        payload=UserMessagePayload(text="hello").model_dump(),
        request_id="r1",
    )
    data = env.model_dump()
    restored = Envelope.model_validate(data)
    assert restored.type == MessageType.USER_MESSAGE
    assert restored.payload["text"] == "hello"
    assert restored.request_id == "r1"


def test_init_db_and_session_messages():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "t.db"
        conn = connect(db)
        init_db(conn)
        repo = Repository(conn)

        sid = repo.create_session("test")
        assert sid
        mid = repo.add_message(sid, "user", "hi")
        assert mid >= 1
        msgs = repo.list_messages(sid)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hi"

        repo.set_pet_state("emotion", "happy")
        assert repo.get_pet_state("emotion") == "happy"

        rid = repo.create_reminder("drink water", "2026-08-05T12:00:00+00:00")
        assert rid >= 1
        reminders = repo.list_reminders(status="pending")
        assert len(reminders) == 1
        assert repo.delete_reminder(rid) is True
        conn.close()
