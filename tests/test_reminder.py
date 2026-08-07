"""Reminder plugin and tool router tests."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.core.tools import ToolRouter
from backend.db.repository import Repository
from backend.db.schema import connect, init_db
from backend.plugins.reminder import ReminderPlugin, resolve_fire_time


@pytest.fixture
def repo_and_plugin():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        scheduler = MagicMock()
        scheduler.running = True
        plugin = ReminderPlugin(repo, scheduler=scheduler)
        yield repo, plugin, scheduler
        conn.close()


def test_resolve_delay_seconds():
    now = datetime(2026, 8, 5, 19, 0, tzinfo=timezone(timedelta(hours=8)))
    when = resolve_fire_time(delay_seconds=60, now=now)
    assert when == now + timedelta(seconds=60)


def test_resolve_past_fire_at_bumped():
    now = datetime(2026, 8, 5, 19, 0, tzinfo=timezone(timedelta(hours=8)))
    when = resolve_fire_time(fire_at="2025-07-09T17:31:00+08:00", now=now)
    assert when == now + timedelta(seconds=5)


def test_create_list_delete_reminder(repo_and_plugin):
    repo, plugin, scheduler = repo_and_plugin
    created = plugin.create_reminder("喝水", delay_seconds=120)
    assert created["id"] >= 1
    scheduler.add_job.assert_called()
    listed = plugin.list_reminders(status="pending")
    assert len(listed) == 1
    deleted = plugin.delete_reminder(created["id"])
    assert deleted["deleted"] is True


def test_fire_calls_notifier(repo_and_plugin):
    _, plugin, _ = repo_and_plugin
    seen: list[tuple[int, str]] = []
    plugin.set_notifier(lambda rid, msg: seen.append((rid, msg)))
    plugin._fire(42, "喝水啦")
    assert seen == [(42, "喝水啦")]


@pytest.mark.asyncio
async def test_tool_router_executes(repo_and_plugin):
    _, plugin, _ = repo_and_plugin
    router = ToolRouter()
    router.register_plugin(plugin)
    tools = router.openai_tools()
    assert any(t["function"]["name"] == "create_reminder" for t in tools)
    out = await router.execute(
        "create_reminder",
        {"message": "test", "delay_seconds": 30},
    )
    assert out["message"] == "test"
    assert "fire_at" in out
