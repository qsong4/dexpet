"""Local open-app intent tests (bypass LLM)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.app_whitelist import DEFAULT_APP_ALIASES
from backend.core.local_intents import (
    handle_close_app_intent,
    handle_open_app_intent,
    looks_like_close_app_command,
    looks_like_open_app_command,
    match_close_app_intent,
    match_open_app_intent,
)
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


def test_looks_like_open_app_command():
    assert looks_like_open_app_command("打开网易云音乐")
    assert looks_like_open_app_command("帮我打开微信")
    assert looks_like_open_app_command("open Safari")
    assert not looks_like_open_app_command("网易云音乐怎么用")
    assert not looks_like_open_app_command("今天天气怎么样")


def test_match_open_app_intent_resolves_spaced_names():
    aliases = dict(DEFAULT_APP_ALIASES)
    assert match_open_app_intent("打开网易云音乐", aliases) == "NeteaseMusic"
    assert match_open_app_intent("打开网易 云音乐", aliases) == "NeteaseMusic"
    assert match_open_app_intent("请打开云音乐", aliases) == "NeteaseMusic"
    assert match_open_app_intent("打开一个不存在的软件xyz", aliases) is None
    assert match_open_app_intent("网易云音乐很好听", aliases) is None


@pytest.mark.asyncio
async def test_handle_open_app_intent_opens():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        sid = repo.create_session()
        with patch("backend.core.local_intents.open_app") as open_mock:
            open_mock.return_value = {"ok": True, "app": "NeteaseMusic"}
            events = []
            async for ev in handle_open_app_intent(
                "打开网易云音乐", repo=repo, session_id=sid
            ):
                events.append(ev)
            open_mock.assert_called_once()
            assert any(e["type"] == "tool_status" for e in events)
            assert "NeteaseMusic" in events[-1]["payload"]["text"]
            assert events[-1]["type"] == "done"
        conn.close()


def test_open_app_intent_via_websocket_without_llm():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        app.state.conversation = None
        client = TestClient(app)
        with patch("backend.core.local_intents.open_app") as open_mock:
            open_mock.return_value = {"ok": True, "app": "NeteaseMusic"}
            with client.websocket_connect("/ws") as ws:
                ws.send_json(
                    {
                        "type": "user_message",
                        "payload": {"text": "打开网易 云音乐"},
                        "request_id": "r-open",
                    }
                )
                events = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
            open_mock.assert_called_once()
            types = [e["type"] for e in events]
            assert "tool_status" in types
            assert "token" in types
            assert "done" in types
            done = next(e for e in events if e["type"] == "done")
            assert done["request_id"] == "r-open"
            assert "NeteaseMusic" in done["payload"]["text"]


def test_looks_like_close_app_command():
    assert looks_like_close_app_command("关闭网易云音乐")
    assert looks_like_close_app_command("帮我退出微信")
    assert looks_like_close_app_command("quit Safari")
    assert not looks_like_close_app_command("打开网易云音乐")
    assert not looks_like_close_app_command("网易云音乐怎么关")
    assert not looks_like_close_app_command("今天天气怎么样")


def test_match_close_app_intent_resolves():
    aliases = dict(DEFAULT_APP_ALIASES)
    assert match_close_app_intent("关闭网易云音乐", aliases) == "NeteaseMusic"
    assert match_close_app_intent("退出网易 云音乐", aliases) == "NeteaseMusic"
    assert match_close_app_intent("请关闭云音乐", aliases) == "NeteaseMusic"
    assert match_close_app_intent("关闭一个不存在的软件xyz", aliases) is None
    assert match_close_app_intent("打开网易云音乐", aliases) is None


@pytest.mark.asyncio
async def test_handle_close_app_intent_quits():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        sid = repo.create_session()
        with patch("backend.core.local_intents.close_app") as close_mock:
            close_mock.return_value = {"ok": True, "app": "NeteaseMusic"}
            events = []
            async for ev in handle_close_app_intent(
                "关闭网易云音乐", repo=repo, session_id=sid
            ):
                events.append(ev)
            close_mock.assert_called_once()
            assert any(e["type"] == "tool_status" for e in events)
            assert "NeteaseMusic" in events[-1]["payload"]["text"]
            assert events[-1]["type"] == "done"
        conn.close()


def test_close_app_intent_via_websocket_without_llm():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        app.state.conversation = None
        client = TestClient(app)
        with patch("backend.core.local_intents.close_app") as close_mock:
            close_mock.return_value = {"ok": True, "app": "NeteaseMusic"}
            with client.websocket_connect("/ws") as ws:
                ws.send_json(
                    {
                        "type": "user_message",
                        "payload": {"text": "关闭网易 云音乐"},
                        "request_id": "r-close",
                    }
                )
                events = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
            close_mock.assert_called_once()
            types = [e["type"] for e in events]
            assert "tool_status" in types
            assert "token" in types
            assert "done" in types
            done = next(e for e in events if e["type"] == "done")
            assert done["request_id"] == "r-close"
            assert "NeteaseMusic" in done["payload"]["text"]
