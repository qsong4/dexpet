"""Optional Live2D pet renderer (QOpenGLWidget + live2d-py)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QWidget

from shared.live2d_config import pick_expression_id, pick_motion_group, resolve_model_json

logger = logging.getLogger("dexpet.live2d")

_LIVE2D_INTED = False


def ensure_live2d_init() -> Any:
    """Initialize live2d.v3 once per process. Raises on failure."""
    global _LIVE2D_INTED
    import live2d.v3 as live2d

    if not _LIVE2D_INTED:
        live2d.init()
        _LIVE2D_INTED = True
    return live2d


def dispose_live2d() -> None:
    global _LIVE2D_INTED
    if not _LIVE2D_INTED:
        return
    try:
        import live2d.v3 as live2d

        live2d.dispose()
    except Exception:  # noqa: BLE001
        logger.exception("live2d.dispose failed")
    _LIVE2D_INTED = False


class Live2DPetWidget(QOpenGLWidget):
    """Drop-in replacement for SpriteAnimator: set_emotion / set_facing."""

    def __init__(
        self,
        model_path: str | Path,
        parent: QWidget | None = None,
    ) -> None:
        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setSamples(4)
        QSurfaceFormat.setDefaultFormat(fmt)
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        self.setMouseTracking(True)

        resolved = resolve_model_json(model_path)
        if resolved is None:
            raise FileNotFoundError(f"Live2D model not found: {model_path}")
        self._model_json = resolved
        self._state = "idle"
        self._facing = 1
        self._model: Any = None
        self._live2d: Any = None
        self._ready = False
        self._load_error: str | None = None
        self._expr_ids: list[str] = []
        self._motion_groups: dict[str, Any] = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(16)

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def set_emotion(self, state: str) -> None:
        self._state = state or "idle"
        if not self._ready or self._model is None:
            return
        self._apply_emotion(self._state)

    def set_facing(self, facing: int) -> None:
        self._facing = 1 if facing >= 0 else -1
        if not self._ready or self._model is None:
            return
        try:
            self._model.SetScaleX(float(self._facing))
        except Exception:  # noqa: BLE001
            logger.debug("SetScaleX failed", exc_info=True)

    def initializeGL(self) -> None:  # noqa: N802
        try:
            live2d = ensure_live2d_init()
            live2d.glInit()
            self._live2d = live2d
            model = live2d.LAppModel()
            model.LoadModelJson(str(self._model_json))
            model.Resize(self.width(), self.height())
            try:
                model.SetAutoBlinkEnable(True)
                model.SetAutoBreathEnable(True)
            except Exception:  # noqa: BLE001
                pass
            self._model = model
            try:
                self._expr_ids = list(model.GetExpressionIds() or [])
            except Exception:  # noqa: BLE001
                self._expr_ids = []
            try:
                groups = model.GetMotionGroups()
                self._motion_groups = dict(groups) if groups else {}
            except Exception:  # noqa: BLE001
                self._motion_groups = {}
            self._ready = True
            self._apply_emotion(self._state)
            self.set_facing(self._facing)
            logger.info("Live2D model loaded: %s", self._model_json)
        except Exception as exc:  # noqa: BLE001
            self._load_error = str(exc)
            self._ready = False
            logger.exception("Live2D initializeGL failed")

    def resizeGL(self, w: int, h: int) -> None:  # noqa: N802
        if self._model is not None:
            try:
                self._model.Resize(w, h)
            except Exception:  # noqa: BLE001
                pass

    def paintGL(self) -> None:  # noqa: N802
        if self._live2d is None or self._model is None or not self._ready:
            return
        try:
            self._live2d.clearBuffer()
            self._model.Update()
            self._model.Draw()
        except Exception:  # noqa: BLE001
            logger.debug("paintGL error", exc_info=True)

    def _apply_emotion(self, emotion: str) -> None:
        assert self._model is not None
        live2d = self._live2d
        expr = pick_expression_id(emotion, self._expr_ids)
        try:
            if emotion == "idle":
                self._model.ResetExpression()
            elif expr:
                self._model.SetExpression(expr)
        except Exception:  # noqa: BLE001
            logger.debug("expression apply failed", exc_info=True)

        group = pick_motion_group(emotion, self._motion_groups)
        if group and live2d is not None:
            try:
                priority = getattr(live2d, "MotionPriority", None)
                force = getattr(priority, "FORCE", 3) if priority else 3
                self._model.StartRandomMotion(group, force)
            except Exception:  # noqa: BLE001
                try:
                    self._model.StartRandomMotion(group)
                except Exception:  # noqa: BLE001
                    logger.debug("motion apply failed", exc_info=True)

        self._nudge_params(emotion)

    def _nudge_params(self, emotion: str) -> None:
        """Soft fallback when model has no matching expression/motion."""
        if self._model is None or self._live2d is None:
            return
        sp = getattr(self._live2d, "StandardParams", None)
        if sp is None:
            return

        def _set(name: str, value: float) -> None:
            try:
                param = getattr(sp, name, None)
                if param is None:
                    return
                key = getattr(param, "value", None) or str(param)
                # Prefer enum member itself if SetParameterValue accepts it.
                try:
                    self._model.SetParameterValue(param, value)
                except Exception:  # noqa: BLE001
                    self._model.SetParameterValue(key, value)
            except Exception:  # noqa: BLE001
                pass

        if emotion == "happy":
            _set("ParamMouthForm", 1.0)
            _set("ParamEyeLSmile", 1.0)
            _set("ParamEyeRSmile", 1.0)
        elif emotion == "sad":
            _set("ParamMouthForm", -1.0)
            _set("ParamBrowLY", -1.0)
            _set("ParamBrowRY", -1.0)
        elif emotion == "surprised":
            _set("ParamEyeLOpen", 1.2)
            _set("ParamEyeROpen", 1.2)
            _set("ParamMouthOpenY", 0.6)
        elif emotion == "thinking":
            _set("ParamEyeBallX", 0.4)
            _set("ParamBrowLAngle", 0.5)
        elif emotion == "curious":
            _set("ParamEyeBallX", -0.3)
            _set("ParamAngleZ", 8.0)
        elif emotion == "idle":
            try:
                self._model.ResetParameters()
            except Exception:  # noqa: BLE001
                pass
