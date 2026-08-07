"""Opportunity-driven proactive memory checks (random sampling + conditional ask)."""

from __future__ import annotations

import json
import logging
import random
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from backend.core.memory_config import load_memory_config
from backend.core.memory_files import (
    list_recent_dailies,
    read_meta,
    read_open_questions,
    read_profile,
    update_meta,
    write_meta,
)
from backend.db.repository import Repository

logger = logging.getLogger("dexpet.memory_proactive")

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}

CHECK_SYSTEM = """你是 DexPet 主动询问判断器。根据画像、缺口与习惯，判断此刻是否值得问用户一句。
偏保守：没有具体、有温度、对用户有价值的问题就安静（should_ask=false）。
禁止编造敏感话题；优先 open_loops/待确认，其次达标习惯触发，再次克制好奇心。
规律触发须在 reason 引用证据；confidence=low 不得单独支撑 should_ask=true。
输出严格 JSON：
{
  "should_ask": bool,
  "question": string|null,
  "ask_kind": "gap"|"pattern"|null,
  "pattern_id": string|null,
  "reason": string,
  "priority": "low"|"medium"|"high",
  "confidence": "low"|"medium"|"high"
}
"""

ProactiveNotifier = Callable[[str, str], None]  # (title, message)


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = (value or "09:00").strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return hour, minute


def sample_check_times(
    *,
    day: date,
    window_start: str = "09:00",
    window_end: str = "21:30",
    count: int = 15,
    min_gap_minutes: int = 25,
    rng: random.Random | None = None,
    now: datetime | None = None,
    tz: datetime.tzinfo | None = None,
) -> list[datetime]:
    """Sample `count` local datetimes within window with min gap; drop past times if now given."""
    rng = rng or random.Random()
    local_tz = tz or datetime.now().astimezone().tzinfo
    sh, sm = _parse_hhmm(window_start)
    eh, em = _parse_hhmm(window_end)
    start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=local_tz)
    end = datetime(day.year, day.month, day.day, eh, em, tzinfo=local_tz)
    # Late start / restart: sample inside remaining window so we keep ~count slots
    if now is not None:
        current = now.astimezone(local_tz) if now.tzinfo else now.replace(tzinfo=local_tz)
        if current.date() == day:
            if current >= end:
                return []
            if current > start:
                start = current + timedelta(seconds=30)
    if end <= start:
        return []
    total_minutes = int((end - start).total_seconds() // 60)
    if total_minutes < 1 or count < 1:
        return []

    # Cap count so gaps are feasible
    max_feasible = max(1, total_minutes // max(1, min_gap_minutes) + 1)
    k = min(count, max_feasible)

    chosen: list[int] = []
    for _ in range(80):
        candidates = sorted(rng.sample(range(total_minutes + 1), k=min(k, total_minutes + 1)))
        ok = True
        for a, b in zip(candidates, candidates[1:]):
            if b - a < min_gap_minutes:
                ok = False
                break
        if ok:
            chosen = candidates
            break
    if not chosen:
        # Greedy even-ish spacing
        if k == 1:
            chosen = [rng.randint(0, total_minutes)]
        else:
            step = total_minutes / (k - 1)
            chosen = [min(total_minutes, int(round(i * step))) for i in range(k)]

    return [start + timedelta(minutes=m) for m in chosen]


def resolve_checks_per_day(cfg: dict[str, Any], *, rng: random.Random | None = None) -> int:
    rng = rng or random.Random()
    cmin = int(cfg.get("proactive_checks_min", 10))
    cmax = int(cfg.get("proactive_checks_max", 20))
    if cmin > cmax:
        cmin, cmax = cmax, cmin
    if cmin == cmax:
        return max(1, cmin)
    # Prefer configured per_day when it falls inside [min,max] and min/max span is default-like:
    # still randomize within range as product decision.
    return rng.randint(cmin, cmax)


def _extract_json(text: str) -> dict[str, Any]:
    from backend.core.llm_json import extract_llm_json

    return extract_llm_json(text)


def _habits_from_meta_or_profile(meta: dict[str, Any]) -> list[dict[str, Any]]:
    habits = meta.get("habits") or []
    if isinstance(habits, list) and habits:
        return [h for h in habits if isinstance(h, dict)]
    return []


def _open_gaps_nonempty(meta: dict[str, Any], profile: str, open_q: str) -> bool:
    oq = meta.get("open_questions") or []
    if isinstance(oq, list) and any(
        (isinstance(x, dict) and str(x.get("text", "")).strip())
        or (isinstance(x, str) and x.strip())
        for x in oq
    ):
        return True
    text = (open_q or "").strip()
    if text and "（空）" not in text and re.search(r"^[-*]\s+\[[^\]]+\]\s+\S|^[-*]\s+\S", text, re.M):
        # Exclude pure headers
        bullets = [
            ln for ln in text.splitlines()
            if re.match(r"^[-*]\s+\S", ln) and "（空）" not in ln
        ]
        if bullets:
            return True
    # Look only inside profile's 记忆缺口 section
    if "记忆缺口" in (profile or ""):
        section = profile.split("记忆缺口", 1)[-1]
        for stop in ("## ", "# "):
            # keep section until next major heading at start of line after first line
            pass
        bullets = [
            ln
            for ln in section.splitlines()
            if re.match(r"^[-*]\s+\S", ln)
            and "（空）" not in ln
            and not re.match(r"^[-*]\s+…", ln)
        ]
        if bullets:
            return True
    return False


def _usable_habits(
    habits: list[dict[str, Any]],
    *,
    min_confidence: str,
    cooldown_hours: int,
    meta: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    min_rank = CONFIDENCE_RANK.get(min_confidence, 1)
    cool = meta.get("pattern_ask_cooldown") or {}
    if not isinstance(cool, dict):
        cool = {}
    usable = []
    for h in habits:
        conf = str(h.get("confidence", "low")).lower()
        if CONFIDENCE_RANK.get(conf, 0) < min_rank:
            continue
        pid = str(h.get("id") or h.get("text") or "")[:80]
        last = cool.get(pid)
        if last:
            try:
                last_dt = datetime.fromisoformat(str(last))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=now.tzinfo)
                if now - last_dt.astimezone(now.tzinfo) < timedelta(hours=cooldown_hours):
                    continue
            except ValueError:
                pass
        usable.append(h)
    return usable


class MemoryProactiveService:
    def __init__(
        self,
        repo: Repository,
        llm: Any | None = None,
        on_ask: ProactiveNotifier | None = None,
        is_busy: Callable[[], bool] | None = None,
    ) -> None:
        self.repo = repo
        self.llm = llm
        self.on_ask = on_ask
        self.is_busy = is_busy

    def set_llm(self, llm: Any | None) -> None:
        self.llm = llm

    def set_notifier(self, on_ask: ProactiveNotifier | None) -> None:
        self.on_ask = on_ask

    def set_busy_checker(self, is_busy: Callable[[], bool] | None) -> None:
        self.is_busy = is_busy

    def _today_ask_count(self, meta: dict[str, Any], day_key: str) -> int:
        if meta.get("proactive_ask_date") != day_key:
            return 0
        return int(meta.get("proactive_ask_count_today") or 0)

    def _gates(
        self,
        cfg: dict[str, Any],
        *,
        now: datetime,
        source: str = "random",
    ) -> str | None:
        """Return skip reason or None if ok to proceed toward LLM/ask."""
        if source == "morning":
            if not cfg.get("proactive_morning_enabled", False):
                return "morning_disabled"
        elif not cfg.get("proactive_enabled", True):
            return "disabled"
        if self.is_busy and self.is_busy():
            return "busy"
        meta = read_meta()
        day_key = now.date().isoformat()
        # <=0 means unlimited successful asks per day
        max_asks = int(cfg.get("proactive_max_asks_per_day", 0) or 0)
        if max_asks > 0 and self._today_ask_count(meta, day_key) >= max_asks:
            return "max_asks"
        # <=0 means no cooldown between successful asks
        cool_min = int(cfg.get("proactive_ask_cooldown_minutes", 0) or 0)
        if cool_min > 0:
            last_ask = meta.get("last_proactive_ask_at")
            if last_ask:
                try:
                    last_dt = datetime.fromisoformat(str(last_ask))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=now.tzinfo)
                    else:
                        last_dt = last_dt.astimezone(now.tzinfo)
                    if now - last_dt < timedelta(minutes=cool_min):
                        return "ask_cooldown"
                except ValueError:
                    pass
        dismiss_until = meta.get("proactive_dismiss_until")
        if dismiss_until:
            try:
                until = datetime.fromisoformat(str(dismiss_until))
                if until.tzinfo is None:
                    until = until.replace(tzinfo=now.tzinfo)
                if now < until.astimezone(now.tzinfo):
                    return "user_dismiss"
            except ValueError:
                pass
        quiet_min = int(cfg.get("proactive_quiet_after_chat_minutes", 20))
        last_msg = self.repo.latest_message_created_at()
        if last_msg:
            try:
                last_dt = datetime.fromisoformat(last_msg)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=now.tzinfo)
                else:
                    last_dt = last_dt.astimezone(now.tzinfo)
                if now - last_dt < timedelta(minutes=quiet_min):
                    return "quiet_after_chat"
            except ValueError:
                pass
        return None

    async def check_once(
        self,
        *,
        now: datetime | None = None,
        source: str = "random",
    ) -> dict[str, Any]:
        cfg = load_memory_config(self.repo)
        current = now or datetime.now().astimezone()
        day_key = current.date().isoformat()
        skip = self._gates(cfg, now=current, source=source)
        if skip in ("max_asks", "disabled", "morning_disabled", "ask_cooldown"):
            logger.info("proactive check skip source=%s reason=%s", source, skip)
            return {"ok": True, "asked": False, "skipped": True, "reason": skip, "llm": False}
        if skip:
            logger.info("proactive check skip source=%s reason=%s", source, skip)
            return {"ok": True, "asked": False, "skipped": True, "reason": skip, "llm": False}

        meta = read_meta()
        profile = read_profile()
        open_q = read_open_questions()
        habits = _habits_from_meta_or_profile(meta)
        min_conf = str(cfg.get("proactive_pattern_min_confidence", "medium"))
        cool_h = int(cfg.get("proactive_pattern_cooldown_hours", 48))
        usable = _usable_habits(
            habits,
            min_confidence=min_conf,
            cooldown_hours=cool_h,
            meta=meta,
            now=current,
        )
        has_gaps = _open_gaps_nonempty(meta, profile, open_q)
        if not has_gaps and not usable:
            logger.info("proactive check skip source=%s reason=no_gaps_or_habits", source)
            return {
                "ok": True,
                "asked": False,
                "skipped": True,
                "reason": "no_gaps_or_habits",
                "llm": False,
            }

        if self.llm is None:
            logger.info("proactive check skip source=%s reason=no_llm", source)
            return {"ok": False, "asked": False, "reason": "no_llm", "llm": False}

        dailies = list_recent_dailies(3)
        daily_text = "\n\n".join(f"[{d}]\n{c[:400]}" for d, c in dailies) or "（无）"
        habit_text = json.dumps(usable or habits, ensure_ascii=False)[:2000]
        source_note = "（晨间轻量检查）" if source == "morning" else ""
        user_prompt = (
            f"当前本地时间：{current.isoformat()}{source_note}\n"
            f"今日已成功提问次数：{self._today_ask_count(meta, day_key)}\n\n"
            f"【画像】\n{profile[:3000] or '（空）'}\n\n"
            f"【open_questions】\n{open_q[:1500] or '（空）'}\n\n"
            f"【可用习惯】\n{habit_text}\n\n"
            f"【近日摘要】\n{daily_text}\n"
        )
        result = await self.llm.chat(
            [
                {"role": "system", "content": CHECK_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.2,
        )
        data = _extract_json(result.content or "")
        should = bool(data.get("should_ask"))
        question = (data.get("question") or "").strip() if data.get("question") else ""
        priority = str(data.get("priority") or "low").lower()
        confidence = str(data.get("confidence") or "low").lower()
        ask_kind = data.get("ask_kind")
        pattern_id = data.get("pattern_id")
        min_pri = str(cfg.get("proactive_min_priority", "medium"))

        if not should or not question:
            logger.info("proactive check quiet source=%s reason=should_ask_false", source)
            return {
                "ok": True,
                "asked": False,
                "skipped": False,
                "reason": "should_ask_false",
                "llm": True,
                "decision": data,
            }
        if PRIORITY_RANK.get(priority, 0) < PRIORITY_RANK.get(min_pri, 1):
            logger.info("proactive check quiet source=%s reason=priority_low", source)
            return {
                "ok": True,
                "asked": False,
                "reason": "priority_low",
                "llm": True,
                "decision": data,
            }
        if ask_kind == "pattern":
            if CONFIDENCE_RANK.get(confidence, 0) < CONFIDENCE_RANK.get(min_conf, 1):
                return {
                    "ok": True,
                    "asked": False,
                    "reason": "pattern_confidence_low",
                    "llm": True,
                    "decision": data,
                }
            pid = str(pattern_id or "")[:80]
            cool = meta.get("pattern_ask_cooldown") or {}
            if isinstance(cool, dict) and pid and pid in cool:
                try:
                    last_dt = datetime.fromisoformat(str(cool[pid]))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=current.tzinfo)
                    if current - last_dt.astimezone(current.tzinfo) < timedelta(hours=cool_h):
                        return {
                            "ok": True,
                            "asked": False,
                            "reason": "pattern_cooldown",
                            "llm": True,
                            "decision": data,
                        }
                except ValueError:
                    pass

        # Re-check max asks / busy right before push
        skip2 = self._gates(cfg, now=datetime.now().astimezone(), source=source)
        if skip2:
            return {"ok": True, "asked": False, "skipped": True, "reason": skip2, "llm": True}

        title = "DexPet 想问你" if source != "morning" else "早上好"
        if self.on_ask:
            self.on_ask(title, question)

        meta = read_meta()
        ask_count = self._today_ask_count(meta, day_key) + 1
        meta["proactive_ask_date"] = day_key
        meta["proactive_ask_count_today"] = ask_count
        meta["last_proactive_ask_at"] = current.isoformat()
        if ask_kind == "pattern":
            pid = str(pattern_id or question[:40])[:80]
            cool = meta.get("pattern_ask_cooldown")
            if not isinstance(cool, dict):
                cool = {}
            cool[pid] = current.isoformat()
            meta["pattern_ask_cooldown"] = cool
        write_meta(meta)
        logger.info(
            "proactive check asked source=%s kind=%s q=%s",
            source,
            ask_kind,
            question[:80],
        )
        return {
            "ok": True,
            "asked": True,
            "question": question,
            "ask_kind": ask_kind,
            "llm": True,
            "decision": data,
            "source": source,
        }

    async def morning_check(self, *, now: datetime | None = None) -> dict[str, Any]:
        """
        Optional morning path: reuse check_once with source=morning.

        If no gaps/habits, send a one-shot light greeting (once per day).
        """
        cfg = load_memory_config(self.repo)
        current = now or datetime.now().astimezone()
        day_key = current.date().isoformat()
        if not cfg.get("proactive_morning_enabled", False):
            return {
                "ok": True,
                "asked": False,
                "skipped": True,
                "reason": "morning_disabled",
                "source": "morning",
            }

        result = await self.check_once(now=current, source="morning")
        if result.get("asked") or result.get("reason") not in (
            "no_gaps_or_habits",
            "should_ask_false",
            "priority_low",
        ):
            return {**result, "source": "morning"}

        # Light greeting when check stayed quiet — at most once per day
        meta = read_meta()
        if meta.get("morning_greeted_date") == day_key:
            return {
                "ok": True,
                "asked": False,
                "skipped": True,
                "reason": "morning_already_greeted",
                "source": "morning",
                "check": result,
            }
        skip = self._gates(cfg, now=current, source="morning")
        if skip:
            return {
                "ok": True,
                "asked": False,
                "skipped": True,
                "reason": skip,
                "source": "morning",
                "check": result,
            }
        greeting = "早上好～今天想聊点什么，或者需要我帮你盯点什么吗？"
        title = "早上好"
        if self.on_ask:
            self.on_ask(title, greeting)
        meta = read_meta()
        meta["morning_greeted_date"] = day_key
        meta["last_proactive_ask_at"] = current.isoformat()
        # Count light greeting toward daily asks when max_asks is enabled
        ask_count = self._today_ask_count(meta, day_key) + 1
        meta["proactive_ask_date"] = day_key
        meta["proactive_ask_count_today"] = ask_count
        write_meta(meta)
        return {
            "ok": True,
            "asked": True,
            "question": greeting,
            "ask_kind": "greeting",
            "llm": False,
            "source": "morning",
            "check": result,
        }
