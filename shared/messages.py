"""Shared WebSocket / HTTP message schemas for DexPet."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

ProfileName = str  # profile id


class MessageType(str, Enum):
    USER_MESSAGE = "user_message"
    TOKEN = "token"
    EMOTION_CHANGED = "emotion_changed"
    TOOL_STATUS = "tool_status"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    DONE = "done"
    REMINDER = "reminder"
    PET_SETTINGS = "pet_settings"


class PetSettingsUpdate(BaseModel):
    always_on_top: bool | None = None
    # sprite | live2d — desktop falls back to sprite if Live2D unavailable
    renderer: Literal["sprite", "live2d"] | None = None
    live2d_model_path: str | None = None


class AppWhitelistEntry(BaseModel):
    alias: str
    app: str


class AppWhitelistUpdate(BaseModel):
    entries: list[AppWhitelistEntry]


class Envelope(BaseModel):
    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class UserMessagePayload(BaseModel):
    text: str
    session_id: str | None = None


class TokenPayload(BaseModel):
    text: str
    session_id: str | None = None


class EmotionChangedPayload(BaseModel):
    state: str


class ToolStatusPayload(BaseModel):
    name: str
    status: Literal["running", "done", "error"]
    detail: str | None = None


class ErrorPayload(BaseModel):
    message: str
    code: str | None = None


class ModelProfilePublic(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    api_key_set: bool = False


class ModelProfileCreate(BaseModel):
    name: str = "新模型"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str | None = None
    activate: bool = False


class ModelProfileUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    activate: bool = False


class ActiveProfileUpdate(BaseModel):
    active_profile: str


class LLMConfigPublic(BaseModel):
    active_profile: str
    provider_preset: str  # alias of active for backward compat
    base_url: str
    model: str
    api_key_set: bool
    profiles: list[ModelProfilePublic]


class ProfileConfig(BaseModel):
    """Deprecated dual-slot shape."""

    base_url: str
    model: str
    api_key_set: bool = False


class LLMConfigUpdate(BaseModel):
    """Legacy upsert by profile id (provider_preset). Prefer /config/profiles."""

    provider_preset: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str | None = None
    activate: bool = True
    name: str | None = None


class MemoryConfigUpdate(BaseModel):
    enabled: bool | None = None
    digest_hour: int | None = None
    digest_minute: int | None = None
    proactive_enabled: bool | None = None
    proactive_checks_min: int | None = None
    proactive_checks_max: int | None = None
    proactive_checks_per_day: int | None = None
    proactive_window_start: str | None = None
    proactive_window_end: str | None = None
    proactive_min_gap_minutes: int | None = None
    proactive_max_asks_per_day: int | None = None
    proactive_ask_cooldown_minutes: int | None = None
    proactive_morning_enabled: bool | None = None
    proactive_morning_hour: int | None = None
    proactive_morning_minute: int | None = None


class MemoryProfileUpdate(BaseModel):
    """Save profile.md. Optimistic concurrency via if_mtime; force=True overwrites."""

    content: str
    if_mtime: float | None = None
    force: bool = False
