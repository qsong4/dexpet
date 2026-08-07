"""Slash command unit + WS integration tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.slash import handle_slash_command, is_slash_command, parse_slash
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


def test_parse_slash():
    assert is_slash_command("/list")
    assert not is_slash_command("list")
    assert parse_slash("/list") == ("list", "")
    assert parse_slash("/HELP") == ("help", "")
    assert parse_slash("/") == ("", "")


@pytest.mark.asyncio
async def test_list_and_clear_commands():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        sid = repo.create_session()
        repo.add_message(sid, "user", "hi")
        repo.add_message(sid, "assistant", "hello")
        repo.set_pet_state(f"summary:{sid}", "old summary")
        repo.create_reminder("喝水", "2026-08-05T20:00:00+08:00")
        done_id = repo.create_reminder("已完成", "2026-08-05T10:00:00+08:00")
        repo.mark_reminder_done(done_id)

        events = []
        async for ev in handle_slash_command("/list", repo=repo, session_id=sid):
            events.append(ev)
        text = events[0]["payload"]["text"]
        assert "喝水" in text
        assert "已完成" not in text
        assert events[-1]["type"] == "done"

        # clear should wipe messages + summary, not touch reminders
        events = []
        async for ev in handle_slash_command("/clear", repo=repo, session_id=sid):
            events.append(ev)
        assert "已清空" in events[0]["payload"]["text"]
        assert repo.list_messages(sid) == []
        assert repo.get_pet_state(f"summary:{sid}") is None
        assert len(repo.list_reminders(status="pending")) == 1

        events = []
        async for ev in handle_slash_command("/nope", repo=repo, session_id=sid):
            events.append(ev)
        assert "未知命令" in events[0]["payload"]["text"]
        conn.close()


@pytest.mark.asyncio
async def test_slash_memory_command(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    events = []
    async for ev in handle_slash_command("/memory", repo=repo, session_id=None):
        events.append(ev)
    text = events[0]["payload"]["text"]
    assert "长期记忆目录" in text
    assert "主动抽检" in text
    conn.close()


def test_slash_via_websocket_without_api_key():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        # Ensure no conversation/LLM required
        app.state.conversation = None
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "user_message",
                    "payload": {"text": "/help"},
                    "request_id": "r1",
                }
            )
            token = ws.receive_json()
            done = ws.receive_json()
            assert token["type"] == "token"
            assert "/list" in token["payload"]["text"]
            assert done["type"] == "done"
            assert done["request_id"] == "r1"
