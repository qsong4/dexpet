"""Live2D config helpers shared by backend and desktop (no OpenGL).

Optional dependency: live2d-py. DexPet never bundles Cubism keys or models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

RENDERER_SPRITE = "sprite"
RENDERER_LIVE2D = "live2d"
VALID_RENDERERS = frozenset({RENDERER_SPRITE, RENDERER_LIVE2D})

EXPRESSION_ALIASES: dict[str, tuple[str, ...]] = {
    "idle": ("idle", "normal", "default", "neutral", "f00", "exp_00"),
    "happy": ("happy", "smile", "joy", "laugh", "f01", "exp_01"),
    "curious": ("curious", "question", "doubt", "think", "f02"),
    "thinking": ("thinking", "think", "doubt", "confused", "f03"),
    "speaking": ("speaking", "talk", "normal", "idle", "f00"),
    "sad": ("sad", "sorrow", "cry", "upset", "f04", "exp_04"),
    "surprised": ("surprised", "surprise", "astonish", "shock", "f05"),
}

MOTION_GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    "idle": ("idle", "idle1", "home"),
    "happy": ("tapbody", "tap_body", "tap", "idle"),
    "curious": ("taphead", "tap_head", "flickhead", "idle"),
    "thinking": ("idle",),
    "speaking": ("idle", "tapbody"),
    "sad": ("idle",),
    "surprised": ("tapbody", "tap", "idle"),
}


def normalize_renderer(value: str | None) -> str:
    raw = (value or RENDERER_SPRITE).strip().lower()
    return raw if raw in VALID_RENDERERS else RENDERER_SPRITE


def live2d_importable() -> bool:
    try:
        import live2d.v3  # noqa: F401

        return True
    except Exception:
        return False


def resolve_model_json(path: str | Path | None) -> Path | None:
    """Return path to a .model3.json / .model.json, or None if not found."""
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    p = Path(text).expanduser()
    if not p.exists():
        return None
    if p.is_file():
        name = p.name.lower()
        if name.endswith(".model3.json") or name.endswith(".model.json"):
            return p.resolve()
        return None
    if not p.is_dir():
        return None
    for pattern in ("*.model3.json", "*.model.json"):
        hits = sorted(p.glob(pattern))
        if hits:
            return hits[0].resolve()
    for pattern in ("*/*.model3.json", "*/*.model.json"):
        hits = sorted(p.glob(pattern))
        if hits:
            return hits[0].resolve()
    return None


def pick_expression_id(emotion: str, expression_ids: list[str]) -> str | None:
    if not expression_ids:
        return None
    aliases = EXPRESSION_ALIASES.get(emotion, ())
    lowered = {e.lower(): e for e in expression_ids}
    for alias in aliases:
        if alias in lowered:
            return lowered[alias]
    for alias in aliases:
        for key, original in lowered.items():
            if alias in key:
                return original
    return None


def pick_motion_group(emotion: str, groups: dict[str, Any] | list[str] | None) -> str | None:
    if not groups:
        return None
    if isinstance(groups, dict):
        names = list(groups.keys())
    else:
        names = list(groups)
    lowered = {n.lower(): n for n in names}
    for alias in MOTION_GROUP_ALIASES.get(emotion, ()):
        if alias in lowered:
            return lowered[alias]
    for alias in MOTION_GROUP_ALIASES.get(emotion, ()):
        for key, original in lowered.items():
            if alias in key:
                return original
    return None


def describe_live2d_status(
    *,
    renderer: str,
    model_path: str,
) -> dict[str, Any]:
    """Snapshot used by /pet and tests (no GL init)."""
    renderer_n = normalize_renderer(renderer)
    available = live2d_importable()
    resolved = resolve_model_json(model_path) if model_path else None
    error: str | None = None
    if renderer_n == RENDERER_LIVE2D:
        if not available:
            error = "未安装 live2d-py（pip install -e '.[live2d]'）"
        elif not (model_path or "").strip():
            error = "未设置 Live2D 模型路径"
        elif resolved is None:
            error = "模型路径无效或找不到 .model3.json / .model.json"
    return {
        "renderer": renderer_n,
        "live2d_model_path": (model_path or "").strip(),
        "live2d_available": available,
        "live2d_model_resolved": str(resolved) if resolved else None,
        "live2d_error": error,
        "effective_renderer": (
            RENDERER_LIVE2D
            if renderer_n == RENDERER_LIVE2D and error is None
            else RENDERER_SPRITE
        ),
    }
