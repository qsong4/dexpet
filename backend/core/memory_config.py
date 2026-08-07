"""Default + merge helpers for memory_config settings JSON."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.db.repository import Repository

SETTING_KEY = "memory_config"

DEFAULT_MEMORY_CONFIG: dict[str, Any] = {
    "enabled": True,
    "digest_hour": 0,
    "digest_minute": 0,
    "proactive_enabled": True,
    "proactive_mode": "random_check",
    "proactive_checks_min": 10,
    "proactive_checks_max": 20,
    "proactive_checks_per_day": 15,
    "proactive_window_start": "09:00",
    "proactive_window_end": "21:30",
    "proactive_min_gap_minutes": 25,
    # 0 = unlimited successful asks per day (anti-spam via other gates)
    "proactive_max_asks_per_day": 0,
    # 0 = no ask cooldown between successful asks (same semantics as max_asks=0)
    "proactive_ask_cooldown_minutes": 0,
    "proactive_quiet_after_chat_minutes": 20,
    "proactive_user_dismiss_cooldown_hours": 24,
    "proactive_pattern_min_confidence": "medium",
    "proactive_pattern_cooldown_hours": 48,
    "proactive_morning_enabled": False,
    "proactive_morning_hour": 9,
    "proactive_morning_minute": 30,
    "proactive_min_priority": "medium",
}


def merge_memory_config(raw: Any = None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_MEMORY_CONFIG)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in cfg or key.startswith("proactive_") or key in (
                "enabled",
                "digest_hour",
                "digest_minute",
            ):
                cfg[key] = value
    # Normalize check count: if only per_day set and min/max absent in raw, keep defaults;
    # if per_day explicitly set with min==max missing, sync min/max to per_day when equal intent.
    cmin = int(cfg.get("proactive_checks_min", 10))
    cmax = int(cfg.get("proactive_checks_max", 20))
    if cmin > cmax:
        cmin, cmax = cmax, cmin
    cfg["proactive_checks_min"] = max(1, cmin)
    cfg["proactive_checks_max"] = max(cfg["proactive_checks_min"], cmax)
    cfg["proactive_checks_per_day"] = int(
        cfg.get("proactive_checks_per_day", 15) or 15
    )
    return cfg


def load_memory_config(repo: Repository) -> dict[str, Any]:
    return merge_memory_config(repo.get_setting_json(SETTING_KEY, None))


def save_memory_config(repo: Repository, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_memory_config(repo)
    current.update(updates or {})
    merged = merge_memory_config(current)
    repo.set_setting_json(SETTING_KEY, merged)
    return merged
