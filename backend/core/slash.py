"""Built-in slash commands (no LLM)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from backend.db.repository import Repository


def is_slash_command(text: str) -> bool:
    return text.startswith("/")


def parse_slash(text: str) -> tuple[str, str]:
    """Return (command, args) with command lowercased without leading slash."""
    body = text[1:].strip()
    if not body:
        return "", ""
    parts = body.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return cmd, args


def _reply_events(text: str, session_id: str | None) -> list[dict[str, Any]]:
    return [
        {"type": "token", "payload": {"text": text, "session_id": session_id}},
        {"type": "done", "payload": {"session_id": session_id, "text": text}},
    ]


def _format_reminders(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无待办提醒。"
    lines = ["待办提醒："]
    for row in rows:
        rid = row.get("id")
        fire_at = row.get("fire_at", "?")
        message = row.get("message", "")
        lines.append(f"#{rid}  {fire_at}\n  {message}")
    return "\n".join(lines)


HELP_TEXT = (
    "内置命令：\n"
    "/list   — 列出当前待办提醒\n"
    "/stocks — 列出股票监控\n"
    "/memory — 长期记忆状态与路径\n"
    "/clear  — 清空当前会话历史\n"
    "/help   — 显示本帮助"
)


def _format_stock_watches(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "暂无股票监控。"
    lines = ["股票监控："]
    for row in rows:
        metric = "价格" if row.get("metric") == "price" else "涨跌幅"
        op = "≥" if row.get("op") == "gte" else "≤"
        unit = "%" if row.get("metric") == "change_pct" else ""
        lines.append(
            f"#{row.get('id')}  {row.get('name')}({row.get('symbol')})  "
            f"{metric}{op}{row.get('threshold')}{unit}"
        )
    return "\n".join(lines)


async def handle_slash_command(
    text: str,
    *,
    repo: Repository,
    session_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    cmd, _args = parse_slash(text)
    sid = repo.ensure_session(session_id)

    if cmd in ("help", ""):
        reply = HELP_TEXT
    elif cmd == "list":
        rows = repo.list_reminders(status="pending")
        reply = _format_reminders(rows)
    elif cmd in ("stocks", "stock"):
        rows = repo.list_stock_watches(status="active")
        reply = _format_stock_watches(rows)
    elif cmd == "memory":
        from backend.core.memory_config import load_memory_config
        from backend.core.memory_files import memory_dir, read_meta, read_profile

        cfg = load_memory_config(repo)
        meta = read_meta()
        profile = read_profile().strip()
        reply = (
            f"长期记忆目录：\n{memory_dir()}\n\n"
            f"夜间整理：{'开' if cfg.get('enabled') else '关'} "
            f"@ {int(cfg.get('digest_hour', 0)):02d}:{int(cfg.get('digest_minute', 0)):02d}\n"
            f"主动抽检：{'开' if cfg.get('proactive_enabled') else '关'} "
            f"窗口 {cfg.get('proactive_window_start')}-{cfg.get('proactive_window_end')} "
            f"次数 {cfg.get('proactive_checks_min')}-{cfg.get('proactive_checks_max')}/日 "
            f"成功提问上限 {('不限' if int(cfg.get('proactive_max_asks_per_day') or 0) <= 0 else cfg.get('proactive_max_asks_per_day'))} "
            f"提问冷却 {('不限' if int(cfg.get('proactive_ask_cooldown_minutes') or 0) <= 0 else str(cfg.get('proactive_ask_cooldown_minutes')) + 'min')}\n"
            f"上次整理成功日：{meta.get('last_success_date') or '无'}\n"
            f"画像：{'有（' + str(len(profile)) + ' 字）' if profile else '空'}\n"
            "清空请用设置页「长期记忆」。"
        )
    elif cmd == "clear":
        deleted = repo.clear_session_messages(sid)
        reply = f"已清空当前会话历史（{deleted} 条消息）。"
    else:
        reply = f"未知命令：/{cmd}\n输入 /help 查看可用命令。"

    for event in _reply_events(reply, sid):
        yield event
