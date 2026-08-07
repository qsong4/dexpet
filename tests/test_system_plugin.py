"""System control plugin unit tests (mocked subprocess)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core import macos_system as mac
from backend.db.repository import Repository
from backend.db.schema import connect, init_db
from backend.plugins.system_control import SystemControlPlugin


def test_resolve_app_and_url_guards():
    assert mac.resolve_app_name("Safari") == "Safari"
    assert mac.resolve_app_name("未知应用") is None
    assert mac.resolve_app_name("打开网易云音乐") == "NeteaseMusic"
    assert mac.resolve_app_name("帮我打开微信") == "WeChat"
    assert mac.resolve_app_name("网易 云音乐") == "NeteaseMusic"
    assert mac.resolve_app_name("打开 网易 云 音乐") == "NeteaseMusic"
    assert mac.resolve_app_name("云音乐") == "NeteaseMusic"
    assert mac.resolve_app_name("Net Ease Music") == "NeteaseMusic"
    assert mac.resolve_app_name("网易云音乐.app") == "NeteaseMusic"
    assert mac.open_url("ftp://x").get("ok") is False
    with patch("backend.core.macos_system._run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert mac.open_url("https://example.com")["ok"] is True
        assert run.call_args[0][0][:2] == ["open", "https://example.com"]


def test_open_app_logs_and_returns_normalized():
    with patch("backend.core.macos_system._run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        out = mac.open_app("打开网易 云音乐")
        assert out["ok"] is True
        assert out["app"] == "NeteaseMusic"
        assert out["normalized"] == "网易云音乐"
        assert run.call_args[0][0] == ["open", "-a", "NeteaseMusic"]


def test_close_app_resolves_and_quits_via_osascript():
    assert mac.resolve_app_name("关闭网易云音乐") == "NeteaseMusic"
    assert mac.resolve_app_name("退出微信") == "WeChat"
    assert mac.resolve_app_name("quit Safari") == "Safari"
    with patch("backend.core.macos_system._run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        out = mac.close_app("关闭网易 云音乐")
        assert out["ok"] is True
        assert out["app"] == "NeteaseMusic"
        assert out["normalized"] == "网易云音乐"
        args = run.call_args[0][0]
        assert args[:2] == ["osascript", "-e"]
        assert 'quit app "NeteaseMusic"' in args[2]


def test_close_app_rejects_non_whitelist():
    out = mac.close_app("关闭一个不存在的软件xyz")
    assert out["ok"] is False
    assert "白名单" in out["error"]
    assert "allowed" in out


def test_open_path_rejects_outside_home(tmp_path: Path):
    with patch("backend.core.macos_system.Path.home", return_value=tmp_path):
        assert mac.open_path("/etc/passwd")["ok"] is False


def test_always_on_top_persist_and_notify():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        seen: list[bool] = []
        plugin = SystemControlPlugin(repo, on_always_on_top=seen.append)
        assert plugin.get_always_on_top()["always_on_top"] is True
        out = plugin.set_always_on_top(False)
        assert out["always_on_top"] is False
        assert seen == [False]
        assert plugin.get_always_on_top()["always_on_top"] is False
        conn.close()


def test_volume_set_clamped():
    with patch("backend.core.macos_system._run") as run:
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        out = mac.volume_set(150)
        assert out["ok"] is True
        assert out["volume"] == 100
        args = run.call_args[0][0]
        assert "100" in args[-1]


def test_pet_http_endpoints():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        client = TestClient(app)
        assert client.get("/pet").json()["always_on_top"] is True
        resp = client.put("/pet", json={"always_on_top": False})
        assert resp.status_code == 200
        assert resp.json()["always_on_top"] is False
        assert client.get("/pet").json()["always_on_top"] is False
