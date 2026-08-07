"""Emotion finite state machine for the desktop pet."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
import re
import time


class Emotion(str, Enum):
    IDLE = "idle"
    HAPPY = "happy"
    CURIOUS = "curious"
    THINKING = "thinking"
    SPEAKING = "speaking"
    SAD = "sad"
    SURPRISED = "surprised"


KEYWORD_MAP: list[tuple[Emotion, tuple[str, ...]]] = [
    (Emotion.HAPPY, ("开心", "高兴", "太好了", "棒", "哈哈", "happy", "great", "yay")),
    (Emotion.SAD, ("难过", "抱歉", "失败", "错误", "对不起", "sad", "sorry", "fail")),
    (Emotion.SURPRISED, ("哇", "居然", "惊讶", "surprise", "wow")),
    (Emotion.CURIOUS, ("呢", "吗", "？", "?", "curious", "wonder")),
]

EMOTION_PROMPT: dict[Emotion, str] = {
    Emotion.IDLE: "你现在心情平静、轻松。",
    Emotion.HAPPY: "你现在很开心，语气活泼一点。",
    Emotion.CURIOUS: "你现在很好奇，喜欢追问和探索。",
    Emotion.THINKING: "你正在认真思考用户的问题。",
    Emotion.SPEAKING: "你正在对用户说话，保持自然友好。",
    Emotion.SAD: "你有点难过或歉意，语气柔和。",
    Emotion.SURPRISED: "你感到惊讶，语气可以夸张一点。",
}


@dataclass
class EmotionStateMachine:
    state: Emotion = Emotion.IDLE
    idle_timeout_sec: float = 30.0
    _last_active: float = field(default_factory=time.monotonic)
    _on_change: Callable[[Emotion], None] | None = None

    def set_on_change(self, callback: Callable[[Emotion], None] | None) -> None:
        self._on_change = callback

    def _transition(self, new_state: Emotion) -> Emotion:
        if new_state != self.state:
            self.state = new_state
            if self._on_change:
                self._on_change(new_state)
        self._last_active = time.monotonic()
        return self.state

    def on_user_message(self) -> Emotion:
        return self._transition(Emotion.THINKING)

    def on_first_token(self) -> Emotion:
        return self._transition(Emotion.SPEAKING)

    def on_error(self) -> Emotion:
        return self._transition(Emotion.SAD)

    def on_idle_tick(self, now: float | None = None) -> Emotion:
        now = now if now is not None else time.monotonic()
        if self.state in {
            Emotion.HAPPY,
            Emotion.CURIOUS,
            Emotion.SAD,
            Emotion.SURPRISED,
            Emotion.SPEAKING,
        }:
            if now - self._last_active >= self.idle_timeout_sec:
                return self._transition(Emotion.IDLE)
        return self.state

    def apply_labeled_emotion(self, label: str | Emotion) -> Emotion:
        if isinstance(label, Emotion):
            emotion = label
        else:
            try:
                emotion = Emotion(label.lower().strip())
            except ValueError:
                emotion = Emotion.IDLE
        if emotion == Emotion.THINKING:
            emotion = Emotion.CURIOUS
        if emotion == Emotion.SPEAKING:
            emotion = Emotion.HAPPY
        return self._transition(emotion)

    def infer_from_text(self, text: str) -> Emotion:
        lowered = text.lower()
        for emotion, keywords in KEYWORD_MAP:
            if any(k.lower() in lowered for k in keywords):
                return self._transition(emotion)
        return self._transition(Emotion.HAPPY)

    def prompt_fragment(self) -> str:
        return EMOTION_PROMPT.get(self.state, EMOTION_PROMPT[Emotion.IDLE])

    @staticmethod
    def parse_emotion_tag(text: str) -> tuple[str, Emotion | None]:
        """Parse trailing [[emotion:happy]] tag; return cleaned text and emotion."""
        pattern = re.compile(r"\[\[\s*emotion\s*:\s*([a-zA-Z_]+)\s*\]\]\s*$", re.I)
        match = pattern.search(text)
        if not match:
            return text, None
        cleaned = text[: match.start()].rstrip()
        try:
            return cleaned, Emotion(match.group(1).lower())
        except ValueError:
            return cleaned, None
