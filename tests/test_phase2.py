"""Phase 2: memory FTS and history helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.core.history import RECENT_MESSAGE_LIMIT, build_context_messages
from backend.core.memory import add_memory, format_memory_block, search_memory
from backend.db.schema import connect, init_db


def test_memory_fts_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        add_memory(conn, "用户喜欢喝美式咖啡", kind="preference")
        add_memory(conn, "明天要开会", kind="dialogue")
        hits = search_memory(conn, "咖啡", limit=5)
        assert any("咖啡" in h["content"] for h in hits)
        block = format_memory_block(hits)
        assert "长期记忆" in block
        conn.close()


def test_build_context_includes_summary_and_memory():
    recent = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "喵"},
    ]
    msgs = build_context_messages(
        persona="persona",
        emotion_prompt="开心",
        summary="用户叫小明",
        memory_block="记忆：喜欢猫",
        recent=recent,
    )
    assert msgs[0]["role"] == "system"
    assert "用户叫小明" in msgs[0]["content"]
    assert "喜欢猫" in msgs[0]["content"]
    assert len(msgs) == 1 + min(len(recent), RECENT_MESSAGE_LIMIT)


def test_settings_page_route():
    from fastapi.testclient import TestClient

    from backend.app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        client = TestClient(app)
        res = client.get("/settings")
        assert res.status_code == 200
        assert "DexPet 设置" in res.text
        assert client.get("/").json()["app"] == "DexPet"
