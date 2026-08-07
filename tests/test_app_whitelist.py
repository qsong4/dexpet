"""App whitelist settings API tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.app_whitelist import get_app_whitelist, save_app_whitelist
from backend.core.macos_system import open_app, resolve_app_name
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


def test_whitelist_roundtrip_and_open_app():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        save_app_whitelist(repo, {"myapp": "TextEdit", "safari": "Safari"})
        mapping = get_app_whitelist(repo)
        assert resolve_app_name("myapp", mapping) == "TextEdit"
        assert resolve_app_name("unknown", mapping) is None
        from unittest.mock import MagicMock, patch

        with patch("backend.core.macos_system._run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            out = open_app("myapp", aliases=mapping)
            assert out["ok"] is True
            assert out["app"] == "TextEdit"
        conn.close()


def test_whitelist_http():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        client = TestClient(app)
        listed = client.get("/system/app-whitelist").json()
        assert any(e["alias"] == "safari" for e in listed["entries"])

        resp = client.put(
            "/system/app-whitelist",
            json={"entries": [{"alias": "notes", "app": "Notes"}, {"alias": "foo", "app": "FooApp"}]},
        )
        assert resp.status_code == 200
        aliases = {e["alias"] for e in resp.json()["entries"]}
        assert aliases == {"notes", "foo"}

        reset = client.post("/system/app-whitelist/reset").json()
        assert any(e["alias"] == "safari" for e in reset["entries"])
