"""Desktop re-export of shared Live2D config helpers."""

from shared.live2d_config import (
    EXPRESSION_ALIASES,
    MOTION_GROUP_ALIASES,
    RENDERER_LIVE2D,
    RENDERER_SPRITE,
    VALID_RENDERERS,
    describe_live2d_status,
    live2d_importable,
    normalize_renderer,
    pick_expression_id,
    pick_motion_group,
    resolve_model_json,
)

__all__ = [
    "EXPRESSION_ALIASES",
    "MOTION_GROUP_ALIASES",
    "RENDERER_LIVE2D",
    "RENDERER_SPRITE",
    "VALID_RENDERERS",
    "describe_live2d_status",
    "live2d_importable",
    "normalize_renderer",
    "pick_expression_id",
    "pick_motion_group",
    "resolve_model_json",
]
