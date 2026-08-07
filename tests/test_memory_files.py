"""Tests for markdown memory file helpers."""

from __future__ import annotations

from datetime import date

from backend.core import memory_files as mf


def test_memory_dir_and_atomic_profile_write(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    assert mf.memory_dir().name == "memory"
    assert mf.memory_dir().exists()
    mf.write_profile("# 关于用户\n\n- 喜欢猫\n")
    assert "喜欢猫" in mf.read_profile()
    mf.write_daily(date(2026, 8, 6), "# 2026-08-06\n\n- hello\n")
    assert "hello" in mf.read_daily("2026-08-06")
    mf.write_meta({"last_success_date": "2026-08-06"})
    assert mf.read_meta()["last_success_date"] == "2026-08-06"


def test_format_file_memory_block_truncates(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    mf.write_profile("画像" + ("很长" * 500))
    mf.write_daily(date.today(), "摘要要点很多 " * 80)
    block = mf.format_file_memory_block(profile_limit=80, daily_limit=60)
    assert "长期画像" in block
    assert len(block) < 400


def test_clear_memory_files(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    mf.write_profile("x")
    mf.write_daily(date.today(), "y")
    mf.write_meta({"a": 1})
    mf.clear_memory_files()
    assert mf.read_profile() == ""
    assert mf.read_daily(date.today()) == ""
    assert mf.read_meta() == {}


def test_digest_failure_record_consume_clear(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    mf.record_digest_failure(error="oops", for_date="2026-08-05")
    meta = mf.read_meta()
    assert meta["digest_failure_unread"] is True
    assert meta["last_digest_failure"]["error"] == "oops"
    first = mf.consume_digest_failure_notification(today="2026-08-06")
    assert first is not None
    assert first["error"] == "oops"
    assert mf.consume_digest_failure_notification(today="2026-08-06") is None
    mf.clear_digest_failure()
    assert "last_digest_failure" not in mf.read_meta()
    assert mf.read_meta().get("digest_failure_unread") is False
