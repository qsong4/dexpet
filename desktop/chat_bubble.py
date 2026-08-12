"""Lightweight AI-style chat overlay for the desktop pet."""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Qt,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    QRectF,
    QTimer,
    QSize,
    QPointF,
)
from PySide6.QtGui import (
    QFont,
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPainterPath,
    QKeyEvent,
    QTextOption,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

TAIL_H = 10
PAD_X = 12
PAD_TOP = 10
PAD_BOTTOM = 10 + TAIL_H
BUBBLE_W = 300
BUBBLE_MAX_H = 320
REPLY_MAX_H = 168
INPUT_MAX_H = 72
INPUT_MIN_H = 34


def _ui_font(size: float = 12.5, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    # Prefer Chinese UI + system sans; avoid missing family alias warnings.
    font.setFamilies(["PingFang SC", "Hiragino Sans GB", "Helvetica Neue"])
    font.setPointSizeF(size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    return font


class _ChatInput(QTextEdit):
    """Modern composer: Enter sends, Shift+Enter inserts newline."""

    submit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatInput")
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(1)
        self.setFixedHeight(INPUT_MIN_H)
        self.textChanged.connect(self._fit_height)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            event.accept()
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)

    def _fit_height(self) -> None:
        doc_h = int(self.document().size().height()) + 12
        self.setFixedHeight(max(INPUT_MIN_H, min(INPUT_MAX_H, doc_h)))


class _ThinkingDots(QWidget):
    """Soft pulsing dots — reading as 'thinking', not ellipsis spam."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setMinimumWidth(52)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._phase = 0.0
        self._timer.start()
        self.show()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.09) % (2 * 3.1416)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        cx = 8.0
        cy = self.height() / 2.0
        for i in range(3):
            t = self._phase - i * 0.85
            # Soft breathe between 0.28 and 0.92 alpha
            wave = 0.5 + 0.5 * math.sin(t)
            a = 0.28 + 0.64 * wave
            r = 2.4 + 0.55 * wave
            painter.setBrush(QBrush(QColor(28, 28, 30, int(a * 220))))
            painter.drawEllipse(QPointF(cx + i * 11, cy), r, r)


class ChatBubble(QFrame):
    """Frosted AI overlay with a soft tail pointing at the pet."""

    submitted = Signal(str)
    # Emitted when preferred height changes so the parent can re-anchor.
    height_changed = Signal()
    # Emitted when fade-out completes and the widget is hidden.
    hide_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatBubble")
        self.setFixedWidth(BUBBLE_W)
        self.setMinimumHeight(96)
        self.setMaximumHeight(BUBBLE_MAX_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("ChatBubble#chatBubble { background: transparent; border: none; }")

        body_font = _ui_font(12.5)
        meta_font = _ui_font(11.5)
        label_font = _ui_font(11.0, QFont.Weight.Medium)

        self._user_label = QLabel("")
        self._user_label.setObjectName("userLabel")
        self._user_label.setWordWrap(True)
        self._user_label.setFont(meta_font)
        self._user_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._user_label.setStyleSheet(
            """
            QLabel#userLabel {
                color: rgba(28, 28, 30, 200);
                background: rgba(28, 28, 30, 8);
                border: 1px solid rgba(28, 28, 30, 10);
                border-radius: 10px;
                padding: 6px 10px;
            }
            """
        )
        self._user_label.hide()

        self._thinking_row = QWidget()
        self._thinking_row.setObjectName("thinkingRow")
        thinking_layout = QHBoxLayout(self._thinking_row)
        thinking_layout.setContentsMargins(2, 2, 2, 2)
        thinking_layout.setSpacing(8)
        self._thinking_label = QLabel("Thinking")
        self._thinking_label.setFont(label_font)
        self._thinking_label.setStyleSheet(
            "QLabel { color: rgba(28, 28, 30, 130); background: transparent; letter-spacing: 0.2px; }"
        )
        self._thinking_dots = _ThinkingDots()
        thinking_layout.addWidget(self._thinking_label, 0, Qt.AlignmentFlag.AlignVCenter)
        thinking_layout.addWidget(self._thinking_dots, 0, Qt.AlignmentFlag.AlignVCenter)
        thinking_layout.addStretch(1)
        self._thinking_row.hide()

        self.reply = QLabel("")
        self.reply.setObjectName("replyLabel")
        self.reply.setWordWrap(True)
        self.reply.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.reply.setMinimumHeight(0)
        self.reply.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.reply.setStyleSheet(
            """
            QLabel#replyLabel {
                color: #1c1c1e;
                background: transparent;
                padding: 2px 2px;
            }
            """
        )
        self.reply.setFont(body_font)
        self.reply.hide()

        self._reply_scroll = QScrollArea()
        self._reply_scroll.setObjectName("replyScroll")
        self._reply_scroll.setWidget(self.reply)
        self._reply_scroll.setWidgetResizable(False)
        self._reply_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._reply_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._reply_scroll.setMaximumHeight(REPLY_MAX_H)
        self._reply_scroll.setMinimumHeight(0)
        self._reply_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._reply_scroll.setStyleSheet(
            """
            QScrollArea#replyScroll {
                background: transparent;
                border: none;
            }
            QScrollArea#replyScroll > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                margin: 2px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(28, 28, 30, 55);
                border-radius: 2px;
                min-height: 16px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(28, 28, 30, 95);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            """
        )
        self._reply_scroll.viewport().setAutoFillBackground(False)
        self._reply_scroll.hide()

        self.input = _ChatInput()
        self.input.setFont(body_font)
        self.input.setPlaceholderText("跟小猫说点什么…")
        self.input.setStyleSheet(
            """
            QTextEdit#chatInput {
                background: transparent;
                border: none;
                padding: 6px 4px;
                color: #1c1c1e;
                selection-background-color: rgba(28, 28, 30, 28);
            }
            """
        )
        self.input.submit_requested.connect(self._emit_submit)

        self._send_btn = QPushButton("↑")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setFixedSize(30, 30)
        self._send_btn.setFont(_ui_font(14, QFont.Weight.DemiBold))
        self._send_btn.setToolTip("发送")
        self._send_btn.setDefault(True)
        self._send_btn.setAutoDefault(True)
        self._send_btn.setStyleSheet(
            """
            QPushButton#sendBtn {
                background: #1c1c1e;
                border: none;
                border-radius: 15px;
                color: #f5f5f7;
                padding: 0;
            }
            QPushButton#sendBtn:hover {
                background: #2c2c2e;
            }
            QPushButton#sendBtn:pressed {
                background: #3a3a3c;
            }
            QPushButton#sendBtn:disabled {
                background: rgba(28, 28, 30, 28);
                color: rgba(28, 28, 30, 70);
            }
            """
        )
        self._send_btn.clicked.connect(self._emit_submit)
        self._send_btn.setEnabled(False)
        self.input.textChanged.connect(self._sync_send_enabled)
        self.input.textChanged.connect(self._notify_height)

        self._composer = QFrame()
        self._composer.setObjectName("composer")
        self._composer.setStyleSheet(
            """
            QFrame#composer {
                background: rgba(28, 28, 30, 6);
                border: 1px solid rgba(28, 28, 30, 12);
                border-radius: 12px;
            }
            """
        )
        composer_row = QHBoxLayout(self._composer)
        composer_row.setContentsMargins(8, 4, 6, 4)
        composer_row.setSpacing(4)
        composer_row.addWidget(self.input, stretch=1)
        composer_row.addWidget(self._send_btn, stretch=0, alignment=Qt.AlignmentFlag.AlignBottom)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAD_X, PAD_TOP, PAD_X, PAD_BOTTOM)
        layout.setSpacing(8)
        layout.addWidget(self._user_label)
        layout.addWidget(self._thinking_row)
        layout.addWidget(self._reply_scroll, stretch=1)
        layout.addWidget(self._composer)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hide()
        self._visible_intent = False
        self._hide_connected = False
        self._waiting = False
        self._last_pref_h = 0

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(BUBBLE_W, min(BUBBLE_MAX_H, max(96, self.minimumSizeHint().height())))

    def preferred_height(self) -> int:
        hint = self.minimumSizeHint().height()
        return min(BUBBLE_MAX_H, max(96, hint))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        body = QRectF(2.5, 2.0, w - 5.0, h - TAIL_H - 3.5)
        radius = 16.0

        # Quiet contact shadow
        shadow = QPainterPath()
        shadow.addRoundedRect(body.adjusted(0, 1.5, 0, 1.5), radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 28)))
        painter.drawPath(shadow)

        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)

        cx = w / 2.0
        tip_y = h - 1.5
        tail = QPainterPath()
        tail.moveTo(cx - 8.5, body.bottom() - 0.5)
        tail.quadTo(cx - 1.2, body.bottom() + 4.5, cx, tip_y)
        tail.quadTo(cx + 1.2, body.bottom() + 4.5, cx + 8.5, body.bottom() - 0.5)
        path = path.united(tail)

        # Frosted light panel — contemporary overlay, not neon glass
        painter.setBrush(QBrush(QColor(250, 250, 252, 236)))
        painter.setPen(QPen(QColor(255, 255, 255, 160), 1.0))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(0, 0, 0, 22), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _disconnect_hide(self) -> None:
        if not self._hide_connected:
            return
        try:
            self._anim.finished.disconnect(self._after_hide)
        except (RuntimeError, TypeError):
            pass
        except Exception:  # noqa: BLE001 — PySide may warn/raise on double disconnect
            pass
        self._hide_connected = False

    def _sync_send_enabled(self) -> None:
        self._send_btn.setEnabled(bool(self.input.toPlainText().strip()))

    def _notify_height(self) -> None:
        h = self.preferred_height()
        if h != self._last_pref_h:
            self._last_pref_h = h
            if self.height() != h and self._visible_intent:
                self.setFixedHeight(h)
            self.height_changed.emit()

    def _emit_submit(self) -> None:
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.input.setFixedHeight(INPUT_MIN_H)
        self._sync_send_enabled()
        self.set_user_message(text)
        self.submitted.emit(text)

    def show_animated(self, focus_input: bool = False) -> None:
        self._visible_intent = True
        self.setFixedHeight(self.preferred_height())
        self.show()
        self.raise_()
        self.update()
        if self._reply_scroll.isVisible():
            self._fit_reply_scroll()
            self._scroll_reply_to_top()
        self._anim.stop()
        self._disconnect_hide()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        if focus_input:
            self.input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.height_changed.emit()

    def hide_animated(self) -> None:
        self._visible_intent = False
        self.input.clearFocus()
        self._stop_waiting()
        self.clear_user_message()
        self._anim.stop()
        self._disconnect_hide()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._after_hide)
        self._hide_connected = True
        self._anim.start()

    def _after_hide(self) -> None:
        self._disconnect_hide()
        if not self._visible_intent:
            # Keep widget hidden but do not clear geometry — parent shrinks atomically.
            self.hide()
            self.input.clearFocus()
            self.hide_finished.emit()

    def _reply_content_width(self) -> int:
        viewport_w = self._reply_scroll.viewport().width()
        if viewport_w > 1:
            return viewport_w
        return max(self.width() - PAD_X * 2 - 8, 40)

    def _fit_reply_scroll(self) -> None:
        if not self.reply.isVisible() and not self.reply.text():
            self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._reply_scroll.setFixedHeight(0)
            return
        content_w = self._reply_content_width()
        self.reply.setFixedWidth(content_w)
        needed = self.reply.heightForWidth(content_w)
        if needed < 0:
            needed = self.reply.sizeHint().height()
        needed = max(needed, 0)
        self.reply.setFixedHeight(needed)
        # Short replies: size to content and hide scrollbar entirely so Qt
        # doesn't reserve a track when height ≈ content (rounding edge cases).
        if needed <= REPLY_MAX_H:
            self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._reply_scroll.setFixedHeight(needed)
        else:
            self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._reply_scroll.setFixedHeight(REPLY_MAX_H)

    def _scroll_reply_to_top(self) -> None:
        bar = self._reply_scroll.verticalScrollBar()
        bar.setValue(0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._reply_scroll.isVisible():
            self._fit_reply_scroll()

    def set_user_message(self, text: str) -> None:
        cleaned = text.strip()
        if cleaned:
            preview = cleaned.replace("\n", " ")
            if len(preview) > 64:
                preview = preview[:63] + "…"
            self._user_label.setText(preview)
            self._user_label.show()
        else:
            self._user_label.clear()
            self._user_label.hide()
        self._relayout_content()

    def clear_user_message(self) -> None:
        self._user_label.clear()
        self._user_label.hide()

    def set_reply(self, text: str) -> None:
        self._stop_waiting()
        cleaned = text.strip()
        if cleaned:
            self.reply.setText(cleaned)
            self.reply.show()
            self._reply_scroll.show()
            self._fit_reply_scroll()
            self._scroll_reply_to_top()
        else:
            self.reply.clear()
            self.reply.hide()
            self._reply_scroll.hide()
            self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._reply_scroll.setFixedHeight(0)
        self._relayout_content()

    def append_reply(self, text: str) -> None:
        self._stop_waiting()
        current = self.reply.text()
        self.set_reply(current + text)

    def clear_reply(self) -> None:
        self._stop_waiting()
        self.reply.clear()
        self.reply.hide()
        self._reply_scroll.hide()
        self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._reply_scroll.setFixedHeight(0)
        self._relayout_content()

    def begin_stream(self) -> None:
        self.clear_reply()
        self._start_waiting()

    def _start_waiting(self) -> None:
        self._waiting = True
        self.reply.clear()
        self.reply.hide()
        self._reply_scroll.hide()
        self._reply_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._reply_scroll.setFixedHeight(0)
        self._thinking_row.show()
        self._thinking_dots.start()
        self._relayout_content()

    def _stop_waiting(self) -> None:
        was = self._waiting
        self._waiting = False
        self._thinking_dots.stop()
        self._thinking_row.hide()
        if was:
            self._relayout_content()

    def _relayout_content(self) -> None:
        self.updateGeometry()
        if self._visible_intent:
            self.setFixedHeight(self.preferred_height())
        self.update()
        self._notify_height()
