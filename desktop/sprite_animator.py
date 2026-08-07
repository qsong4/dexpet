"""Cute cat sprite painter with emotion states + optional custom images."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QRadialGradient,
    QPainterPath,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from backend.core.sprites import ALLOWED_EXT, EMOTIONS
from backend.paths import sprites_dir

# (fur_light, fur_mid, fur_dark, accent)
STATE_PALETTE: dict[str, tuple[QColor, QColor, QColor, QColor]] = {
    "idle": (QColor("#F6D7A8"), QColor("#E8B86D"), QColor("#C98B3C"), QColor("#FF8FAB")),
    "happy": (QColor("#FFE0A8"), QColor("#F0B85A"), QColor("#D4892E"), QColor("#FF6B9D")),
    "curious": (QColor("#F3D2B0"), QColor("#E0A96D"), QColor("#B87A3A"), QColor("#C77DFF")),
    "thinking": (QColor("#E8D2B8"), QColor("#CDB08C"), QColor("#A88860"), QColor("#9BB7C9")),
    "speaking": (QColor("#F8D9A4"), QColor("#E8B65C"), QColor("#C98A30"), QColor("#7ED957")),
    "sad": (QColor("#D9C4A8"), QColor("#B89A78"), QColor("#8F7354"), QColor("#8FA3B0")),
    "surprised": (QColor("#FFD9B0"), QColor("#F0A86A"), QColor("#D47A3A"), QColor("#FF6B4A")),
}


def _find_local_sprite(emotion: str) -> Path | None:
    base = sprites_dir()
    for ext in ALLOWED_EXT:
        path = base / f"{emotion}{ext}"
        if path.is_file():
            return path
    return None


class SpriteAnimator(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._state = "idle"
        self._frame = 0
        self._facing = 1  # 1 = right, -1 = left
        self._pixmaps: dict[str, QPixmap] = {}
        self._mtime_stamp = 0.0
        self._reload_sprites(force=True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(80)

        self._watch = QTimer(self)
        self._watch.timeout.connect(lambda: self._reload_sprites(force=False))
        self._watch.start(2000)

    def set_emotion(self, state: str) -> None:
        self._state = state if state in STATE_PALETTE else "idle"
        self.update()

    def set_facing(self, facing: int) -> None:
        self._facing = 1 if facing >= 0 else -1
        self.update()

    def _dir_mtime(self) -> float:
        base = sprites_dir()
        latest = 0.0
        try:
            for p in base.iterdir():
                if p.suffix.lower() in ALLOWED_EXT:
                    latest = max(latest, p.stat().st_mtime)
        except OSError:
            pass
        return latest

    def _reload_sprites(self, force: bool = False) -> None:
        stamp = self._dir_mtime()
        if not force and stamp == self._mtime_stamp:
            return
        self._mtime_stamp = stamp
        loaded: dict[str, QPixmap] = {}
        for emotion in EMOTIONS:
            path = _find_local_sprite(emotion)
            if path is None:
                continue
            pm = QPixmap(str(path))
            if not pm.isNull():
                loaded[emotion] = pm
        self._pixmaps = loaded
        self.update()

    def _custom_for(self, state: str) -> QPixmap | None:
        if state in self._pixmaps:
            return self._pixmaps[state]
        # Fallback chain: idle → any available
        if "idle" in self._pixmaps:
            return self._pixmaps["idle"]
        if self._pixmaps:
            return next(iter(self._pixmaps.values()))
        return None

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % 48
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        custom = self._custom_for(self._state)
        if custom is not None:
            self._paint_custom(painter, custom)
        else:
            self._paint_drawn_cat(painter)

    def _paint_custom(self, painter: QPainter, pixmap: QPixmap) -> None:
        t = self._frame / 48.0
        bounce = math.sin(t * math.pi * 2) * 2.2
        if self._state in {"happy", "speaking"}:
            bounce = -3.0 if (self._frame // 3) % 2 == 0 else 2.5
        elif self._state == "surprised":
            bounce = -5.0 if self._frame % 6 < 3 else 1.0
        elif self._state == "sad":
            bounce = 4.0

        target = QRectF(10, 8 + bounce, 160, 150)
        scaled = pixmap.scaled(
            int(target.width()),
            int(target.height()),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._facing < 0:
            scaled = scaled.transformed(QTransform().scale(-1, 1))
        x = target.center().x() - scaled.width() / 2
        y = target.center().y() - scaled.height() / 2
        painter.drawPixmap(int(x), int(y), scaled)

    def _paint_drawn_cat(self, painter: QPainter) -> None:
        light, mid, dark, accent = STATE_PALETTE.get(self._state, STATE_PALETTE["idle"])

        t = self._frame / 48.0
        breathe = math.sin(t * math.pi * 2) * 1.8
        bounce = breathe
        if self._state in {"happy", "speaking"}:
            bounce = -4.0 if (self._frame // 3) % 2 == 0 else 3.0
        elif self._state == "surprised":
            bounce = -6.0 if self._frame % 6 < 3 else 1.0
        elif self._state == "thinking":
            bounce = math.sin(t * math.pi * 4) * 1.5
        elif self._state == "sad":
            bounce = 6.0

        cx, cy = 90.0, 96.0 + bounce
        if self._facing < 0:
            painter.translate(180, 0)
            painter.scale(-1, 1)

        tail_wag = math.sin(t * math.pi * 4) * (14 if self._state == "happy" else 7)

        tail = QPainterPath()
        tail.moveTo(cx + 40, cy + 18)
        tail.cubicTo(
            cx + 70 + tail_wag * 0.3,
            cy + 8,
            cx + 78 + tail_wag,
            cy - 28,
            cx + 58 + tail_wag * 0.5,
            cy - 46,
        )
        painter.setPen(QPen(dark, 11, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(tail)
        painter.setPen(QPen(mid, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(tail)

        body_grad = QRadialGradient(QPointF(cx - 10, cy + 8), 70)
        body_grad.setColorAt(0.0, light)
        body_grad.setColorAt(0.55, mid)
        body_grad.setColorAt(1.0, dark)
        painter.setPen(QPen(QColor(60, 40, 20, 40), 1.2))
        painter.setBrush(QBrush(body_grad))
        painter.drawEllipse(QPointF(cx, cy + 28), 48, 40)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 248, 236, 210)))
        painter.drawEllipse(QPointF(cx, cy + 34), 24, 22)

        head_grad = QRadialGradient(QPointF(cx - 14, cy - 28), 68)
        head_grad.setColorAt(0.0, QColor(255, 255, 255, 70))
        head_grad.setColorAt(0.3, light)
        head_grad.setColorAt(1.0, mid)
        painter.setPen(QPen(QColor(60, 40, 20, 40), 1.2))
        painter.setBrush(QBrush(head_grad))
        painter.drawEllipse(QPointF(cx, cy - 18), 52, 46)

        painter.setBrush(QBrush(mid))
        painter.setPen(QPen(QColor(60, 40, 20, 35), 1))
        left_ear = QPainterPath()
        left_ear.moveTo(cx - 34, cy - 42)
        left_ear.lineTo(cx - 52, cy - 78)
        left_ear.lineTo(cx - 10, cy - 54)
        left_ear.closeSubpath()
        painter.drawPath(left_ear)
        right_ear = QPainterPath()
        right_ear.moveTo(cx + 34, cy - 42)
        right_ear.lineTo(cx + 52, cy - 78)
        right_ear.lineTo(cx + 10, cy - 54)
        right_ear.closeSubpath()
        painter.drawPath(right_ear)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(accent.red(), accent.green(), accent.blue(), 170)))
        inner_l = QPainterPath()
        inner_l.moveTo(cx - 32, cy - 46)
        inner_l.lineTo(cx - 44, cy - 70)
        inner_l.lineTo(cx - 16, cy - 54)
        inner_l.closeSubpath()
        painter.drawPath(inner_l)
        inner_r = QPainterPath()
        inner_r.moveTo(cx + 32, cy - 46)
        inner_r.lineTo(cx + 44, cy - 70)
        inner_r.lineTo(cx + 16, cy - 54)
        inner_r.closeSubpath()
        painter.drawPath(inner_r)

        blush_a = 55 if self._state != "sad" else 20
        if self._state == "happy":
            blush_a = 90
        painter.setBrush(QBrush(QColor(255, 120, 140, blush_a)))
        painter.drawEllipse(QPointF(cx - 34, cy - 6), 11, 7)
        painter.drawEllipse(QPointF(cx + 34, cy - 6), 11, 7)

        eye_y = cy - 22 + (4 if self._state == "sad" else 0)
        look = 0.0
        if self._state == "curious":
            look = 3.5 if (self._frame // 6) % 2 == 0 else -3.5
        elif self._state == "thinking":
            look = 2.0

        if self._state == "happy":
            painter.setPen(QPen(QColor("#2A1F16"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(cx - 32, eye_y - 4, 22, 16), 20 * 16, 160 * 16)
            painter.drawArc(QRectF(cx + 10, eye_y - 4, 22, 16), 20 * 16, 160 * 16)
        else:
            painter.setPen(QPen(QColor(60, 40, 20, 30), 1))
            painter.setBrush(QBrush(QColor("#FFF8EF")))
            eye_h = 26 if self._state == "surprised" else 22
            eye_w = 18 if self._state != "sad" else 16
            painter.drawEllipse(QRectF(cx - 30, eye_y - eye_h / 2, eye_w, eye_h))
            painter.drawEllipse(QRectF(cx + 12, eye_y - eye_h / 2, eye_w, eye_h))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2A1F16")))
            pupil_h = 14 if self._state == "surprised" else 11
            pupil_w = 5.5 if self._state != "surprised" else 8
            painter.drawEllipse(QPointF(cx - 21 + look, eye_y + 1), pupil_w / 2, pupil_h / 2)
            painter.drawEllipse(QPointF(cx + 21 + look, eye_y + 1), pupil_w / 2, pupil_h / 2)

            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.drawEllipse(QPointF(cx - 23 + look, eye_y - 3), 2.2, 2.2)
            painter.drawEllipse(QPointF(cx + 19 + look, eye_y - 3), 2.2, 2.2)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#FF8FA3")))
        nose = QPainterPath()
        nose.moveTo(cx, cy - 4)
        nose.lineTo(cx - 5, cy - 10)
        nose.lineTo(cx + 5, cy - 10)
        nose.closeSubpath()
        painter.drawPath(nose)

        painter.setPen(QPen(QColor("#2A1F16"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._state in {"happy", "speaking"}:
            painter.drawArc(QRectF(cx - 10, cy - 6, 10, 10), 200 * 16, 140 * 16)
            painter.drawArc(QRectF(cx, cy - 6, 10, 10), 200 * 16, 140 * 16)
        elif self._state == "sad":
            painter.drawArc(QRectF(cx - 8, cy + 2, 16, 12), 30 * 16, 120 * 16)
        elif self._state == "surprised":
            painter.setBrush(QBrush(QColor("#2A1F16")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy + 2), 4.5, 5.5)
        else:
            painter.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 2))
            painter.drawArc(QRectF(cx - 8, cy - 2, 8, 8), 200 * 16, 120 * 16)
            painter.drawArc(QRectF(cx, cy - 2, 8, 8), 220 * 16, 120 * 16)

        painter.setPen(QPen(QColor(80, 60, 40, 120), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        wy = cy - 2
        for dy, dx in ((-4, 0), (0, 2), (4, 0)):
            painter.drawLine(QPointF(cx - 14, wy + dy), QPointF(cx - 48 - dx, wy + dy - 2))
            painter.drawLine(QPointF(cx + 14, wy + dy), QPointF(cx + 48 + dx, wy + dy - 2))

        painter.setPen(QPen(QColor(60, 40, 20, 30), 1))
        painter.setBrush(QBrush(light))
        painter.drawEllipse(QPointF(cx - 22, cy + 58), 12, 9)
        painter.drawEllipse(QPointF(cx + 22, cy + 58), 12, 9)
        painter.setBrush(QBrush(QColor(255, 200, 200, 140)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx - 22, cy + 59), 6, 4)
        painter.drawEllipse(QPointF(cx + 22, cy + 59), 6, 4)

        if self._state == "thinking":
            for i in range(3):
                alpha = 160 if (self._frame // 4) % 3 == i else 50
                painter.setBrush(QBrush(QColor(70, 55, 40, alpha)))
                painter.drawEllipse(
                    QPointF(cx + 50 + i * 10, cy - 58 - i * 8),
                    3.2 + i * 0.5,
                    3.2 + i * 0.5,
                )
