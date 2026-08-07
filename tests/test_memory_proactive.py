"""Tests for proactive memory checks."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.memory_config import save_memory_config
from backend.core.memory_files import update_meta, write_meta, write_open_questions, write_profile
from backend.core.memory_proactive import MemoryProactiveService, sample_check_times
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    r = Repository(conn)
    save_memory_config(
        r,
        {
            "proactive_enabled": True,
            "proactive_quiet_after_chat_minutes": 0,
            "proactive_max_asks_per_day": 0,
            "proactive_ask_cooldown_minutes": 0,
            "proactive_pattern_min_confidence": "medium",
            "proactive_pattern_cooldown_hours": 48,
        },
    )
    yield r
    conn.close()


@pytest.mark.asyncio
async def test_no_gaps_no_habits_skips_llm(repo):
    write_profile("# 关于用户\n\n- 喜欢茶\n")
    write_open_questions("# 记忆缺口\n\n（空）\n")
    write_meta({"habits": []})
    llm = AsyncMock()
    seen = []
    svc = MemoryProactiveService(repo, llm=llm, on_ask=lambda t, m: seen.append((t, m)))
    out = await svc.check_once(now=datetime(2026, 8, 6, 12, 0).astimezone())
    assert out["asked"] is False
    assert out.get("llm") is False
    assert out.get("reason") == "no_gaps_or_habits"
    llm.chat.assert_not_called()
    assert seen == []


@pytest.mark.asyncio
async def test_should_ask_false_no_notifier(repo):
    write_profile("# 关于用户\n\n## 记忆缺口\n### open_loops\n- 上次说的项目怎样了？\n")
    write_open_questions("# 记忆缺口\n\n- [high] 上次说的项目怎样了？\n")
    update_meta(open_questions=[{"text": "上次说的项目怎样了？", "priority": "high"}])
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {
                        "should_ask": False,
                        "question": None,
                        "ask_kind": None,
                        "pattern_id": None,
                        "reason": "not now",
                        "priority": "low",
                        "confidence": "low",
                    }
                )
            )
        )
    )
    seen = []
    svc = MemoryProactiveService(repo, llm=llm, on_ask=lambda t, m: seen.append((t, m)))
    out = await svc.check_once(now=datetime(2026, 8, 6, 12, 0).astimezone())
    assert out["asked"] is False
    assert seen == []


def _gap_llm(question: str = "上次那个项目后来怎样了？"):
    return SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {
                        "should_ask": True,
                        "question": question,
                        "ask_kind": "gap",
                        "pattern_id": None,
                        "reason": "open_loop",
                        "priority": "high",
                        "confidence": "high",
                    }
                )
            )
        )
    )


@pytest.mark.asyncio
async def test_should_ask_true_notifies_unlimited_by_default(repo):
    write_profile("# 关于用户\n\n## 记忆缺口\n### open_loops\n- 项目进度？\n")
    write_open_questions("- [high] 项目进度？\n")
    update_meta(open_questions=[{"text": "项目进度？", "priority": "high"}])
    llm = _gap_llm()
    seen = []
    svc = MemoryProactiveService(repo, llm=llm, on_ask=lambda t, m: seen.append((t, m)))
    now = datetime(2026, 8, 6, 12, 0).astimezone()
    out = await svc.check_once(now=now)
    assert out["asked"] is True
    assert len(seen) == 1
    assert "项目" in seen[0][1]

    # Default max_asks=0 → unlimited; cooldown disabled in fixture → second ask ok
    llm.chat.reset_mock()
    out2 = await svc.check_once(now=now + timedelta(hours=2))
    assert out2["asked"] is True
    assert len(seen) == 2
    assert llm.chat.await_count == 1


@pytest.mark.asyncio
async def test_max_asks_per_day_blocks_second(repo):
    save_memory_config(
        repo,
        {
            "proactive_max_asks_per_day": 1,
            "proactive_ask_cooldown_minutes": 0,
            "proactive_quiet_after_chat_minutes": 0,
        },
    )
    write_open_questions("- [high] 项目进度？\n")
    update_meta(open_questions=[{"text": "项目进度？", "priority": "high"}])
    llm = _gap_llm()
    seen = []
    svc = MemoryProactiveService(repo, llm=llm, on_ask=lambda t, m: seen.append((t, m)))
    now = datetime(2026, 8, 6, 12, 0).astimezone()
    assert (await svc.check_once(now=now))["asked"] is True
    llm.chat.reset_mock()
    out2 = await svc.check_once(now=now + timedelta(hours=2))
    assert out2["asked"] is False
    assert out2.get("reason") == "max_asks"
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_ask_cooldown_blocks_without_llm(repo):
    save_memory_config(
        repo,
        {
            "proactive_max_asks_per_day": 0,
            "proactive_ask_cooldown_minutes": 180,
            "proactive_quiet_after_chat_minutes": 0,
        },
    )
    write_open_questions("- [high] 项目进度？\n")
    update_meta(open_questions=[{"text": "项目进度？", "priority": "high"}])
    llm = _gap_llm()
    seen = []
    svc = MemoryProactiveService(repo, llm=llm, on_ask=lambda t, m: seen.append((t, m)))
    now = datetime(2026, 8, 6, 12, 0).astimezone()
    assert (await svc.check_once(now=now))["asked"] is True
    llm.chat.reset_mock()
    out2 = await svc.check_once(now=now + timedelta(hours=1))
    assert out2["asked"] is False
    assert out2.get("reason") == "ask_cooldown"
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_pattern_low_confidence_no_ask(repo):
    write_profile("# 关于用户\n\n## 习惯与规律\n- 早上看盘\n")
    update_meta(
        habits=[
            {
                "id": "stock-am",
                "text": "早上看盘",
                "kind": "time_pattern",
                "evidence": "1次",
                "confidence": "low",
            }
        ],
        open_questions=[],
    )
    # No gaps; only low-confidence habit → skip LLM
    llm = AsyncMock()
    svc = MemoryProactiveService(repo, llm=llm, on_ask=MagicMock())
    out = await svc.check_once(now=datetime(2026, 8, 6, 10, 0).astimezone())
    assert out["asked"] is False
    assert out.get("reason") == "no_gaps_or_habits"
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_pattern_cooldown_blocks(repo):
    write_open_questions("- gap\n")
    update_meta(
        open_questions=[{"text": "gap", "priority": "medium"}],
        habits=[
            {
                "id": "stock-am",
                "text": "早上看盘",
                "kind": "time_pattern",
                "evidence": "近5日4次",
                "confidence": "high",
            }
        ],
        pattern_ask_cooldown={
            "stock-am": (datetime(2026, 8, 5, 10, 0).astimezone()).isoformat()
        },
    )
    llm = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=json.dumps(
                    {
                        "should_ask": True,
                        "question": "今天要看盘吗？",
                        "ask_kind": "pattern",
                        "pattern_id": "stock-am",
                        "reason": "habit",
                        "priority": "medium",
                        "confidence": "high",
                    }
                )
            )
        )
    )
    seen = []
    svc = MemoryProactiveService(repo, llm=llm, on_ask=lambda t, m: seen.append((t, m)))
    out = await svc.check_once(now=datetime(2026, 8, 6, 10, 0).astimezone())
    assert out["asked"] is False
    assert out.get("reason") == "pattern_cooldown"
    assert seen == []


@pytest.mark.asyncio
async def test_busy_skips_without_ask_count(repo):
    write_open_questions("- [high] x\n")
    update_meta(open_questions=[{"text": "x", "priority": "high"}])
    llm = AsyncMock()
    svc = MemoryProactiveService(
        repo, llm=llm, on_ask=MagicMock(), is_busy=lambda: True
    )
    out = await svc.check_once(now=datetime(2026, 8, 6, 12, 0).astimezone())
    assert out["skipped"] is True
    assert out["reason"] == "busy"
    llm.chat.assert_not_called()


def test_sample_k_in_window():
    import random

    times = sample_check_times(
        day=datetime(2026, 8, 6).date(),
        count=12,
        min_gap_minutes=25,
        window_start="09:00",
        window_end="21:30",
        rng=random.Random(1),
    )
    assert len(times) == 12


@pytest.mark.asyncio
async def test_morning_disabled_skips(repo):
    save_memory_config(repo, {"proactive_morning_enabled": False})
    seen = []
    svc = MemoryProactiveService(repo, llm=AsyncMock(), on_ask=lambda t, m: seen.append((t, m)))
    out = await svc.morning_check(now=datetime(2026, 8, 6, 9, 30).astimezone())
    assert out["skipped"] is True
    assert out["reason"] == "morning_disabled"
    assert seen == []


@pytest.mark.asyncio
async def test_morning_light_greeting_when_no_gaps(repo):
    save_memory_config(
        repo,
        {
            "proactive_morning_enabled": True,
            "proactive_quiet_after_chat_minutes": 0,
        },
    )
    write_profile("# 关于用户\n\n- 喜欢茶\n")
    write_open_questions("# 记忆缺口\n\n（空）\n")
    write_meta({"habits": []})
    seen = []
    svc = MemoryProactiveService(repo, llm=AsyncMock(), on_ask=lambda t, m: seen.append((t, m)))
    now = datetime(2026, 8, 6, 9, 30).astimezone()
    out = await svc.morning_check(now=now)
    assert out["asked"] is True
    assert out["ask_kind"] == "greeting"
    assert len(seen) == 1
    assert "早上好" in seen[0][0]
    # Second morning same day: no re-greet
    out2 = await svc.morning_check(now=now)
    assert out2["asked"] is False
    assert out2["reason"] == "morning_already_greeted"
    assert len(seen) == 1
