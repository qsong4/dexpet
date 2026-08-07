"""APScheduler jobs for nightly digest + daily random proactive checks + optional morning."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from backend.core.memory_config import load_memory_config
from backend.core.memory_digest import MemoryDigestService
from backend.core.memory_files import (
    consume_digest_failure_notification,
    read_meta,
    record_digest_failure,
    update_meta,
)
from backend.core.memory_proactive import (
    MemoryProactiveService,
    resolve_checks_per_day,
    sample_check_times,
)
from backend.db.repository import Repository

logger = logging.getLogger("dexpet.memory_scheduler")

DIGEST_JOB_ID = "memory-nightly-digest"
DAILY_RESAMPLE_JOB_ID = "memory-proactive-daily-resample"
CHECK_JOB_PREFIX = "memory-proactive-check-"
MORNING_JOB_ID = "memory-proactive-morning"
CATCHUP_JOB_ID = "memory-proactive-catchup"
CATCHUP_DELAY_SECONDS = 45

DIGEST_FAILURE_TITLE = "记忆整理失败"
DIGEST_FAILURE_MESSAGE = (
    "昨晚记忆整理失败。可在设置页「长期记忆」点「立即整理今日」，"
    "或调用 POST /memory/digest 重试。"
)

# (title, message)
FailureNotifier = Callable[[str, str], None]


class MemoryScheduler:
    def __init__(
        self,
        repo: Repository,
        scheduler: BackgroundScheduler,
        digest: MemoryDigestService,
        proactive: MemoryProactiveService,
        loop_provider: Any | None = None,
        on_digest_failure: FailureNotifier | None = None,
    ) -> None:
        self.repo = repo
        self.scheduler = scheduler
        self.digest = digest
        self.proactive = proactive
        # Callable returning asyncio loop, or object with .loop
        self.loop_provider = loop_provider
        self.on_digest_failure = on_digest_failure

    def set_digest_failure_notifier(self, cb: FailureNotifier | None) -> None:
        self.on_digest_failure = cb

    def _get_loop(self) -> asyncio.AbstractEventLoop | None:
        lp = self.loop_provider
        if lp is None:
            return None
        if callable(lp):
            return lp()
        return getattr(lp, "loop", None)

    def _run_coro(self, coro: Any, timeout: float = 300.0) -> Any:
        loop = self._get_loop()
        if loop is None or not loop.is_running():
            # Fallback for tests without running loop
            return asyncio.run(coro)
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    def ensure_jobs(self, *, now: datetime | None = None) -> dict[str, Any]:
        cfg = load_memory_config(self.repo)
        current = now or datetime.now().astimezone()
        summary: dict[str, Any] = {
            "digest": False,
            "proactive_checks": 0,
            "morning": False,
            "catchup": False,
        }

        # Digest cron
        try:
            self.scheduler.remove_job(DIGEST_JOB_ID)
        except Exception:  # noqa: BLE001
            pass
        if cfg.get("enabled", True):
            hour = int(cfg.get("digest_hour", 0))
            minute = int(cfg.get("digest_minute", 0))
            self.scheduler.add_job(
                self._job_digest,
                trigger=CronTrigger(hour=hour, minute=minute),
                id=DIGEST_JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            summary["digest"] = True

        # Clear old check jobs
        self._clear_check_jobs()
        try:
            self.scheduler.remove_job(DAILY_RESAMPLE_JOB_ID)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.scheduler.remove_job(CATCHUP_JOB_ID)
        except Exception:  # noqa: BLE001
            pass

        if cfg.get("proactive_enabled", True):
            # Midnight-ish resample + immediate schedule for today
            self.scheduler.add_job(
                self._job_resample_checks,
                trigger=CronTrigger(hour=0, minute=5),
                id=DAILY_RESAMPLE_JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            n = self.schedule_proactive_for_day(current.date(), now=current)
            summary["proactive_checks"] = n
            # One soft catch-up after restart (not a pile of missed jobs)
            summary["catchup"] = self.schedule_startup_catchup(now=current)

        # Optional morning greeting / check (independent of random checks)
        try:
            self.scheduler.remove_job(MORNING_JOB_ID)
        except Exception:  # noqa: BLE001
            pass
        if cfg.get("proactive_morning_enabled", False):
            mh = int(cfg.get("proactive_morning_hour", 9))
            mm = int(cfg.get("proactive_morning_minute", 30))
            self.scheduler.add_job(
                self._job_morning,
                trigger=CronTrigger(hour=mh, minute=mm),
                id=MORNING_JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            summary["morning"] = True

        # At most one bubble per day for pending digest failure (startup / config refresh)
        self.notify_pending_digest_failure()
        return summary

    def schedule_startup_catchup(self, *, now: datetime | None = None) -> bool:
        """
        Schedule a single check shortly after startup when still inside today's window.

        Does not replay missed slots (product: no pile-up); just recovers one opportunity
        after the process was down or restarted mid-day.
        """
        cfg = load_memory_config(self.repo)
        if not cfg.get("proactive_enabled", True):
            return False
        current = now or datetime.now().astimezone()
        sh, sm = (str(cfg.get("proactive_window_start", "09:00")) or "09:00").split(":")
        eh, em = (str(cfg.get("proactive_window_end", "21:30")) or "21:30").split(":")
        start = current.replace(hour=int(sh), minute=int(sm), second=0, microsecond=0)
        end = current.replace(hour=int(eh), minute=int(em), second=0, microsecond=0)
        if not (start <= current <= end):
            return False
        when = current + timedelta(seconds=CATCHUP_DELAY_SECONDS)
        if when > end:
            return False
        try:
            self.scheduler.remove_job(CATCHUP_JOB_ID)
        except Exception:  # noqa: BLE001
            pass
        self.scheduler.add_job(
            self._job_check_once,
            trigger=DateTrigger(run_date=when),
            id=CATCHUP_JOB_ID,
            replace_existing=True,
            misfire_grace_time=120,
            coalesce=True,
            max_instances=1,
        )
        logger.info("scheduled proactive catch-up at %s", when.isoformat())
        return True

    def notify_pending_digest_failure(self) -> bool:
        """Push bubble once if unread digest failure exists and not yet notified today."""
        failure = consume_digest_failure_notification()
        if not failure:
            return False
        if self.on_digest_failure:
            try:
                self.on_digest_failure(DIGEST_FAILURE_TITLE, DIGEST_FAILURE_MESSAGE)
            except Exception:  # noqa: BLE001
                logger.exception("digest failure notifier failed")
        return True

    def _clear_check_jobs(self) -> None:
        for job in list(self.scheduler.get_jobs()):
            jid = getattr(job, "id", "") or ""
            if jid.startswith(CHECK_JOB_PREFIX):
                try:
                    self.scheduler.remove_job(jid)
                except Exception:  # noqa: BLE001
                    pass

    def schedule_proactive_for_day(self, day: date, *, now: datetime | None = None) -> int:
        cfg = load_memory_config(self.repo)
        if not cfg.get("proactive_enabled", True):
            self._clear_check_jobs()
            return 0
        current = now or datetime.now().astimezone()
        # Only keep today's jobs when scheduling today
        if day == current.date():
            self._clear_check_jobs()

        k = resolve_checks_per_day(cfg)
        times = sample_check_times(
            day=day,
            window_start=str(cfg.get("proactive_window_start", "09:00")),
            window_end=str(cfg.get("proactive_window_end", "21:30")),
            count=k,
            min_gap_minutes=int(cfg.get("proactive_min_gap_minutes", 25)),
            now=current if day == current.date() else None,
        )
        day_key = day.isoformat()
        meta = read_meta()
        schedule = meta.get("proactive_schedule") or {}
        if not isinstance(schedule, dict):
            schedule = {}
        schedule[day_key] = [t.isoformat() for t in times]
        update_meta(proactive_schedule=schedule)

        for i, when in enumerate(times):
            job_id = f"{CHECK_JOB_PREFIX}{day_key}-{i}"
            # Do not pile up missed jobs: short misfire grace
            self.scheduler.add_job(
                self._job_check_once,
                trigger=DateTrigger(run_date=when),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=120,
                coalesce=True,
                max_instances=1,
            )
        return len(times)

    def _handle_digest_failure(self, exc: BaseException) -> None:
        record_digest_failure(error=str(exc))
        # Immediate notify (consume so ensure_jobs / restart won't re-push same day)
        self.notify_pending_digest_failure()
        # Schedule +1h retry (best-effort)
        try:
            self.scheduler.add_job(
                self._job_digest_retry,
                trigger=DateTrigger(
                    run_date=datetime.now().astimezone() + timedelta(hours=1)
                ),
                id="memory-digest-retry",
                replace_existing=True,
                max_instances=1,
            )
        except Exception:  # noqa: BLE001
            pass

    def _job_digest(self) -> None:
        try:
            self._run_coro(self.digest.run(force=False), timeout=300)
        except Exception as exc:  # noqa: BLE001
            logger.exception("memory digest job failed")
            self._handle_digest_failure(exc)

    def _job_digest_retry(self) -> None:
        try:
            self._run_coro(self.digest.run(force=False), timeout=300)
        except Exception as exc:  # noqa: BLE001
            logger.exception("memory digest retry failed")
            self._handle_digest_failure(exc)

    def _job_check_once(self) -> None:
        try:
            self._run_coro(self.proactive.check_once(), timeout=120)
        except Exception:  # noqa: BLE001
            logger.exception("memory proactive check failed")

    def _job_morning(self) -> None:
        try:
            self._run_coro(self.proactive.morning_check(), timeout=120)
        except Exception:  # noqa: BLE001
            logger.exception("memory morning check failed")

    def _job_resample_checks(self) -> None:
        try:
            self.schedule_proactive_for_day(date.today())
        except Exception:  # noqa: BLE001
            logger.exception("memory proactive resample failed")

    def trigger_digest_sync(self, for_date: date | None = None, *, force: bool = True) -> dict[str, Any]:
        return self._run_coro(self.digest.run(for_date=for_date, force=force), timeout=300)

    def trigger_check_sync(self) -> dict[str, Any]:
        return self._run_coro(self.proactive.check_once(), timeout=120)
