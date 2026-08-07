"""Custom sprite storage and HTTP API tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.sprites import delete_sprite, list_sprites, save_sprite


def test_save_list_delete_sprite(tmp_path: Path):
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path = save_sprite("happy", png, "cat.png", root=tmp_path)
    assert path.name == "happy.png"
    assert list_sprites(tmp_path)["happy"]["set"] is True
    assert list_sprites(tmp_path)["idle"]["set"] is False
    assert delete_sprite("happy", root=tmp_path) is True
    assert list_sprites(tmp_path)["happy"]["set"] is False


def test_sprites_http_upload(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.core.sprites.sprites_dir", lambda: tmp_path)
    monkeypatch.setattr("backend.paths.sprites_dir", lambda: tmp_path)

    with tempfile.TemporaryDirectory() as db_tmp:
        app = create_app(db_file=str(Path(db_tmp) / "t.db"))
        client = TestClient(app)
        listed = client.get("/sprites").json()
        assert listed["sprites"]["idle"]["set"] is False

        tiny = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        resp = client.post(
            "/sprites/idle",
            files={"file": ("idle.png", tiny, "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["sprites"]["idle"]["set"] is True
        img = client.get("/sprites/idle/image")
        assert img.status_code == 200
        assert client.delete("/sprites/idle").json()["deleted"] is True
