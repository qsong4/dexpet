"""Main transparent pet window with hover chat bubble."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, Signal, QPoint, QObject, QTimer, QEvent, QSize, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QAction
from PySide6.QtWidgets import (
    QApplication,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QMenu,
)

from backend.paths import DEFAULT_HOST, DEFAULT_PORT
from desktop.chat_bubble import BUBBLE_MAX_H, BUBBLE_W, ChatBubble
from desktop.pet_factory import create_pet_renderer
from desktop.wander import WanderController
from desktop.ws_client import WsClient
from shared.live2d_config import RENDERER_SPRITE, normalize_renderer

PET_W = 196
PET_H = 196
# Room for bubble max height + gap above the sprite (no shared layout).
CHAT_EXTRA_H = BUBBLE_MAX_H + 8
CHAT_W = BUBBLE_W + 16
SPRITE_BOTTOM_PAD = 8


class _Bridge(QObject):
    message = Signal(dict)
    status = Signal(str)


class PetWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DexPet")
        self._always_on_top = True
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMinimumSize(PET_W, PET_H)

        self._drag_pos: QPoint | None = None
        self._session_id: str | None = None
        self._streaming = False
        self._chat_pinned = False
        self._renderer = RENDERER_SPRITE
        self._live2d_model_path = ""
        self._live2d_status: dict = {}
        self._bridge = _Bridge()
        self._bridge.message.connect(self._on_ws_message)
        self._bridge.status.connect(self._on_status)

        # Pet renderer owns the layout slot; bubble is an absolute overlay so
        # hide/show never reflows the pet (fixes vertical flash on dismiss).
        self.sprite, self._live2d_status = create_pet_renderer(self)
        self.sprite.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, SPRITE_BOTTOM_PAD)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self._layout.addWidget(self.sprite, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.bubble = ChatBubble(self)
        self.bubble.submitted.connect(self._send)
        self.bubble.hide_finished.connect(self._shrink_keep_cat)
        self.bubble.height_changed.connect(self._position_bubble)
        self.bubble.hide()

        self._apply_idle_geometry()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._maybe_hide_bubble)

        self.client = WsClient(
            on_message=lambda m: self._bridge.message.emit(m),
            on_status=lambda s: self._bridge.status.emit(s),
        )
        self.client.start()
        self.wander = WanderController(self)
        QTimer.singleShot(400, self._load_pet_settings)

    def _apply_window_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # Changing flags hides the window; re-show if it was visible.
        if getattr(self, "_shown_once", False):
            self.show()

    def set_always_on_top(self, enabled: bool) -> None:
        enabled = bool(enabled)
        shown = getattr(self, "_shown_once", False)
        if enabled == self._always_on_top and shown:
            return
        self._always_on_top = enabled
        was_visible = self.isVisible()
        self._apply_window_flags()
        if was_visible or shown:
            self.show()
            self.raise_()

    def _load_pet_settings(self) -> None:
        try:
            with urllib.request.urlopen(
                f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/pet", timeout=2
            ) as resp:
                data = json.loads(resp.read().decode())
            self.set_always_on_top(bool(data.get("always_on_top", True)))
            self._apply_renderer_settings(data, force=True)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass

    def _apply_renderer_settings(self, data: dict, *, force: bool = False) -> None:
        renderer = normalize_renderer(data.get("renderer"))
        path = str(data.get("live2d_model_path") or "")
        if (
            not force
            and renderer == self._renderer
            and path == self._live2d_model_path
        ):
            return
        self._renderer = renderer
        self._live2d_model_path = path
        self._replace_pet_renderer(renderer, path)

    def _replace_pet_renderer(self, renderer: str, model_path: str) -> None:
        prev_state = getattr(self.sprite, "_state", "idle")
        prev_facing = getattr(self.sprite, "_facing", 1)
        new_widget, status = create_pet_renderer(
            self,
            renderer=renderer,
            model_path=model_path,
        )
        self._live2d_status = status
        new_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        old = self.sprite
        self._layout.replaceWidget(old, new_widget)
        self.sprite = new_widget
        old.setParent(None)
        old.deleteLater()
        if hasattr(self.sprite, "set_emotion"):
            self.sprite.set_emotion(prev_state)
        if hasattr(self.sprite, "set_facing"):
            self.sprite.set_facing(prev_facing)
        err = status.get("live2d_error")
        if err and normalize_renderer(renderer) != RENDERER_SPRITE:
            print(f"DexPet Live2D fallback to sprite: {err}", flush=True)
        # GL load happens in initializeGL; if it fails, fall back shortly after show.
        if status.get("effective_renderer") == "live2d":
            QTimer.singleShot(800, self._check_live2d_gl_ready)
        self._position_bubble()

    def _check_live2d_gl_ready(self) -> None:
        # Live2DPetWidget sets _ready after initializeGL. If the GL context never
        # comes up (common when shaders are missing from a frozen .app), load_error
        # stays None and the translucent window looks like a failed launch.
        ready = getattr(self.sprite, "_ready", True)
        err = getattr(self.sprite, "load_error", None)
        if ready and not err:
            return
        if not err:
            err = "Live2D OpenGL 未就绪（将回退精灵帧）"
        print(f"DexPet Live2D GL fallback: {err}", flush=True)
        self._live2d_status = {
            **self._live2d_status,
            "effective_renderer": RENDERER_SPRITE,
            "live2d_error": err,
        }
        new_widget, status = create_pet_renderer(
            self, renderer=RENDERER_SPRITE, model_path=""
        )
        self._live2d_status = {**self._live2d_status, **status}
        prev_state = getattr(self.sprite, "_state", "idle")
        old = self.sprite
        self._layout.replaceWidget(old, new_widget)
        self.sprite = new_widget
        old.setParent(None)
        old.deleteLater()
        self.sprite.set_emotion(prev_state)

    def _put_always_on_top(self, enabled: bool) -> None:
        body = json.dumps({"always_on_top": enabled}).encode()
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/pet",
            data=body,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
            self.set_always_on_top(bool(data.get("always_on_top", enabled)))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            # Apply locally even if backend unreachable
            self.set_always_on_top(enabled)

    def _apply_idle_geometry(self) -> None:
        self.setFixedSize(QSize(PET_W, PET_H))

    def _apply_chat_geometry(self) -> None:
        # Grow upward so the cat stays put visually when possible.
        old = self.geometry()
        new_w = max(PET_W, CHAT_W)
        new_h = PET_H + CHAT_EXTRA_H
        if old.width() == new_w and old.height() == new_h:
            return
        dy = new_h - old.height()
        self.setFixedSize(QSize(new_w, new_h))
        if dy != 0 or new_w != old.width():
            self.move(old.x() - (new_w - old.width()) // 2, old.y() - max(dy, 0))

    def _position_bubble(self) -> None:
        """Place overlay above the sprite; bubble is NOT in the layout."""
        if not self.bubble._visible_intent and not self.bubble.isVisible():
            return
        bh = self.bubble.preferred_height()
        self.bubble.setFixedHeight(bh)
        bw = BUBBLE_W
        bx = (self.width() - bw) // 2
        # Derive sprite top from window size so we don't race layout.
        sprite_top = self.height() - self.sprite.height() - SPRITE_BOTTOM_PAD
        # Tail overlaps the sprite slightly for a natural speech-bubble sit.
        by = sprite_top - bh + 6
        self.bubble.setGeometry(bx, max(0, by), bw, bh)
        self.bubble.raise_()

    def _show_bubble(self, focus_input: bool = False) -> None:
        self._hide_timer.stop()
        self.wander.pause("chat")
        if not self.bubble.isVisible() or not getattr(self.bubble, "_visible_intent", False):
            self._apply_chat_geometry()
            self.bubble.show_animated(focus_input=focus_input)
            self._position_bubble()
        elif focus_input:
            self.bubble.input.setFocus(Qt.FocusReason.OtherFocusReason)
            self._position_bubble()

    def _force_hide_bubble(self) -> None:
        self._hide_timer.stop()
        self._chat_pinned = False
        self.bubble.hide_animated()
        self.wander.resume("chat")
        self.wander.resume("reminder")
        # Shrink runs on hide_finished so fade and layout stay decoupled.

    def _shrink_keep_cat(self) -> None:
        """Atomically hide overlay leftovers + shrink; sprite screen position stays."""
        if self.bubble._visible_intent or self._streaming:
            return
        old = self.geometry()
        new_w, new_h = PET_W, PET_H
        if old.width() == new_w and old.height() == new_h:
            self.bubble.hide()
            return
        dy = old.height() - new_h
        # Hide first (no layout effect — bubble is not in the layout), then
        # resize+move in the same event turn so Qt paints once.
        self.bubble.hide()
        self.setFixedSize(QSize(new_w, new_h))
        if dy > 0 or old.width() != new_w:
            self.move(old.x() + (old.width() - new_w) // 2, old.y() + max(dy, 0))

    def _maybe_hide_bubble(self) -> None:
        if self._streaming:
            return
        if self._cursor_inside():
            return
        # Focus must not block hide — clear it and dismiss.
        self._force_hide_bubble()

    def _cursor_inside(self) -> bool:
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self.wander.pause("hover")
        self._show_bubble(focus_input=False)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.wander.resume("hover")
        # Reminder bubble: keep its own longer timer; don't cut it short on leave.
        if self._chat_pinned and not self._streaming:
            if not self._hide_timer.isActive():
                self._hide_timer.start(8000)
        else:
            self._hide_timer.start(220)
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.bubble._visible_intent or self.bubble.isVisible():
            self._position_bubble()

    def _send(self, text: str) -> None:
        if not text.strip():
            return
        self._chat_pinned = True
        self.wander.pause("chat")
        self._show_bubble(focus_input=True)
        self.bubble.begin_stream()
        self.sprite.set_emotion("thinking")
        if not self.client.send_user_message(text.strip(), session_id=self._session_id):
            self._streaming = False
            self._chat_pinned = False
            self.bubble.set_reply("后端未连接，正在重连…请稍后再试（或运行 ./scripts/run.sh）")
            self.sprite.set_emotion("sad")
            self._hide_timer.start(3200)

    def _on_status(self, status: str) -> None:
        if status == "disconnected":
            self.sprite.set_emotion("sad")
            if self._streaming or self.bubble._visible_intent:
                self._streaming = False
                self._chat_pinned = False
                self._show_bubble()
                self.bubble.set_reply("连接断开，正在重连…")
                self._hide_timer.start(2800)
        elif status == "connected":
            if self.sprite._state == "sad":
                self.sprite.set_emotion("idle")

    def _on_ws_message(self, data: dict) -> None:
        msg_type = data.get("type")
        payload = data.get("payload") or {}
        if msg_type == "emotion_changed":
            self.sprite.set_emotion(payload.get("state", "idle"))
        elif msg_type == "token":
            text = payload.get("text", "")
            self._show_bubble()
            if not self._streaming:
                self._streaming = True
                self._chat_pinned = True
                self.bubble.begin_stream()
            self.bubble.append_reply(text)
            sid = payload.get("session_id")
            if sid:
                self._session_id = sid
        elif msg_type == "done":
            self._streaming = False
            self._chat_pinned = False
            sid = payload.get("session_id")
            if sid:
                self._session_id = sid
            # Auto-hide after a short read window if cursor already left
            self._hide_timer.start(1600)
            if not self._cursor_inside():
                self.wander.resume("chat")
        elif msg_type == "tool_status":
            name = payload.get("name")
            status = payload.get("status")
            if status == "running":
                self._show_bubble()
                self.bubble.set_reply(f"正在执行 {name}…")
        elif msg_type == "reminder":
            text = str(payload.get("message") or "你有一个提醒")
            title = str(payload.get("title") or "提醒")
            self._chat_pinned = True
            self._streaming = False
            self.wander.pause("reminder")
            self._show_bubble(focus_input=False)
            self.bubble.set_reply(f"{title}：{text}")
            self.sprite.set_emotion("surprised")
            # Keep bubble visible longer so the user can notice
            self._hide_timer.stop()
            self._hide_timer.start(8000)
            QTimer.singleShot(1200, lambda: self.sprite.set_emotion("happy"))
        elif msg_type == "pet_settings":
            if "always_on_top" in payload:
                self.set_always_on_top(bool(payload.get("always_on_top")))
            if "renderer" in payload or "live2d_model_path" in payload:
                merged = {
                    "renderer": payload.get("renderer", self._renderer),
                    "live2d_model_path": payload.get(
                        "live2d_model_path", self._live2d_model_path
                    ),
                }
                self._apply_renderer_settings(merged)
        elif msg_type == "error":
            self._streaming = False
            self._chat_pinned = False
            self._show_bubble()
            message = str(payload.get("message") or "未知错误")
            self.bubble.set_reply(f"出错了：{message}")
            self.sprite.set_emotion("sad")
            # Keep longer messages (e.g. timeout + endpoint tip) readable
            hold_ms = 6500 if ("超时" in message or "timeout" in message.lower()) else 4000
            self._hide_timer.start(hold_ms)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._open_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        child = self.childAt(event.position().toPoint())
        # Clicking the bubble (input / reply / chrome) focuses input; send handles itself.
        if child is not None and (child is self.bubble or self.bubble.isAncestorOf(child)):
            widget = child
            while widget is not None and widget is not self.bubble:
                if widget.objectName() == "sendBtn":
                    return
                widget = widget.parentWidget()
            self._show_bubble(focus_input=True)
            return
        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self.wander.pause("drag")
        event.accept()

    def _open_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        wander_action = QAction(
            "暂停走动" if self.wander.enabled else "恢复走动",
            self,
        )
        wander_action.triggered.connect(self._toggle_wander)
        top_action = QAction(
            "取消始终置顶" if self._always_on_top else "始终置顶",
            self,
        )
        top_action.triggered.connect(self._toggle_always_on_top)
        settings_action = QAction("打开设置…", self)
        settings_action.triggered.connect(self._open_settings)
        quit_action = QAction("退出 DexPet", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(wander_action)
        menu.addAction(top_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        menu.exec(global_pos)

    def _toggle_wander(self) -> None:
        self.wander.set_enabled(not self.wander.enabled)

    def _toggle_always_on_top(self) -> None:
        self._put_always_on_top(not self._always_on_top)

    def _open_settings(self) -> None:
        url = QUrl(f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/settings")
        QDesktopServices.openUrl(url)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None
        self.wander.resume("drag")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.client.stop()
        try:
            from desktop.live2d_widget import dispose_live2d

            dispose_live2d()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)


def run_window() -> None:
    import sys
    import traceback

    sys.excepthook = lambda *args: (
        traceback.print_exception(*args),
        sys.__excepthook__(*args),
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationName("DexPet")
    win = PetWindow()
    app._dexpet_window = win  # type: ignore[attr-defined]
    screen = app.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        win.move(geo.right() - win.width() - 40, geo.bottom() - win.height() - 80)
    win.show()
    win._shown_once = True  # type: ignore[attr-defined]
    win.raise_()
    print(f"DexPet window visible={win.isVisible()} pos={win.pos().x()},{win.pos().y()}", flush=True)
    sys.exit(app.exec())
