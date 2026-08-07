"""Reminder plugin with APScheduler + pet-bubble push."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from backend.core.tools import Plugin, ToolSpec
from backend.db.repository import Repository

ReminderNotifier = Callable[[int, str], None]


def resolve_fire_time(
    *,
    fire_at: str | None = None,
    delay_seconds: int | None = None,
    now: datetime | None = None,
) -> datetime:
    """Resolve a future fire time. Past absolute times are bumped to now+5s."""
    current = now or datetime.now().astimezone()
    if delay_seconds is not None:
        return current + timedelta(seconds=max(1, int(delay_seconds)))
    if not fire_at:
        raise ValueError("需要提供 delay_seconds 或 fire_at")
    when = datetime.fromisoformat(fire_at)
    if when.tzinfo is None:
        when = when.replace(tzinfo=current.tzinfo)
    else:
        when = when.astimezone(current.tzinfo)
    if when <= current:
        return current + timedelta(seconds=5)
    return when


class ReminderPlugin(Plugin):
    name = "reminder"

    def __init__(
        self,
        repo: Repository,
        scheduler: BackgroundScheduler | None = None,
        on_fire: ReminderNotifier | None = None,
    ) -> None:
        self.repo = repo
        self.scheduler = scheduler or BackgroundScheduler()
        self.on_fire = on_fire
        if not self.scheduler.running:
            self.scheduler.start()
        self._restore_pending()

    def set_notifier(self, on_fire: ReminderNotifier | None) -> None:
        self.on_fire = on_fire

    def _restore_pending(self) -> None:
        # Overdue pending reminders still notify shortly after restart.
        now = datetime.now().astimezone()
        overdue_offset = 2
        for row in self.repo.list_reminders(status="pending"):
            try:
                original = datetime.fromisoformat(row["fire_at"])
            except ValueError:
                continue
            if original.tzinfo is None:
                original = original.replace(tzinfo=now.tzinfo)
            original = original.astimezone(now.tzinfo)
            if original <= now:
                when = now + timedelta(seconds=overdue_offset)
                overdue_offset += 2
            else:
                when = original
            self._schedule(row["id"], row["message"], when)

    def _schedule(self, reminder_id: int, message: str, when: datetime) -> None:
        job_id = f"reminder-{reminder_id}"
        try:
            self.scheduler.add_job(
                self._fire,
                trigger=DateTrigger(run_date=when),
                id=job_id,
                replace_existing=True,
                args=[reminder_id, message],
                misfire_grace_time=3600 * 24 * 7,  # allow late fire within a week
            )
        except Exception:  # noqa: BLE001
            pass

    def _fire(self, reminder_id: int, message: str) -> None:
        if self.on_fire is not None:
            try:
                self.on_fire(reminder_id, message)
            except Exception:  # noqa: BLE001
                pass
        self.repo.mark_reminder_done(reminder_id)

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="create_reminder",
                description=(
                    "创建一次提醒。相对时间优先用 delay_seconds（秒）；"
                    "绝对时间才用 fire_at（ISO8601，必须是未来时间，年份不要写错）。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "提醒内容"},
                        "delay_seconds": {
                            "type": "integer",
                            "description": "多少秒后提醒。例如 1 分钟后=60，优先使用此字段。",
                        },
                        "fire_at": {
                            "type": "string",
                            "description": "绝对触发时间 ISO8601，如 2026-08-05T19:05:00+08:00",
                        },
                    },
                    "required": ["message"],
                },
                handler=self.create_reminder,
            ),
            ToolSpec(
                name="list_reminders",
                description="列出提醒。可按 status 过滤：pending/done。",
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "done"],
                            "description": "可选状态过滤",
                        }
                    },
                },
                handler=self.list_reminders,
            ),
            ToolSpec(
                name="delete_reminder",
                description="按 id 删除提醒。",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "提醒 ID"},
                    },
                    "required": ["id"],
                },
                handler=self.delete_reminder,
            ),
        ]

    def create_reminder(
        self,
        message: str,
        fire_at: str | None = None,
        delay_seconds: int | None = None,
    ) -> dict[str, Any]:
        when = resolve_fire_time(fire_at=fire_at, delay_seconds=delay_seconds)
        iso = when.isoformat()
        rid = self.repo.create_reminder(message, iso)
        self._schedule(rid, message, when)
        return {
            "id": rid,
            "message": message,
            "fire_at": iso,
            "status": "pending",
            "delay_seconds": delay_seconds,
        }

    def list_reminders(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.repo.list_reminders(status=status)

    def delete_reminder(self, id: int) -> dict[str, Any]:
        ok = self.repo.delete_reminder(id)
        job_id = f"reminder-{id}"
        try:
            self.scheduler.remove_job(job_id)
        except Exception:  # noqa: BLE001
            pass
        return {"deleted": ok, "id": id}
