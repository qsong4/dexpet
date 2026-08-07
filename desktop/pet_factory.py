"""Create the desktop pet renderer (sprite or Live2D) with safe fallback."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import QWidget

from desktop.sprite_animator import SpriteAnimator
from shared.live2d_config import (
    RENDERER_LIVE2D,
    RENDERER_SPRITE,
    describe_live2d_status,
    normalize_renderer,
)

logger = logging.getLogger("dexpet.pet_factory")


def create_pet_renderer(
    parent: QWidget | None,
    *,
    renderer: str | None = None,
    model_path: str | None = None,
) -> tuple[QWidget, dict[str, Any]]:
    """Return (widget, status_dict). Widget always implements set_emotion/set_facing."""
    status = describe_live2d_status(
        renderer=normalize_renderer(renderer),
        model_path=model_path or "",
    )
    want = status["effective_renderer"]
    if want == RENDERER_LIVE2D:
        try:
            from desktop.live2d_widget import Live2DPetWidget

            widget = Live2DPetWidget(model_path or "", parent=parent)
            status = {**status, "effective_renderer": RENDERER_LIVE2D, "live2d_error": None}
            return widget, status
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live2D widget create failed, falling back to sprite: %s", exc)
            status = {
                **status,
                "effective_renderer": RENDERER_SPRITE,
                "live2d_error": str(exc),
            }
    sprite = SpriteAnimator(parent)
    return sprite, status
