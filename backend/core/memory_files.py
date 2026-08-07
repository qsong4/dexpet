"""Markdown file-layer long-term memory (profile + daily + meta)."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.paths import memory_dir as paths_memory_dir


def memory_dir() -> Path:
    return paths_memory_dir()


def daily_dir() -> Path:
    path = memory_dir() / "daily"
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_path() -> Path:
    return memory_dir() / "profile.md"


def meta_path() -> Path:
    return memory_dir() / "meta.json"


def open_questions_path() -> Path:
    return memory_dir() / "open_questions.md"


def daily_path(day: date | str) -> Path:
    key = day if isinstance(day, str) else day.isoformat()
    return daily_dir() / f"{key}.md"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def read_profile() -> str:
    path = profile_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def profile_mtime() -> float:
    """Return profile.md mtime, or 0.0 if missing. Used for optimistic save."""
    path = profile_path()
    if not path.exists():
        return 0.0
    return path.stat().st_mtime


def write_profile(content: str) -> None:
    _atomic_write_text(profile_path(), content)


def record_digest_failure(*, error: str, for_date: str | None = None) -> dict[str, Any]:
    """Persist digest failure for UI + one-shot bubble notification."""
    day_key = for_date or date.today().isoformat()
    meta = read_meta()
    failures = list(meta.get("failures") or [])
    entry = {
        "at": datetime.now().astimezone().isoformat(),
        "kind": "digest",
        "error": str(error)[:500],
        "date": day_key,
    }
    failures.append(entry)
    meta["failures"] = failures[-10:]
    meta["last_digest_failure"] = entry
    meta["digest_failure_unread"] = True
    write_meta(meta)
    return meta


def clear_digest_failure() -> dict[str, Any]:
    """Clear failure markers after a successful digest."""
    meta = read_meta()
    meta.pop("last_digest_failure", None)
    meta["digest_failure_unread"] = False
    # Keep digest_failure_notified_date so we don't re-spam after success+new failure same day
    write_meta(meta)
    return meta


def consume_digest_failure_notification(*, today: str | None = None) -> dict[str, Any] | None:
    """
    If there is an unread digest failure not yet bubbled today, return it and mark notified.

    Strategy: at most one bubble per local calendar day per failure wave.
    last_digest_failure remains until clear_digest_failure (for settings banner).
    """
    day_key = today or date.today().isoformat()
    meta = read_meta()
    failure = meta.get("last_digest_failure")
    if not failure or not meta.get("digest_failure_unread"):
        return None
    if meta.get("digest_failure_notified_date") == day_key:
        # Already pushed today; drop unread so startups don't keep seeing unread
        meta["digest_failure_unread"] = False
        write_meta(meta)
        return None
    meta["digest_failure_unread"] = False
    meta["digest_failure_notified_date"] = day_key
    write_meta(meta)
    return failure if isinstance(failure, dict) else {"error": str(failure)}


def read_daily(day: date | str) -> str:
    path = daily_path(day)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_daily(day: date | str, content: str) -> None:
    _atomic_write_text(daily_path(day), content)


def read_open_questions() -> str:
    path = open_questions_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_open_questions(content: str) -> None:
    _atomic_write_text(open_questions_path(), content)


def read_meta() -> dict[str, Any]:
    path = meta_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_meta(data: dict[str, Any]) -> None:
    _atomic_write_text(meta_path(), json.dumps(data, ensure_ascii=False, indent=2))


def update_meta(**kwargs: Any) -> dict[str, Any]:
    meta = read_meta()
    meta.update(kwargs)
    write_meta(meta)
    return meta


def list_recent_dailies(n: int = 3, *, before: date | None = None) -> list[tuple[str, str]]:
    """Return up to n (date_str, content) pairs, newest first, ending at before-1 or today."""
    end = before or date.today()
    out: list[tuple[str, str]] = []
    for i in range(n):
        day = end - timedelta(days=i)
        text = read_daily(day)
        if text.strip():
            out.append((day.isoformat(), text))
    return out


def clear_memory_files(*, include_meta: bool = True) -> None:
    """Reset profile, daily summaries, open_questions; optionally meta."""
    for path in (profile_path(), open_questions_path()):
        if path.exists():
            path.unlink()
    ddir = daily_dir()
    for child in ddir.glob("*.md"):
        child.unlink()
    if include_meta and meta_path().exists():
        meta_path().unlink()


def truncate_chars(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def format_file_memory_block(
    *,
    profile_limit: int = 800,
    daily_limit: int = 400,
    daily_days: int = 3,
) -> str:
    """Assemble profile + recent dailies for prompt injection (hard-ish budget)."""
    parts: list[str] = []
    profile = read_profile().strip()
    if profile:
        parts.append("长期画像：\n" + truncate_chars(profile, profile_limit))
    dailies = list_recent_dailies(daily_days)
    if dailies:
        budget = daily_limit
        daily_chunks: list[str] = []
        for day_str, content in dailies:
            if budget <= 0:
                break
            snippet = truncate_chars(content.strip(), min(budget, 200))
            daily_chunks.append(f"[{day_str}]\n{snippet}")
            budget -= len(snippet)
        if daily_chunks:
            parts.append("近日摘要：\n" + "\n\n".join(daily_chunks))
    if not parts:
        return ""
    return "\n\n".join(parts)


def local_day_bounds_utc_iso(day: date, *, tz: datetime.tzinfo | None = None) -> tuple[str, str]:
    """Return [start, end) ISO strings in UTC for a local calendar day."""
    from datetime import timezone

    local_tz = tz or datetime.now().astimezone().tzinfo
    start_local = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=local_tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )
