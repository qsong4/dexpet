"""Custom pet sprite image storage (per emotion)."""

from __future__ import annotations

from pathlib import Path

from backend.paths import sprites_dir

EMOTIONS: tuple[str, ...] = (
    "idle",
    "happy",
    "curious",
    "thinking",
    "speaking",
    "sad",
    "surprised",
)

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}
EMOTION_LABELS: dict[str, str] = {
    "idle": "待机",
    "happy": "开心",
    "curious": "好奇",
    "thinking": "思考",
    "speaking": "说话",
    "sad": "难过",
    "surprised": "惊讶",
}


def _normalize_emotion(emotion: str) -> str:
    key = emotion.strip().lower()
    if key not in EMOTIONS:
        raise ValueError(f"未知情绪: {emotion}")
    return key


def find_sprite_file(emotion: str, root: Path | None = None) -> Path | None:
    key = _normalize_emotion(emotion)
    base = root or sprites_dir()
    for ext in ALLOWED_EXT:
        path = base / f"{key}{ext}"
        if path.is_file():
            return path
    return None


def list_sprites(root: Path | None = None) -> dict[str, dict]:
    base = root or sprites_dir()
    out: dict[str, dict] = {}
    for emotion in EMOTIONS:
        path = find_sprite_file(emotion, base)
        out[emotion] = {
            "emotion": emotion,
            "label": EMOTION_LABELS[emotion],
            "set": path is not None,
            "url": f"/sprites/{emotion}/image" if path is not None else None,
            "filename": path.name if path is not None else None,
        }
    return out


def save_sprite(emotion: str, data: bytes, filename: str, root: Path | None = None) -> Path:
    key = _normalize_emotion(emotion)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("仅支持 PNG / JPG / WEBP")
    if not data:
        raise ValueError("空文件")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("图片不能超过 8MB")

    base = root or sprites_dir()
    base.mkdir(parents=True, exist_ok=True)
    # Remove previous variants for this emotion
    for old_ext in ALLOWED_EXT:
        old = base / f"{key}{old_ext}"
        if old.exists():
            old.unlink()
    dest = base / f"{key}{ext}"
    dest.write_bytes(data)
    return dest


def delete_sprite(emotion: str, root: Path | None = None) -> bool:
    key = _normalize_emotion(emotion)
    path = find_sprite_file(key, root)
    if path is None:
        return False
    path.unlink(missing_ok=True)
    return True
