"""Desktop pet wander: short pacing + occasional long walks."""

from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from desktop.window import PetWindow


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


class WanderController(QObject):
    def __init__(self, window: PetWindow) -> None:
        super().__init__(window)
        self.window = window
        self.enabled = True
        self._pause_reasons: set[str] = set()
        self._mode = "idle"  # idle | pacing | walking
        self._next_at = time.monotonic() + random.uniform(2.0, 5.0)
        self._pending_long = False
        self._from = QPoint()
        self._to = QPoint()
        self._anim_t0 = 0.0
        self._anim_dur = 1.0
        self._facing = 1

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self._mode = "idle"
        else:
            self._next_at = time.monotonic() + random.uniform(1.5, 3.0)

    def pause(self, reason: str) -> None:
        self._pause_reasons.add(reason)
        self._mode = "idle"

    def resume(self, reason: str) -> None:
        self._pause_reasons.discard(reason)
        if not self._pause_reasons:
            self._next_at = time.monotonic() + random.uniform(1.0, 2.5)

    @property
    def paused(self) -> bool:
        return bool(self._pause_reasons) or not self.enabled

    def _bounds(self) -> QRect:
        screen = QApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1280, 800)
        return screen.availableGeometry()

    def _clamp(self, pos: QPoint) -> QPoint:
        geo = self.window.geometry()
        area = self._bounds()
        x = max(area.left(), min(pos.x(), area.right() - geo.width() + 1))
        y = max(area.top(), min(pos.y(), area.bottom() - geo.height() + 1))
        return QPoint(x, y)

    def _start_move(self, target: QPoint, duration: float) -> None:
        self._from = self.window.pos()
        self._to = self._clamp(target)
        dx = self._to.x() - self._from.x()
        if abs(dx) > 2:
            self._facing = 1 if dx > 0 else -1
            self.window.sprite.set_facing(self._facing)
        self._anim_t0 = time.monotonic()
        self._anim_dur = max(0.35, duration)
        dist = math.hypot(dx, self._to.y() - self._from.y())
        if dist < 2:
            self._mode = "idle"
            self._schedule_next()
            return
        self._mode = "walking" if dist > 80 else "pacing"

    def _schedule_next(self) -> None:
        # Mostly short paces; occasionally a longer walk
        if random.random() < 0.18:
            self._next_at = time.monotonic() + random.uniform(8.0, 20.0)
            self._pending_long = True
        else:
            self._next_at = time.monotonic() + random.uniform(3.0, 8.0)
            self._pending_long = False

    def _pick_target(self, long_walk: bool) -> QPoint:
        cur = self.window.pos()
        area = self._bounds()
        if long_walk:
            x = random.randint(area.left(), max(area.left(), area.right() - self.window.width()))
            y = random.randint(area.top(), max(area.top(), area.bottom() - self.window.height()))
            return QPoint(x, y)
        dx = random.randint(-60, 60)
        dy = random.randint(-28, 28)
        return QPoint(cur.x() + dx, cur.y() + dy)

    def _tick(self) -> None:
        if self.paused:
            return
        now = time.monotonic()
        if self._mode in {"pacing", "walking"}:
            t = (now - self._anim_t0) / self._anim_dur
            if t >= 1.0:
                self.window.move(self._to)
                self._mode = "idle"
                self._schedule_next()
                return
            e = _ease_in_out(t)
            x = int(self._from.x() + (self._to.x() - self._from.x()) * e)
            y = int(self._from.y() + (self._to.y() - self._from.y()) * e)
            self.window.move(self._clamp(QPoint(x, y)))
            return

        if now < self._next_at:
            return
        long_walk = self._pending_long
        target = self._pick_target(long_walk=long_walk)
        duration = random.uniform(2.2, 4.0) if long_walk else random.uniform(0.45, 1.1)
        self._start_move(target, duration)
