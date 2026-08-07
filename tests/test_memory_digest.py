"""Tests for nightly memory digest + message range query."""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.core.memory_digest import MemoryDigestService
from backend.core.memory_files import read_daily, read_meta, read_profile
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    yield Repository(conn)
    conn.close()


def test_list_messages_between_filters_by_created_at(repo):
    sid = repo.create_session()
    # Force created_at via raw SQL for deterministic bounds
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "user", "early", "2026-08-05T10:00:00+00:00"),
    )
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "user", "mid", "2026-08-06T02:00:00+00:00"),
    )
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "user", "late", "2026-08-07T01:00:00+00:00"),
    )
    repo.conn.commit()
    rows = repo.list_messages_between("2026-08-06T00:00:00+00:00", "2026-08-07T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["content"] == "mid"


@pytest.mark.asyncio
async def test_digest_empty_day_skips_llm(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    llm = AsyncMock()
    svc = MemoryDigestService(repo, llm=llm)
    day = date(2026, 8, 6)
    out = await svc.run(for_date=day, force=True)
    assert out["ok"] is True
    assert out.get("empty") is True
    assert out.get("llm") is False
    llm.chat.assert_not_called()
    assert read_meta().get("last_success_date") == "2026-08-06"
    assert "无有效对话" in read_daily(day)


@pytest.mark.asyncio
async def test_digest_with_messages_writes_profile_and_habits(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    sid = repo.create_session()
    # Place messages in local calendar day for `day`
    day = date(2026, 8, 6)
    local = datetime(2026, 8, 6, 12, 0, tzinfo=datetime.now().astimezone().tzinfo)
    utc = local.astimezone(timezone.utc).isoformat()
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "user", "我喜欢看股票", utc),
    )
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "assistant", "好的，记下了", utc),
    )
    repo.conn.commit()

    payload = {
        "daily_markdown": f"# {day.isoformat()} 日摘要\n\n## 要点\n- 聊了股票\n",
        "profile_markdown": (
            "# 关于用户\n\n## 稳定事实\n- 关注股票\n\n## 习惯与规律\n"
            "- 常问股票（置信度：medium；依据：当日）\n\n## 记忆缺口\n### open_loops\n- （空）\n"
        ),
        "open_questions": [],
        "habits": [
            {
                "id": "stock",
                "text": "常问股票",
                "kind": "request_type",
                "evidence": "当日提及",
                "confidence": "medium",
            }
        ],
        "fts_facts": ["用户关注股票"],
    }
    llm = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))
    )
    svc = MemoryDigestService(repo, llm=llm)
    out = await svc.run(for_date=day, force=True)
    assert out["ok"] is True
    assert out["llm"] is True
    assert "关注股票" in read_profile() or "常问股票" in read_profile()
    assert "聊了股票" in read_daily(day)
    assert read_meta().get("last_success_date") == day.isoformat()
    assert len(read_meta().get("habits") or []) == 1

    # Idempotent skip
    out2 = await svc.run(for_date=day, force=False)
    assert out2.get("skipped") is True
    assert llm.chat.await_count == 1


@pytest.mark.asyncio
async def test_digest_parses_fenced_malformed_json(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    sid = repo.create_session()
    day = date(2026, 8, 6)
    local = datetime(2026, 8, 6, 12, 0, tzinfo=datetime.now().astimezone().tzinfo)
    utc = local.astimezone(timezone.utc).isoformat()
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "user", "提醒我看股票", utc),
    )
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "assistant", "好的", utc),
    )
    repo.conn.commit()

    messy = """```json
{
  "daily_markdown": "# 日摘要
- 提到 "股票"
",
  "profile_markdown": "# 关于用户
- 关心 "行情"
",
  "open_questions": [],
  "habits": [],
  "fts_facts": [],
}
```"""
    llm = SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content=messy)))
    svc = MemoryDigestService(repo, llm=llm)
    out = await svc.run(for_date=day, force=True)
    assert out["ok"] is True
    assert out.get("degraded") is False
    assert "股票" in read_daily(day)
    assert "行情" in read_profile()


@pytest.mark.asyncio
async def test_digest_degrades_instead_of_raising(repo, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    sid = repo.create_session()
    day = date(2026, 8, 6)
    local = datetime(2026, 8, 6, 12, 0, tzinfo=datetime.now().astimezone().tzinfo)
    utc = local.astimezone(timezone.utc).isoformat()
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "user", "你好", utc),
    )
    repo.conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (sid, "assistant", "嗨", utc),
    )
    repo.conn.commit()

    llm = SimpleNamespace(
        chat=AsyncMock(
            side_effect=[
                SimpleNamespace(content="not json at all {{{"),
                SimpleNamespace(content="still broken"),
            ]
        )
    )
    svc = MemoryDigestService(repo, llm=llm)
    out = await svc.run(for_date=day, force=True)
    assert out["ok"] is True
    assert out.get("degraded") is True
    assert out.get("retried") is True
    assert llm.chat.await_count == 2
    assert "降级" in read_daily(day)
    assert read_meta().get("last_success_date") == day.isoformat()
    assert read_profile().strip()  # profile written (stub or preserved)
