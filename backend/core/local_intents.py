"""Local intents that bypass the LLM when the user request is unambiguous."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from backend.core.app_whitelist import get_app_whitelist
from backend.core.macos_system import (
    _CLOSE_PREFIXES,
    _OPEN_PREFIXES,
    close_app,
    open_app,
    resolve_app_name,
)
from backend.db.repository import Repository

logger = logging.getLogger("dexpet.local_intents")

# Keep local intercepts short so chatty sentences still go to the LLM.
_MAX_OPEN_INTENT_LEN = 48
_MAX_CLOSE_INTENT_LEN = 48


def looks_like_open_app_command(text: str) -> bool:
    raw = (text or "").strip().lower()
    if not raw or len(raw) > _MAX_OPEN_INTENT_LEN:
        return False
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1].strip()
    return any(raw.startswith(prefix) for prefix in _OPEN_PREFIXES)


def match_open_app_intent(text: str, aliases: dict[str, str]) -> str | None:
    """If text is clearly「打开某应用」and resolves, return the macOS app name."""
    if not looks_like_open_app_command(text):
        return None
    return resolve_app_name(text, aliases)


def looks_like_close_app_command(text: str) -> bool:
    raw = (text or "").strip().lower()
    if not raw or len(raw) > _MAX_CLOSE_INTENT_LEN:
        return False
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1].strip()
    return any(raw.startswith(prefix) for prefix in _CLOSE_PREFIXES)


def match_close_app_intent(text: str, aliases: dict[str, str]) -> str | None:
    """If text is clearly「关闭/退出某应用」and resolves, return the macOS app name."""
    if not looks_like_close_app_command(text):
        return None
    return resolve_app_name(text, aliases)


def _reply_events(text: str, session_id: str | None) -> list[dict[str, Any]]:
    return [
        {"type": "token", "payload": {"text": text, "session_id": session_id}},
        {"type": "done", "payload": {"session_id": session_id, "text": text}},
    ]


async def handle_open_app_intent(
    text: str,
    *,
    repo: Repository,
    session_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """Execute local open_app and yield chat events. Caller must pre-match."""
    sid = repo.ensure_session(session_id)
    aliases = get_app_whitelist(repo)
    app = match_open_app_intent(text, aliases)
    logger.info("local open_app intent text=%r resolved=%r", text, app)
    if not app:
        reply = "没找到可打开的应用，请确认白名单里有它。"
        repo.add_message(sid, "user", text)
        repo.add_message(sid, "assistant", reply)
        for event in _reply_events(reply, sid):
            yield event
        return

    result = open_app(text, aliases=aliases)
    if result.get("ok"):
        reply = f"已打开 {result.get('app') or app}。"
    else:
        reply = result.get("error") or f"打开 {app} 失败。"
    repo.add_message(sid, "user", text)
    repo.add_message(sid, "assistant", reply)
    yield {
        "type": "tool_status",
        "payload": {
            "name": "open_app",
            "status": "done" if result.get("ok") else "error",
            "detail": str(result),
        },
    }
    for event in _reply_events(reply, sid):
        yield event


async def handle_close_app_intent(
    text: str,
    *,
    repo: Repository,
    session_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """Execute local close_app and yield chat events. Caller must pre-match."""
    sid = repo.ensure_session(session_id)
    aliases = get_app_whitelist(repo)
    app = match_close_app_intent(text, aliases)
    logger.info("local close_app intent text=%r resolved=%r", text, app)
    if not app:
        reply = "没找到可关闭的应用，请确认白名单里有它。"
        repo.add_message(sid, "user", text)
        repo.add_message(sid, "assistant", reply)
        for event in _reply_events(reply, sid):
            yield event
        return

    result = close_app(text, aliases=aliases)
    if result.get("ok"):
        reply = f"已关闭 {result.get('app') or app}。"
    else:
        reply = result.get("error") or f"关闭 {app} 失败。"
    repo.add_message(sid, "user", text)
    repo.add_message(sid, "assistant", reply)
    yield {
        "type": "tool_status",
        "payload": {
            "name": "close_app",
            "status": "done" if result.get("ok") else "error",
            "detail": str(result),
        },
    }
    for event in _reply_events(reply, sid):
        yield event
