"""Tests for memory scheduler job registration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

from backend.core.memory_config import DEFAULT_MEMORY_CONFIG, save_memory_config
from backend.core.memory_digest import MemoryDigestService
from backend.core.memory_files import (
    consume_digest_failure_notification,
    read_meta,
    record_digest_failure,
)
from backend.core.memory_proactive import MemoryProactiveService, sample_check_times
from backend.core.memory_scheduler import (
    CHECK_JOB_PREFIX,
    DAILY_RESAMPLE_JOB_ID,
    DIGEST_JOB_ID,
    MORNING_JOB_ID,
    MemoryScheduler,
)
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


def test_sample_check_times_respects_window_and_gap():
    day = date(2026, 8, 6)
    import random

    times = sample_check_times(
        day=day,
        window_start="09:00",
        window_end="21:30",
        count=15,
        min_gap_minutes=25,
        rng=random.Random(42),
    )
    assert 10 <= len(times) <= 15
    assert all(t.hour >= 9 for t in times)
    assert all(
        (t.hour < 21) or (t.hour == 21 and t.minute <= 30) for t in times
    )
    for a, b in zip(times, times[1:]):
        assert (b - a) >= timedelta(minutes=25)


def test_sample_check_times_midday_keeps_count_in_remaining_window():
    """Late start should resample inside remaining window, not drop most of K."""
    import random

    day = date(2026, 8, 7)
    now = datetime(2026, 8, 7, 14, 4).astimezone()
    times = sample_check_times(
        day=day,
        window_start="09:00",
        window_end="21:30",
        count=15,
        min_gap_minutes=25,
        rng=random.Random(42),
        now=now,
    )
    assert len(times) == 15
    assert all(t > now - timedelta(minutes=2) for t in times)
    assert all(
        (t.hour < 21) or (t.hour == 21 and t.minute <= 30) for t in times
    )
    for a, b in zip(times, times[1:]):
        assert (b - a) >= timedelta(minutes=25)


def test_ensure_jobs_registers_digest_and_checks(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    save_memory_config(
        repo,
        {
            **DEFAULT_MEMORY_CONFIG,
            "proactive_checks_min": 10,
            "proactive_checks_max": 10,
        },
    )
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = []

    digest = MemoryDigestService(repo)
    proactive = MemoryProactiveService(repo)
    ms = MemoryScheduler(repo, scheduler, digest, proactive, loop_provider=None)

    # Schedule for a fixed day with "now" before the window so all 10 remain
    fixed_day = date(2026, 8, 6)
    morning = datetime(2026, 8, 6, 8, 0).astimezone()
    n = ms.schedule_proactive_for_day(fixed_day, now=morning)
    assert n == 10

    summary = ms.ensure_jobs()
    assert summary["digest"] is True
    assert summary["morning"] is False
    ids = [c.kwargs.get("id") for c in scheduler.add_job.call_args_list]
    assert DIGEST_JOB_ID in ids
    assert DAILY_RESAMPLE_JOB_ID in ids
    assert MORNING_JOB_ID not in ids
    check_ids = [i for i in ids if i and str(i).startswith(CHECK_JOB_PREFIX)]
    assert len(check_ids) >= 1
    conn.close()


def test_ensure_jobs_schedules_startup_catchup_inside_window(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    save_memory_config(
        repo,
        {
            **DEFAULT_MEMORY_CONFIG,
            "proactive_enabled": True,
            "proactive_checks_min": 10,
            "proactive_checks_max": 10,
            "proactive_window_start": "09:00",
            "proactive_window_end": "21:30",
        },
    )
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = []
    digest = MemoryDigestService(repo)
    proactive = MemoryProactiveService(repo)
    ms = MemoryScheduler(repo, scheduler, digest, proactive, loop_provider=None)

    fixed_now = datetime(2026, 8, 7, 14, 4).astimezone()
    summary = ms.ensure_jobs(now=fixed_now)
    assert summary["proactive_checks"] >= 1
    assert summary.get("catchup") is True
    ids = [c.kwargs.get("id") for c in scheduler.add_job.call_args_list]
    assert "memory-proactive-catchup" in ids
    conn.close()


def test_ensure_jobs_registers_morning_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    save_memory_config(
        repo,
        {
            **DEFAULT_MEMORY_CONFIG,
            "proactive_enabled": False,
            "proactive_morning_enabled": True,
            "proactive_morning_hour": 9,
            "proactive_morning_minute": 0,
        },
    )
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = []
    digest = MemoryDigestService(repo)
    proactive = MemoryProactiveService(repo)
    ms = MemoryScheduler(repo, scheduler, digest, proactive, loop_provider=None)
    summary = ms.ensure_jobs()
    assert summary["morning"] is True
    assert summary["proactive_checks"] == 0
    ids = [c.kwargs.get("id") for c in scheduler.add_job.call_args_list]
    assert MORNING_JOB_ID in ids
    assert DAILY_RESAMPLE_JOB_ID not in ids
    conn.close()


def test_digest_failure_notifies_once_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = []
    digest = MemoryDigestService(repo)
    proactive = MemoryProactiveService(repo)
    pushes: list[tuple[str, str]] = []
    ms = MemoryScheduler(
        repo,
        scheduler,
        digest,
        proactive,
        loop_provider=None,
        on_digest_failure=lambda t, m: pushes.append((t, m)),
    )
    record_digest_failure(error="llm down", for_date="2026-08-05")
    assert ms.notify_pending_digest_failure() is True
    assert len(pushes) == 1
    assert "记忆整理失败" in pushes[0][0]
    # Second call same day: no re-push
    assert ms.notify_pending_digest_failure() is False
    assert len(pushes) == 1
    assert read_meta().get("digest_failure_notified_date") == date.today().isoformat()
    assert consume_digest_failure_notification() is None
    conn.close()


def test_job_digest_failure_records_and_notifies(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    conn = connect(tmp_path / "t.db")
    init_db(conn)
    repo = Repository(conn)
    scheduler = MagicMock()
    scheduler.running = True
    scheduler.get_jobs.return_value = []
    digest = MagicMock()

    async def boom(**kwargs):
        raise RuntimeError("mock digest fail")

    digest.run = boom
    proactive = MemoryProactiveService(repo)
    pushes: list[tuple[str, str]] = []
    ms = MemoryScheduler(
        repo,
        scheduler,
        digest,
        proactive,
        loop_provider=None,
        on_digest_failure=lambda t, m: pushes.append((t, m)),
    )
    ms._job_digest()
    assert len(pushes) == 1
    meta = read_meta()
    assert meta.get("last_digest_failure", {}).get("error")
    assert "mock digest fail" in meta["last_digest_failure"]["error"]
    conn.close()
