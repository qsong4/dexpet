"""Pet display settings (renderer mode + Live2D path) stored in pet_state."""

from __future__ import annotations

from typing import Any

from backend.db.repository import Repository
from shared.live2d_config import (
    RENDERER_SPRITE,
    describe_live2d_status,
    normalize_renderer,
)

KEY_RENDERER = "renderer"
KEY_LIVE2D_PATH = "live2d_model_path"


def load_pet_display(repo: Repository) -> dict[str, Any]:
    renderer = normalize_renderer(repo.get_pet_state(KEY_RENDERER, RENDERER_SPRITE))
    path = repo.get_pet_state(KEY_LIVE2D_PATH, "") or ""
    status = describe_live2d_status(renderer=renderer, model_path=path)
    always = repo.get_pet_state("always_on_top", "1") != "0"
    return {"always_on_top": always, **status}


def save_pet_display(
    repo: Repository,
    *,
    renderer: str | None = None,
    live2d_model_path: str | None = None,
) -> dict[str, Any]:
    if renderer is not None:
        repo.set_pet_state(KEY_RENDERER, normalize_renderer(renderer))
    if live2d_model_path is not None:
        repo.set_pet_state(KEY_LIVE2D_PATH, live2d_model_path.strip())
    return load_pet_display(repo)
