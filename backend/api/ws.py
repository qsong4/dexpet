"""WebSocket chat endpoint."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.app_whitelist import get_app_whitelist
from backend.core.local_intents import (
    handle_close_app_intent,
    handle_open_app_intent,
    match_close_app_intent,
    match_open_app_intent,
)
from backend.core.slash import handle_slash_command, is_slash_command
from shared.messages import Envelope, MessageType

logger = logging.getLogger("dexpet.ws")

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    app = websocket.app
    hub = getattr(app.state, "ws_hub", None)
    if hub is not None:
        await hub.register(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                envelope = Envelope.model_validate(data)
            except Exception:  # noqa: BLE001
                await websocket.send_json(
                    {
                        "type": MessageType.ERROR.value,
                        "payload": {"message": "无效消息格式", "code": "bad_request"},
                    }
                )
                continue

            if envelope.type == MessageType.PING:
                await websocket.send_json(
                    {
                        "type": MessageType.PONG.value,
                        "payload": {},
                        "request_id": envelope.request_id,
                    }
                )
                continue

            if envelope.type != MessageType.USER_MESSAGE:
                await websocket.send_json(
                    {
                        "type": MessageType.ERROR.value,
                        "payload": {
                            "message": f"不支持的消息类型: {envelope.type}",
                            "code": "unsupported",
                        },
                        "request_id": envelope.request_id,
                    }
                )
                continue

            text = str(envelope.payload.get("text", "")).strip()
            session_id = envelope.payload.get("session_id")
            if not text:
                await websocket.send_json(
                    {
                        "type": MessageType.ERROR.value,
                        "payload": {"message": "消息不能为空", "code": "empty"},
                        "request_id": envelope.request_id,
                    }
                )
                continue

            # Slash commands: no LLM, works without API Key
            if is_slash_command(text):
                async for event in handle_slash_command(
                    text, repo=app.state.repo, session_id=session_id
                ):
                    event["request_id"] = envelope.request_id
                    await websocket.send_json(event)
                continue

            # 「打开网易云音乐」等：本地直接 open_app，不依赖 LLM 传参
            aliases = get_app_whitelist(app.state.repo)
            if match_open_app_intent(text, aliases):
                logger.info("ws local open_app intent text=%r", text)
                async for event in handle_open_app_intent(
                    text, repo=app.state.repo, session_id=session_id
                ):
                    event["request_id"] = envelope.request_id
                    await websocket.send_json(event)
                continue

            # 「关闭网易云音乐」等：本地直接 close_app
            if match_close_app_intent(text, aliases):
                logger.info("ws local close_app intent text=%r", text)
                async for event in handle_close_app_intent(
                    text, repo=app.state.repo, session_id=session_id
                ):
                    event["request_id"] = envelope.request_id
                    await websocket.send_json(event)
                continue

            manager = app.state.conversation
            if manager is None:
                await websocket.send_json(
                    {
                        "type": MessageType.ERROR.value,
                        "payload": {
                            "message": "尚未配置 API Key，请先打开设置页配置",
                            "code": "not_configured",
                        },
                        "request_id": envelope.request_id,
                    }
                )
                continue

            async for event in manager.handle_user_message(text, session_id=session_id):
                event["request_id"] = envelope.request_id
                await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        if hub is not None:
            await hub.unregister(websocket)
