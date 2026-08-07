"""HTTP API tests for memory config / digest / clear."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.memory_files import (
    profile_mtime,
    read_meta,
    read_profile,
    record_digest_failure,
    write_profile,
)


def test_memory_config_get_put_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    # Also patch db path via create_app db_file
    app = create_app(db_file=str(tmp_path / "t.db"))
    client = TestClient(app)

    r = client.get("/config/memory")
    assert r.status_code == 200
    data = r.json()
    assert data["config"]["digest_hour"] == 0
    assert data["config"]["digest_minute"] == 0
    assert data["config"]["proactive_max_asks_per_day"] == 0
    assert data["config"]["proactive_ask_cooldown_minutes"] == 0
    assert data["config"]["proactive_window_start"] == "09:00"
    assert data["config"]["proactive_checks_min"] == 10
    assert data["config"]["proactive_checks_max"] == 20
    assert data["config"]["proactive_morning_enabled"] is False

    r2 = client.put(
        "/config/memory",
        json={
            "enabled": True,
            "digest_hour": 23,
            "digest_minute": 0,
            "proactive_enabled": False,
            "proactive_checks_min": 12,
            "proactive_checks_max": 18,
            "proactive_morning_enabled": True,
            "proactive_morning_hour": 8,
            "proactive_morning_minute": 15,
        },
    )
    assert r2.status_code == 200
    cfg = r2.json()["config"]
    assert cfg["digest_hour"] == 23
    assert cfg["proactive_enabled"] is False
    assert cfg["proactive_checks_min"] == 12
    assert cfg["proactive_morning_enabled"] is True
    assert cfg["proactive_morning_hour"] == 8
    assert cfg["proactive_morning_minute"] == 15

    write_profile("secret profile")
    assert "secret" in read_profile()
    r3 = client.post("/memory/clear")
    assert r3.status_code == 200
    assert read_profile() == ""


def test_memory_profile_get_put_and_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    app = create_app(db_file=str(tmp_path / "t.db"))
    client = TestClient(app)

    r = client.get("/memory/profile")
    assert r.status_code == 200
    assert r.json()["content"] == ""
    assert r.json()["mtime"] == 0.0

    r2 = client.put("/memory/profile", json={"content": "# 关于用户\n\n- 喜欢猫\n"})
    assert r2.status_code == 200
    assert "喜欢猫" in r2.json()["content"]
    assert "喜欢猫" in read_profile()
    mtime = r2.json()["mtime"]
    assert mtime == profile_mtime()

    # Simulate digest overwrite
    write_profile("# 关于用户\n\n- digest wrote\n")
    r3 = client.put(
        "/memory/profile",
        json={"content": "# 关于用户\n\n- user edit\n", "if_mtime": mtime, "force": False},
    )
    assert r3.status_code == 409
    detail = r3.json()["detail"]
    assert detail["conflict"] is True
    assert "digest wrote" in detail["content"]

    r4 = client.put(
        "/memory/profile",
        json={"content": "# 关于用户\n\n- user edit\n", "if_mtime": mtime, "force": True},
    )
    assert r4.status_code == 200
    assert "user edit" in read_profile()


def test_memory_config_exposes_digest_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    app = create_app(db_file=str(tmp_path / "t.db"))
    client = TestClient(app)
    record_digest_failure(error="boom", for_date="2026-08-05")
    r = client.get("/config/memory")
    assert r.status_code == 200
    fail = r.json()["digest_failure"]
    assert fail["error"] == "boom"
    assert read_meta().get("digest_failure_unread") is True


def test_memory_digest_endpoint_mocked(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    app = create_app(db_file=str(tmp_path / "t.db"))
    # Empty day → no LLM needed
    app.state.memory_digest.set_llm(AsyncMock())
    client = TestClient(app)
    r = client.post("/memory/digest?force=true")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
