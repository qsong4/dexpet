"""Live2D config resolution, fallback status, and /pet API."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from shared.live2d_config import (
    RENDERER_LIVE2D,
    RENDERER_SPRITE,
    describe_live2d_status,
    live2d_importable,
    normalize_renderer,
    pick_expression_id,
    pick_motion_group,
    resolve_model_json,
)


def test_normalize_renderer():
    assert normalize_renderer(None) == RENDERER_SPRITE
    assert normalize_renderer("LIVE2D") == RENDERER_LIVE2D
    assert normalize_renderer("nope") == RENDERER_SPRITE


def test_resolve_model_json_file_and_dir(tmp_path: Path):
    assert resolve_model_json("") is None
    assert resolve_model_json(tmp_path / "missing") is None

    model = tmp_path / "Cat.model3.json"
    model.write_text("{}", encoding="utf-8")
    assert resolve_model_json(model) == model.resolve()
    assert resolve_model_json(tmp_path) == model.resolve()

    nested = tmp_path / "pack"
    nested.mkdir()
    nested_model = nested / "Hi.model.json"
    nested_model.write_text("{}", encoding="utf-8")
    # top-level model3 wins over nested
    assert resolve_model_json(tmp_path) == model.resolve()

    only_nested = tmp_path / "only"
    only_nested.mkdir()
    nested2 = only_nested / "m" / "x.model3.json"
    nested2.parent.mkdir()
    nested2.write_text("{}", encoding="utf-8")
    assert resolve_model_json(only_nested) == nested2.resolve()


def test_describe_fallback_without_path(monkeypatch):
    monkeypatch.setattr("shared.live2d_config.live2d_importable", lambda: True)
    status = describe_live2d_status(renderer="live2d", model_path="")
    assert status["effective_renderer"] == RENDERER_SPRITE
    assert status["live2d_error"]


def test_describe_fallback_bad_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shared.live2d_config.live2d_importable", lambda: True)
    status = describe_live2d_status(
        renderer="live2d",
        model_path=str(tmp_path / "empty"),
    )
    assert status["effective_renderer"] == RENDERER_SPRITE
    assert "无效" in (status["live2d_error"] or "")


def test_describe_ready(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shared.live2d_config.live2d_importable", lambda: True)
    model = tmp_path / "A.model3.json"
    model.write_text("{}", encoding="utf-8")
    status = describe_live2d_status(renderer="live2d", model_path=str(tmp_path))
    assert status["effective_renderer"] == RENDERER_LIVE2D
    assert status["live2d_error"] is None
    assert status["live2d_model_resolved"] == str(model.resolve())


def test_describe_without_package(monkeypatch):
    monkeypatch.setattr("shared.live2d_config.live2d_importable", lambda: False)
    status = describe_live2d_status(renderer="live2d", model_path="/x")
    assert status["live2d_available"] is False
    assert status["effective_renderer"] == RENDERER_SPRITE


def test_pick_expression_and_motion():
    assert pick_expression_id("happy", ["F01", "Smile"]) == "Smile"
    assert pick_expression_id("sad", ["exp_sad_01"]) == "exp_sad_01"
    assert pick_motion_group("happy", {"Idle": [], "TapBody": []}) == "TapBody"


def test_pet_api_renderer_roundtrip():
    with tempfile.TemporaryDirectory() as db_tmp:
        app = create_app(db_file=str(Path(db_tmp) / "t.db"))
        client = TestClient(app)
        got = client.get("/pet").json()
        assert got["renderer"] == "sprite"
        assert "live2d_available" in got
        assert got["effective_renderer"] == "sprite"

        put = client.put(
            "/pet",
            json={"renderer": "live2d", "live2d_model_path": "/no/such/model"},
        )
        assert put.status_code == 200
        body = put.json()
        assert body["renderer"] == "live2d"
        assert body["live2d_model_path"] == "/no/such/model"
        assert body["effective_renderer"] == "sprite"
        assert body["live2d_error"]

        back = client.put("/pet", json={"renderer": "sprite"})
        assert back.json()["renderer"] == "sprite"


def test_live2d_import_smoke():
    """If optional dep is installed, import should succeed; otherwise skip logic via bool."""
    available = live2d_importable()
    if available:
        import live2d.v3 as live2d

        assert hasattr(live2d, "LAppModel")
        assert hasattr(live2d, "init")
    else:
        assert available is False
