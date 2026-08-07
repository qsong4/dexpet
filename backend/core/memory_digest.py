"""Nightly memory digest: messages → profile.md + daily/YYYY-MM-DD.md."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from backend.core.llm_json import extract_llm_json
from backend.core.memory import add_memory
from backend.core.memory_files import (
    clear_digest_failure,
    local_day_bounds_utc_iso,
    read_meta,
    read_profile,
    update_meta,
    write_daily,
    write_open_questions,
    write_profile,
)
from backend.db.repository import Repository

logger = logging.getLogger("dexpet.memory_digest")

DIGEST_SYSTEM = """你是 DexPet 的记忆整理器。根据当日对话与近日摘要，更新用户画像与日摘要。
规则：
- 只提取稳定事实、偏好、待办与有证据的习惯；禁止编造。
- 时间规律样本不足须标 confidence=low；宁可不写强断言。
- 「习惯与规律」与「记忆缺口」必须分开，不要混写。
- habits 产出 0–5 条，每条含 text/kind/evidence/confidence（low|medium|high）。
- open_questions 为缺口：open_loops / 好奇心 / 待确认；克制，宁缺毋滥。
- profile_markdown 须含：关于用户、稳定事实、偏好与习惯、习惯与规律、近期关注、关系与称呼、记忆缺口。
- 输出严格 JSON，不要 markdown 围栏。
- JSON 字符串内的双引号必须转义为 \\"，换行必须写成 \\n，禁止尾逗号。
JSON schema:
{
  "daily_markdown": string,
  "profile_markdown": string,
  "open_questions": [{"text": string, "priority": "low"|"medium"|"high", "source": string}],
  "habits": [{"id": string, "text": string, "kind": "request_type"|"time_pattern"|"theme", "evidence": string, "confidence": "low"|"medium"|"high"}],
  "fts_facts": [string]
}
"""

RETRY_REMINDER = (
    "上次输出不是可解析的严格 JSON。"
    "请仅输出一个 JSON 对象，不要 markdown 围栏或解释。"
    "字符串内双引号用 \\\"，换行用 \\n，不要尾逗号。"
)


def _extract_json(text: str) -> dict[str, Any]:
    return extract_llm_json(text)


def _format_transcript(rows: list[dict[str, Any]], limit_chars: int = 12000) -> str:
    lines = [f"{r.get('role')}: {r.get('content', '')}" for r in rows]
    text = "\n".join(lines)
    if len(text) <= limit_chars:
        return text
    return text[-limit_chars:]


def _format_recent_dailies(n: int = 7, *, before: date) -> str:
    from datetime import timedelta

    from backend.core.memory_files import read_daily

    chunks: list[str] = []
    budget = 3000
    for i in range(1, n + 1):
        day = before - timedelta(days=i)
        content = read_daily(day).strip()
        if not content:
            continue
        snippet = content[: min(budget, 600)]
        chunks.append(f"## {day.isoformat()}\n{snippet}")
        budget -= len(snippet)
        if budget <= 0:
            break
    return "\n\n".join(chunks) if chunks else "（无）"


def _open_questions_markdown(items: list[Any]) -> str:
    lines = ["# 记忆缺口", ""]
    if not items:
        lines.append("（空）")
        return "\n".join(lines)
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            pri = item.get("priority", "medium")
            src = item.get("source", "")
            if text:
                lines.append(f"- [{pri}] {text}" + (f" ({src})" if src else ""))
        elif isinstance(item, str) and item.strip():
            lines.append(f"- {item.strip()}")
    return "\n".join(lines) + "\n"


def _has_meaningful_dialogue(rows: list[dict[str, Any]]) -> bool:
    for r in rows:
        if r.get("role") in ("user", "assistant") and str(r.get("content", "")).strip():
            return True
    return False


def _preview_raw(text: str, limit: int = 800) -> str:
    raw = (text or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "…"


def _degraded_digest(day_key: str, transcript: str, raw_llm: str) -> dict[str, Any]:
    snippet = (transcript or "").strip()
    if len(snippet) > 1200:
        snippet = snippet[:1200] + "…"
    raw_snip = (raw_llm or "").strip()
    if len(raw_snip) > 600:
        raw_snip = raw_snip[:600] + "…"
    daily_md = (
        f"# {day_key} 日摘要\n\n"
        f"## 要点\n"
        f"- （LLM JSON 解析失败，已降级为空摘要）\n\n"
        f"## 对话原文片段\n"
        f"```\n{snippet or '（无）'}\n```\n\n"
        f"## 模型原始输出片段\n"
        f"```\n{raw_snip or '（无）'}\n```\n"
    )
    old_profile = (read_profile() or "").strip()
    if old_profile:
        profile_md = old_profile if old_profile.endswith("\n") else old_profile + "\n"
    else:
        profile_md = (
            "# 关于用户\n\n"
            "## 稳定事实\n- （暂无）\n\n"
            "## 偏好与习惯\n- （暂无）\n\n"
            "## 习惯与规律\n- （暂无）\n\n"
            "## 近期关注\n- （暂无）\n\n"
            "## 关系与称呼\n- （暂无）\n\n"
            "## 记忆缺口\n- （暂无；digest 降级）\n"
        )
    return {
        "daily_markdown": daily_md,
        "profile_markdown": profile_md,
        "open_questions": [],
        "habits": [],
        "fts_facts": [],
    }


async def _parse_digest_response(
    llm: Any,
    messages: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, bool]:
    """Try parse; on failure retry once. Returns (data|None, last_raw, retried)."""
    result = await llm.chat(messages, tools=None, temperature=0.2)
    raw = result.content or ""
    try:
        return extract_llm_json(raw), raw, False
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "digest JSON parse failed (%s); raw=%s",
            exc,
            _preview_raw(raw),
        )

    retry_messages = list(messages) + [
        {"role": "assistant", "content": raw or ""},
        {"role": "user", "content": RETRY_REMINDER},
    ]
    result2 = await llm.chat(retry_messages, tools=None, temperature=0.1)
    raw2 = result2.content or ""
    try:
        return extract_llm_json(raw2), raw2, True
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "digest JSON parse retry failed (%s); raw=%s",
            exc,
            _preview_raw(raw2),
        )
        return None, raw2 or raw, True


class MemoryDigestService:
    def __init__(self, repo: Repository, llm: Any | None = None) -> None:
        self.repo = repo
        self.llm = llm

    def set_llm(self, llm: Any | None) -> None:
        self.llm = llm

    async def run(
        self,
        for_date: date | None = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        day = for_date or date.today()
        day_key = day.isoformat()
        meta = read_meta()
        if not force and meta.get("last_success_date") == day_key:
            return {"ok": True, "skipped": True, "reason": "already_done", "date": day_key}

        start_iso, end_iso = local_day_bounds_utc_iso(day)
        rows = self.repo.list_messages_between(start_iso, end_iso)

        if not _has_meaningful_dialogue(rows):
            write_daily(
                day,
                f"# {day_key} 日摘要\n\n## 要点\n- （当日无有效对话）\n",
            )
            update_meta(
                last_success_date=day_key,
                last_digest_at=datetime.now().astimezone().isoformat(),
                last_digest_empty=True,
            )
            clear_digest_failure()
            return {"ok": True, "skipped": False, "empty": True, "date": day_key, "llm": False}

        if self.llm is None:
            raise RuntimeError("LLM not configured for memory digest")

        old_profile = read_profile() or "（尚无画像）"
        recent_daily = _format_recent_dailies(7, before=day)
        transcript = _format_transcript(rows)
        user_prompt = (
            f"整理日期：{day_key}\n\n"
            f"【旧画像】\n{old_profile[:4000]}\n\n"
            f"【近几日摘要（习惯提炼）】\n{recent_daily}\n\n"
            f"【当日对话】\n{transcript}\n"
        )
        messages = [
            {"role": "system", "content": DIGEST_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        data, raw, retried = await _parse_digest_response(self.llm, messages)
        degraded = False
        if data is None:
            degraded = True
            data = _degraded_digest(day_key, transcript, raw)

        daily_md = str(data.get("daily_markdown") or "").strip()
        profile_md = str(data.get("profile_markdown") or "").strip()
        if not daily_md or not profile_md:
            degraded = True
            data = _degraded_digest(day_key, transcript, raw)
            daily_md = str(data.get("daily_markdown") or "").strip()
            profile_md = str(data.get("profile_markdown") or "").strip()
            if not daily_md or not profile_md:
                raise ValueError("digest missing daily_markdown or profile_markdown")

        habits = data.get("habits") or []
        if isinstance(habits, list) and habits and not degraded:
            if "习惯与规律" not in profile_md:
                habit_lines = []
                for h in habits[:5]:
                    if isinstance(h, dict) and h.get("text"):
                        habit_lines.append(
                            f"- {h['text']}（置信度：{h.get('confidence', 'low')}；"
                            f"依据：{h.get('evidence', '')}）"
                        )
                if habit_lines:
                    profile_md = (
                        profile_md.rstrip()
                        + "\n\n## 习惯与规律\n"
                        + "\n".join(habit_lines)
                        + "\n"
                    )

        write_daily(day, daily_md if daily_md.endswith("\n") else daily_md + "\n")
        write_profile(profile_md if profile_md.endswith("\n") else profile_md + "\n")
        oq = data.get("open_questions") or []
        if isinstance(oq, list):
            write_open_questions(_open_questions_markdown(oq))

        if not degraded:
            for fact in (data.get("fts_facts") or [])[:20]:
                if isinstance(fact, str) and fact.strip():
                    add_memory(self.repo.conn, fact.strip(), kind="profile")
            add_memory(
                self.repo.conn,
                daily_md[:500],
                kind="daily",
            )

        habit_list = (
            [h for h in habits if isinstance(h, dict)][:5]
            if isinstance(habits, list) and not degraded
            else []
        )
        update_meta(
            last_success_date=day_key,
            last_digest_at=datetime.now().astimezone().isoformat(),
            last_digest_empty=bool(degraded),
            last_digest_degraded=bool(degraded),
            habits=habit_list,
            open_questions=oq if isinstance(oq, list) and not degraded else [],
        )
        clear_digest_failure()
        return {
            "ok": True,
            "skipped": False,
            "empty": False,
            "degraded": degraded,
            "retried": retried,
            "date": day_key,
            "llm": True,
            "habits": len(habit_list),
        }
