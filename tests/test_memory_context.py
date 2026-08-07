"""Tests for file memory prompt injection."""

from __future__ import annotations

from datetime import date

from backend.core.conversation import ConversationManager
from backend.core.emotion import EmotionStateMachine
from backend.core.history import build_context_messages
from backend.core.memory_files import write_daily, write_profile
from backend.core.tools import ToolRouter
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


def test_build_context_orders_file_memory_before_summary():
    msgs = build_context_messages(
        persona="persona",
        emotion_prompt="emo",
        summary="会话要点",
        file_memory_block="长期画像：\n- 喜欢猫",
        memory_block="FTS片段",
        recent=[{"role": "user", "content": "hi"}],
    )
    system = msgs[0]["content"]
    assert system.index("长期画像") < system.index("会话摘要")
    assert system.index("会话摘要") < system.index("FTS片段")


def test_conversation_injects_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    write_profile("# 关于用户\n\n- 喜欢猫\n")
    write_daily(date.today(), "# 今日\n\n- 聊了工作\n")
    cm = ConversationManager(
        repo=repo,
        llm=object(),  # unused
        emotion=EmotionStateMachine(),
        tools=ToolRouter(),
    )
    sid = repo.create_session()
    repo.add_message(sid, "user", "你好")
    msgs = cm._build_messages(sid, "你好")
    system = msgs[0]["content"]
    assert "长期画像" in system
    assert "喜欢猫" in system
    conn.close()


def test_profile_truncation_in_block(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    from backend.core.memory_files import format_file_memory_block

    write_profile("X" * 2000)
    block = format_file_memory_block(profile_limit=100, daily_limit=50)
    assert "长期画像" in block
    assert len(block) < 250
